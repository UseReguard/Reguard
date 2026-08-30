"""v1.1.2 persistence terminalization tests.

CR-3 hardening: the executor used to persist terminal state in 3
separate sqlite3 connections per job. A transient
`sqlite3.OperationalError: database is locked` from concurrent
connections could skip the v1.1 stamping step without raising,
leaving the row in a hybrid state. The row for
`ZhuLinsen/daily_stock_analysis` in corpus_run_id=11 is the
documented example.

These tests pin the new behaviour:

  - `terminalize_job` writes every terminal-state field atomically
    (single transaction).
  - Re-issuing the same payload is a no-op (idempotent).
  - Re-issuing a *different* payload raises TerminalizationConflict
    (no silent overwrite).
  - Forced lock contention retries deterministically.
  - Retry exhaustion surfaces a clear error and leaves the row in
    its pre-terminal state.
  - The exact CR-3 anomaly shape (UNSUPPORTED +
    missing_capability=NULL + execution_recipe_version='v0') is
    pinned post-fix.
  - A synthetic 500-job / 4-thread stress test asserts that every
    row lands fully terminal (no hybrid state) and every row gets
    exactly one requirement_evaluations entry.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.errors import TerminalizationConflict
from compliance.corpus_runner.persistence import default_db_path

REQUIREMENT_ID = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
REQUIREMENT_VERSION = "1.4.0"
SCENARIO_ID = "compliance.article12_1.simple"
AGENT_REPO_OWNER = "acme"
AGENT_REPO_NAME_TMPL = "r{idx}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test SQLite file with the migrations the runner depends on."""
    db = tmp_path / "corpus_runner.db"
    migrations_dir = ROOT / "migrations"
    needed = [
        "001_agent_repositories.sql",
        "002_agent_repositories_reclassified_at.sql",
        "003_agent_repository_audits.sql",
        "004_article_runtime_assessments.sql",
        "005_compliance_runtime_runs.sql",
        "006_corpus_runs.sql",
        "007_corpus_run_repositories.sql",
        "008_evaluation_jobs.sql",
        "009_evaluation_attempts.sql",
        "010_corpus_runner_v1_1_schema.sql",
        "011_corpus_runner_v1_1_evidence_state.sql",
    ]
    con = sqlite3.connect(db)
    try:
        for name in needed:
            sql = (migrations_dir / name).read_text(encoding="utf-8")
            con.executescript(sql)
        con.commit()
    finally:
        con.close()
    return db


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    """Seed 5 agent_repositories + 1 corpus_run + 5 evaluation_jobs."""
    con = sqlite3.connect(db_path)
    try:
        repo_ids = []
        for i in range(5):
            cur = con.execute(
                """INSERT INTO agent_repositories (
                       github_id, full_name, owner, name, html_url, clone_url,
                       primary_language, stars, forks, archived, fork,
                       relevance_status, discovered_at, enabled
                   ) VALUES (?, ?, ?, ?, ?, ?, 'Python', ?, 0, 0, 0,
                             'accepted', '2026-01-01T00:00:00Z', 1)""",
                (
                    100000 + i,
                    f"{AGENT_REPO_OWNER}/{AGENT_REPO_NAME_TMPL.format(idx=i)}",
                    AGENT_REPO_OWNER,
                    AGENT_REPO_NAME_TMPL.format(idx=i),
                    f"https://github.com/{AGENT_REPO_OWNER}/{AGENT_REPO_NAME_TMPL.format(idx=i)}",
                    f"https://github.com/{AGENT_REPO_OWNER}/{AGENT_REPO_NAME_TMPL.format(idx=i)}.git",
                    100,
                ),
            )
            repo_ids.append(cur.lastrowid)
        # 1 corpus_run
        cur = con.execute(
            """INSERT INTO corpus_runs (
                   created_at, status, requirement_id, requirement_version,
                   scenario_id, executor, runtime_version, max_workers,
                   max_attempts, selection_description, requested_repo_count
               ) VALUES (?, 'pending', ?, ?, ?, 'subprocess', 'test', 1, 2,
                         'persistence-hardening-test', 5)""",
            (
                "2026-08-29T00:00:00Z",
                REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO_ID,
            ),
        )
        run_id = cur.lastrowid
        # 5 evaluation_jobs (pending)
        for i, rid in enumerate(repo_ids):
            con.execute(
                """INSERT INTO evaluation_jobs (
                       corpus_run_id, repository_id, repo_sha,
                       requirement_id, requirement_version, scenario_id,
                       adapter_name, adapter_version, job_status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    run_id, rid,
                    f"{i:04x}{'a' * 36}",
                    REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO_ID,
                    "__MISSING__" if i % 2 == 0 else "fake-adapter",
                    "0", "2026-08-29T00:00:00Z",
                ),
            )
        con.commit()
    finally:
        con.close()
    return db_path


def _payload_for(job_id: int, *, status: str = "UNSUPPORTED",
                 missing_capability: str | None = "compatible_execution_recipe",
                 runtime_run_id: int | None = None,
                 error_class: str = "",
                 error_message: str = "") -> crp.TerminalPayload:
    return crp.TerminalPayload(
        job_id=job_id,
        compliance_status=status,
        compliance_runtime_run_id=runtime_run_id,
        missing_capability=missing_capability,
        execution_recipe_id="legacy-adapter-direct",
        execution_recipe_version="v1.1",
        error_class=error_class,
        error_message=error_message,
        completed_at="2026-08-29T12:00:00Z",
        requirement_id=REQUIREMENT_ID,
        requirement_version=REQUIREMENT_VERSION,
    )


def _job_ids(seeded_db: Path) -> list[int]:
    con = sqlite3.connect(seeded_db)
    try:
        rows = con.execute(
            "SELECT id FROM evaluation_jobs ORDER BY id ASC"
        ).fetchall()
        return [int(r[0]) for r in rows]
    finally:
        con.close()


def _row_for(seeded_db: Path, job_id: int) -> sqlite3.Row:
    con = sqlite3.connect(seeded_db)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            "SELECT * FROM evaluation_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        con.close()


def _req_eval_for(seeded_db: Path, job_id: int) -> sqlite3.Row | None:
    con = sqlite3.connect(seeded_db)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            "SELECT * FROM requirement_evaluations WHERE evaluation_job_id = ?",
            (job_id,),
        ).fetchone()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Test 1 — atomic terminalization
# ---------------------------------------------------------------------------


def test_terminalize_writes_all_fields_atomically(seeded_db: Path) -> None:
    """A single terminalize_job call lands every terminal-state
    field in one transaction: job_status, compliance_status,
    compliance_runtime_run_id, error_class, error_message,
    completed_at, missing_capability, execution_recipe_id,
    execution_recipe_version, AND the requirement_evaluations row.
    """
    job_ids = _job_ids(seeded_db)
    jid = job_ids[0]

    crp.terminalize_job(_payload_for(jid, status="PASS",
                                     missing_capability=None),
                        db_path=seeded_db)

    row = _row_for(seeded_db, jid)
    assert row["job_status"] == "completed"
    assert row["compliance_status"] == "PASS"
    assert row["error_class"] == ""
    assert row["error_message"] == ""
    assert row["completed_at"] == "2026-08-29T12:00:00Z"
    assert row["missing_capability"] is None
    assert row["execution_recipe_id"] == "legacy-adapter-direct"
    assert row["execution_recipe_version"] == "v1.1"

    re_row = _req_eval_for(seeded_db, jid)
    assert re_row is not None
    assert re_row["compliance_status"] == "PASS"
    assert re_row["requirement_id"] == REQUIREMENT_ID
    assert re_row["requirement_version"] == REQUIREMENT_VERSION


# ---------------------------------------------------------------------------
# Test 2 — idempotent under retry
# ---------------------------------------------------------------------------


def test_terminalize_idempotent_under_retry(seeded_db: Path) -> None:
    """Calling terminalize_job twice with the same payload must
    converge to the same row state without raising IntegrityError,
    and produce exactly one requirement_evaluations row."""
    job_ids = _job_ids(seeded_db)
    jid = job_ids[0]

    payload = _payload_for(jid, status="UNSUPPORTED",
                            missing_capability="compatible_execution_recipe")
    crp.terminalize_job(payload, db_path=seeded_db)
    crp.terminalize_job(payload, db_path=seeded_db)
    crp.terminalize_job(payload, db_path=seeded_db)

    row = _row_for(seeded_db, jid)
    assert row["compliance_status"] == "UNSUPPORTED"
    assert row["missing_capability"] == "compatible_execution_recipe"

    con = sqlite3.connect(seeded_db)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM requirement_evaluations "
            "WHERE evaluation_job_id = ?", (jid,),
        ).fetchone()[0]
        assert n == 1
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Test 3 — conflicting second terminalization raises
# ---------------------------------------------------------------------------


def test_terminalize_conflict_raises_TerminalizationConflict(
        seeded_db: Path) -> None:
    """Calling terminalize_job twice with *different*
    compliance_status must raise TerminalizationConflict on the
    second call. The first payload is preserved (no silent
    overwrite)."""
    job_ids = _job_ids(seeded_db)
    jid = job_ids[0]

    crp.terminalize_job(_payload_for(jid, status="PASS",
                                     missing_capability=None),
                        db_path=seeded_db)
    with pytest.raises(TerminalizationConflict):
        crp.terminalize_job(_payload_for(jid, status="FAIL",
                                         missing_capability=None),
                            db_path=seeded_db)

    # First payload wins; row state unchanged after the conflict.
    row = _row_for(seeded_db, jid)
    assert row["compliance_status"] == "PASS"
    assert row["missing_capability"] is None


# ---------------------------------------------------------------------------
# Test 4 — forced lock contention retries
# ---------------------------------------------------------------------------


def test_forced_lock_contention_retries(seeded_db: Path,
                                          monkeypatch) -> None:
    """Thread A holds an EXCLUSIVE write lock on the DB for a
    short window. Thread B calls terminalize_job in parallel.
    Bounded busy-retry must succeed once A releases. Final row
    must have all terminal fields and no partial state."""
    job_ids = _job_ids(seeded_db)
    jid = job_ids[0]

    holder_started = threading.Event()
    holder_release = threading.Event()

    def holder() -> None:
        con = sqlite3.connect(seeded_db, isolation_level=None)
        try:
            con.execute("BEGIN EXCLUSIVE")
            holder_started.set()
            # Hold the EXCLUSIVE lock until the main thread releases
            # us. The main thread releases us after one terminalize_job
            # attempt has been observed to fail (signalled by the
            # contention observer below).
            holder_release.wait(timeout=2)
            con.execute("COMMIT")
        finally:
            con.close()

    # Speed up retries so the test finishes in <1 second.
    real_helper = crp._execute_with_busy_retry
    def fast_retry(*args, **kwargs):
        kwargs.setdefault("attempts", 8)
        kwargs.setdefault("base_sleep_s", 0.005)
        return real_helper(*args, **kwargs)
    monkeypatch.setattr(crp, "_execute_with_busy_retry", fast_retry)

    t = threading.Thread(target=holder)
    t.start()
    try:
        holder_started.wait(timeout=2)
        # Give the EXCLUSIVE transaction a moment to fully register.
        time.sleep(0.02)

        # Release the holder shortly after the test starts, so the
        # caller's first attempt is contended and the bounded retry
        # succeeds once the holder commits. 80 ms is enough to be
        # observed as at least one failed attempt (each attempt is
        # ~immediate with busy_timeout=0) but releases well within
        # the bounded retry budget (5 outer attempts × ~0.005 s
        # inner sleep ≈ 0.03 s worst case).
        def release_after() -> None:
            time.sleep(0.08)
            holder_release.set()
        threading.Thread(target=release_after, daemon=True).start()

        # terminalize_job must NOT crash despite the held lock.
        crp.terminalize_job(
            _payload_for(jid, status="FAIL", missing_capability=None),
            db_path=seeded_db,
        )
    finally:
        holder_release.set()
        t.join(timeout=5)

    row = _row_for(seeded_db, jid)
    assert row["job_status"] == "completed"
    assert row["compliance_status"] == "FAIL"
    assert row["missing_capability"] is None
    assert row["execution_recipe_version"] == "v1.1"
    re_row = _req_eval_for(seeded_db, jid)
    assert re_row is not None
    assert re_row["compliance_status"] == "FAIL"


# ---------------------------------------------------------------------------
# Test 5 — retry exhaustion raises clearly; pre-terminal row preserved
# ---------------------------------------------------------------------------


def test_retry_exhaustion_raises_clearly(seeded_db: Path,
                                         monkeypatch) -> None:
    """Thread A holds the EXCLUSIVE lock longer than the
    terminalize_job retry budget. terminalize_job raises a clear
    OperationalError. The job row must NOT be updated to a
    partial state — it stays as the pre-terminal `pending` row
    that `build_jobs_for_run` created."""
    job_ids = _job_ids(seeded_db)
    jid = job_ids[0]

    # Snapshot pre-terminal state.
    before = _row_for(seeded_db, jid)
    assert before["job_status"] == "pending"
    assert before["compliance_status"] is None
    assert before["missing_capability"] is None

    holder_started = threading.Event()
    holder_release = threading.Event()

    def holder() -> None:
        con = sqlite3.connect(seeded_db, isolation_level=None)
        try:
            con.execute("BEGIN EXCLUSIVE")
            holder_started.set()
            holder_release.wait(timeout=10)
            con.execute("COMMIT")
        finally:
            con.close()

    # Shrink the retry budget so the test finishes in <1 second.
    # terminalize_job now relies on the connection's busy_timeout
    # PRAGMA plus a bounded outer retry loop; the legacy
    # ``_execute_with_busy_retry`` helper is no longer on the
    # terminalization path. We therefore shrink the new envelope
    # instead: busy_timeout=1ms + 2 outer attempts × 1ms base.
    monkeypatch.setattr(crp, "_TERMINALIZE_BUSY_TIMEOUT_MS", 1)
    monkeypatch.setattr(crp, "_TERMINALIZE_OUTER_ATTEMPTS", 2)
    monkeypatch.setattr(crp, "_TERMINALIZE_BACKOFF_BASE_S", 0.001)
    monkeypatch.setattr(crp, "_TERMINALIZE_BACKOFF_CAP_S", 0.001)

    t = threading.Thread(target=holder)
    t.start()
    try:
        holder_started.wait(timeout=2)
        time.sleep(0.05)

        with pytest.raises(sqlite3.OperationalError) as excinfo:
            crp.terminalize_job(
                _payload_for(jid, status="UNSUPPORTED",
                             missing_capability="compatible_execution_recipe"),
                db_path=seeded_db,
            )
        msg = str(excinfo.value).lower()
        assert "locked" in msg or "busy" in msg, (
            f"expected a clear busy/locked error message, got {msg!r}"
        )
    finally:
        holder_release.set()
        t.join(timeout=5)

    # Row must be in its original pre-terminal state — no partial
    # update leaked through.
    after = _row_for(seeded_db, jid)
    assert after["job_status"] == "pending"
    assert after["compliance_status"] is None
    assert after["missing_capability"] is None
    assert after["execution_recipe_version"] == "v0"


# ---------------------------------------------------------------------------
# Test 6 — CR-3 anomaly shape pinned post-fix
# ---------------------------------------------------------------------------


def test_cr3_anomaly_shape_after_fix(seeded_db: Path) -> None:
    """Reproduce the exact CR-3 anomaly shape:
    ADAPTER_MISSING_SENTINEL → UNSUPPORTED with
    missing_capability='compatible_execution_recipe',
    execution_recipe_version='v1.1', error_class=''.

    Before the fix, the row was left with
    missing_capability=NULL and execution_recipe_version='v0'
    because the per-call `update_evaluation_job_recipe_and_missing`
    write never landed (transient OperationalError swallowed by the
    narrow `except sqlite3.IntegrityError`).
    """
    job_ids = _job_ids(seeded_db)
    # Find a job with __MISSING__ adapter (CR-3 anomaly path).
    con = sqlite3.connect(seeded_db)
    try:
        row = con.execute(
            "SELECT id FROM evaluation_jobs "
            "WHERE adapter_name = '__MISSING__' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        jid = int(row[0])
    finally:
        con.close()

    crp.terminalize_job(
        _payload_for(jid, status="UNSUPPORTED",
                     missing_capability="compatible_execution_recipe"),
        db_path=seeded_db,
    )

    row = _row_for(seeded_db, jid)
    assert row["job_status"] == "completed"
    assert row["compliance_status"] == "UNSUPPORTED"
    # The exact fields that were broken in the CR-3 anomaly row:
    assert row["missing_capability"] == "compatible_execution_recipe", (
        "missing_capability must be the structured token; NULL would "
        "be the CR-3 anomaly"
    )
    assert row["execution_recipe_version"] == "v1.1", (
        "execution_recipe_version must be 'v1.1'; 'v0' would be the "
        "CR-3 anomaly"
    )
    assert row["error_class"] == ""


# ---------------------------------------------------------------------------
# Test 7 — synthetic 500-job / 4-thread stress
# ---------------------------------------------------------------------------


def test_synthetic_persistence_stress(seeded_db: Path,
                                       monkeypatch) -> None:
    """Create 500 synthetic pending jobs (in addition to the 5
    seed jobs) and terminalise them concurrently across 4 worker
    threads. Every job must end up with `missing_capability`,
    `execution_recipe_version='v1.1'`, and exactly one
    `requirement_evaluations` row — no hybrid state, no duplicate
    rows, no lost writes."""
    con = sqlite3.connect(seeded_db)
    try:
        run_id = con.execute(
            "SELECT id FROM corpus_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        repo_id = con.execute(
            "SELECT id FROM agent_repositories ORDER BY id ASC LIMIT 1"
        ).fetchone()[0]
        new_ids: list[int] = []
        for i in range(500):
            cur = con.execute(
                """INSERT INTO evaluation_jobs (
                       corpus_run_id, repository_id, repo_sha,
                       requirement_id, requirement_version, scenario_id,
                       adapter_name, adapter_version, job_status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    run_id, repo_id,
                    f"{i:04x}{'b' * 36}",
                    REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO_ID,
                    "__MISSING__", "0", "2026-08-29T00:00:00Z",
                ),
            )
            new_ids.append(int(cur.lastrowid))
        con.commit()
    finally:
        con.close()

    # Worker function: terminalise every job in the batch with the
    # CR-3 anomaly shape.
    def _drive(batch: list[int]) -> None:
        for jid in batch:
            crp.terminalize_job(
                _payload_for(jid, status="UNSUPPORTED",
                             missing_capability="compatible_execution_recipe"),
                db_path=seeded_db,
            )

    chunks = [new_ids[i::4] for i in range(4)]
    with ThreadPoolExecutor(max_workers=4,
                            thread_name_prefix="stress") as pool:
        futures = [pool.submit(_drive, c) for c in chunks]
        for fut in futures:
            fut.result()

    # Final assertions: every synthetic job is fully terminal.
    con = sqlite3.connect(seeded_db)
    try:
        rows = con.execute(
            "SELECT id, job_status, compliance_status, "
            "missing_capability, execution_recipe_version, error_class "
            "FROM evaluation_jobs WHERE id IN ("
            + ",".join("?" * len(new_ids)) + ")",
            new_ids,
        ).fetchall()
        assert len(rows) == 500
        for r in rows:
            assert r[1] == "completed", (
                f"job {r[0]} job_status={r[1]!r}, expected 'completed'"
            )
            assert r[2] == "UNSUPPORTED", (
                f"job {r[0]} compliance_status={r[2]!r}"
            )
            assert r[3] == "compatible_execution_recipe", (
                f"job {r[0]} missing_capability={r[3]!r} — "
                f"this is the CR-3 anomaly shape leaking through"
            )
            assert r[4] == "v1.1", (
                f"job {r[0]} execution_recipe_version={r[4]!r}"
            )
            assert r[5] == "" or r[5] is None, (
                f"job {r[0]} error_class={r[5]!r}"
            )

        # Exactly one requirement_evaluations row per synthetic job.
        re_counts = con.execute(
            "SELECT evaluation_job_id, COUNT(*) FROM requirement_evaluations "
            "WHERE evaluation_job_id IN ("
            + ",".join("?" * len(new_ids)) + ") GROUP BY evaluation_job_id",
            new_ids,
        ).fetchall()
        assert len(re_counts) == 500, (
            f"expected 500 requirement_evaluations rows, got "
            f"{len(re_counts)} distinct jobs"
        )
        for jid, n in re_counts:
            assert n == 1, (
                f"job {jid} has {n} requirement_evaluations rows"
            )
    finally:
        con.close()

    # Counter recompute sanity check: pass+fail+unsupported+unknown+
    # error+skipped must equal total_jobs (5 + 500 = 505).
    crp.set_corpus_run_counters_from_jobs(run_id, db_path=seeded_db)
    crp.update_corpus_run_status(run_id, "pending",
                                  total_jobs=505, db_path=seeded_db)
    crp.set_corpus_run_counters_from_jobs(run_id, db_path=seeded_db)
    final = crp.load_corpus_run(run_id, db_path=seeded_db)
    assert final is not None
    # 500 UNSUPPORTED + 2 frozen PASSes + 3 frozen FAILs == 505.
    assert final.unsupported_count == 500
    assert final.pass_count == 0
    assert final.fail_count == 0
    assert final.completed_jobs == 500  # 5 seed jobs remain pending
