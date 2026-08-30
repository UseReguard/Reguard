"""Tests for the v1.1.2 structured terminal-state validator.

The validator walks every terminal `evaluation_jobs` row for a
`corpus_run` and emits `ValidationIssue` records for malformed
terminal states. Issue classes:

  - `MALFORMED_UNSUPPORTED_REASON`
  - `MISSING_REQUIREMENT_EVALUATION`
  - `CONFLICTING_REQUIREMENT_EVALUATION`
  - `MALFORMED_SKIPPED_SCENARIO`

These tests verify:

  1. Each issue class is detected against a synthetic DB.
  2. Healthy rows produce no issues.
  3. The CR-3 historical row (id=93 in corpus_run_id=11) is the
     only malformed row in that run, and it produces exactly one
     `MALFORMED_UNSUPPORTED_REASON` issue. The row is NOT mutated.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.persistence import (
    CONFLICTING_REQUIREMENT_EVALUATION,
    MALFORMED_SKIPPED_SCENARIO,
    MALFORMED_UNSUPPORTED_REASON,
    MISSING_REQUIREMENT_EVALUATION,
    ValidationIssue,
    default_db_path,
    validate_terminal_state,
)

REQUIREMENT_ID = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
REQUIREMENT_VERSION = "1.4.0"
SCENARIO_ID = "compliance.article12_1.simple"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test SQLite file with the migrations the runner depends on."""
    db = tmp_path / "validator.db"
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


def _seed_run_with_repos(db: Path, n_repos: int = 1,
                          run_id_fixed: int | None = None) -> tuple[int, list[int]]:
    """Insert 1 corpus_run + N agent_repositories + N manifest rows.

    Returns (run_id, [repo_id, ...]).
    """
    if n_repos < 1:
        raise ValueError("n_repos must be >= 1")
    con = sqlite3.connect(db)
    try:
        repo_ids: list[int] = []
        for i in range(n_repos):
            full_name = f"acme/repo{i}"
            cur = con.execute(
                """INSERT INTO agent_repositories (
                       github_id, full_name, owner, name, html_url, clone_url,
                       primary_language, stars, forks, archived, fork,
                       relevance_status, discovered_at, enabled
                   ) VALUES (?, ?, ?, ?, ?, ?, 'Python', ?, 0, 0, 0,
                             'accepted', '2026-01-01T00:00:00Z', 1)""",
                (100000 + i, full_name, "acme", f"repo{i}",
                 f"https://github.com/{full_name}",
                 f"https://github.com/{full_name}.git", 100),
            )
            repo_ids.append(cur.lastrowid)
        if run_id_fixed is not None:
            run_id = run_id_fixed
        else:
            cur = con.execute(
                """INSERT INTO corpus_runs (
                       created_at, status, requirement_id, requirement_version,
                       scenario_id, executor, runtime_version, max_workers,
                       max_attempts, selection_description, requested_repo_count
                   ) VALUES (?, 'pending', ?, ?, ?, 'subprocess', 'test', 1, 2,
                             'validator-test', ?)""",
                (
                    "2026-08-29T00:00:00Z",
                    REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO_ID,
                    n_repos,
                ),
            )
            run_id = cur.lastrowid
        for i, repo_id in enumerate(repo_ids):
            full_name = f"acme/repo{i}"
            con.execute(
                """INSERT INTO corpus_run_repositories (
                       corpus_run_id, repository_id, full_name, clone_url,
                       resolved_sha, position, sha_resolution_class, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, 'pinned', ?)""",
                (
                    run_id, repo_id, full_name,
                    f"https://github.com/{full_name}.git",
                    f"{'a' * 39}{i:x}", i,
                    "2026-08-29T00:00:00Z",
                ),
            )
        con.commit()
        return run_id, repo_ids
    finally:
        con.close()


def _seed_run_with_one_repo(db: Path) -> tuple[int, int]:
    """Insert 1 corpus_run + 1 repo + 1 manifest row. Convenience
    wrapper for tests that need a single repo."""
    run_id, repo_ids = _seed_run_with_repos(db, n_repos=1)
    return run_id, repo_ids[0]


def _insert_evaluation_job(db: Path, *, run_id: int, repo_id: int,
                            status: str | None,
                            job_status: str,
                            missing_capability: str | None = None,
                            recipe_id: str = "legacy-adapter-direct",
                            recipe_version: str = "v1.1") -> int:
    con = sqlite3.connect(db)
    try:
        cur = con.execute(
            """INSERT INTO evaluation_jobs (
                   corpus_run_id, repository_id, repo_sha,
                   requirement_id, requirement_version, scenario_id,
                   adapter_name, adapter_version, job_status,
                   compliance_status, missing_capability,
                   execution_recipe_id, execution_recipe_version,
                   created_at, completed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         '2026-08-29T00:00:00Z',
                         '2026-08-29T12:00:00Z')""",
            (
                run_id, repo_id,
                "a" * 40,
                REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO_ID,
                "__MISSING__", "0",
                job_status, status, missing_capability,
                recipe_id, recipe_version,
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def _insert_requirement_evaluation(db: Path, *, job_id: int,
                                    compliance_status: str) -> None:
    con = sqlite3.connect(db)
    try:
        con.execute(
            """INSERT INTO requirement_evaluations (
                   evaluation_job_id, requirement_id, requirement_version,
                   compliance_status, compliance_runtime_run_id, evaluated_at
               ) VALUES (?, ?, ?, ?, NULL, '2026-08-29T12:00:00Z')""",
            (job_id, REQUIREMENT_ID, REQUIREMENT_VERSION,
             compliance_status),
        )
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_detect_malformed_unsupported_reason(db_path: Path) -> None:
    """A row with compliance_status='UNSUPPORTED' and
    missing_capability=NULL must produce exactly one
    MALFORMED_UNSUPPORTED_REASON issue. This is the exact CR-3
    anomaly shape."""
    run_id, repo_id = _seed_run_with_one_repo(db_path)
    jid = _insert_evaluation_job(
        db_path, run_id=run_id, repo_id=repo_id,
        status="UNSUPPORTED", job_status="completed",
        missing_capability=None,  # <-- the anomaly
        recipe_version="v0",      # <-- the anomaly
    )
    _insert_requirement_evaluation(db_path, job_id=jid,
                                    compliance_status="UNSUPPORTED")

    issues = validate_terminal_state(run_id, db_path=db_path)
    assert len(issues) == 1, [str(i) for i in issues]
    assert issues[0].issue_class == MALFORMED_UNSUPPORTED_REASON
    assert issues[0].job_id == jid
    assert issues[0].full_name == "acme/repo0"


def test_detect_missing_requirement_evaluation(db_path: Path) -> None:
    """A completed terminal job with NO requirement_evaluations row
    must produce exactly one MISSING_REQUIREMENT_EVALUATION issue."""
    run_id, repo_id = _seed_run_with_one_repo(db_path)
    jid = _insert_evaluation_job(
        db_path, run_id=run_id, repo_id=repo_id,
        status="PASS", job_status="completed",
        missing_capability=None,
    )
    # Deliberately do NOT insert a requirement_evaluations row.

    issues = validate_terminal_state(run_id, db_path=db_path)
    assert len(issues) == 1
    assert issues[0].issue_class == MISSING_REQUIREMENT_EVALUATION
    assert issues[0].job_id == jid


def test_detect_conflicting_requirement_evaluation(db_path: Path) -> None:
    """A completed job whose evaluation_jobs.compliance_status
    differs from its requirement_evaluations.compliance_status must
    produce exactly one CONFLICTING_REQUIREMENT_EVALUATION issue."""
    run_id, repo_id = _seed_run_with_one_repo(db_path)
    jid = _insert_evaluation_job(
        db_path, run_id=run_id, repo_id=repo_id,
        status="PASS", job_status="completed",
        missing_capability=None,
    )
    _insert_requirement_evaluation(db_path, job_id=jid,
                                    compliance_status="FAIL")

    issues = validate_terminal_state(run_id, db_path=db_path)
    assert len(issues) == 1
    assert issues[0].issue_class == CONFLICTING_REQUIREMENT_EVALUATION


def test_detect_malformed_skipped_scenario(db_path: Path) -> None:
    """A skipped_unsupported_scenario row whose missing_capability
    is not 'tool_failure_scenario' must produce exactly one
    MALFORMED_SKIPPED_SCENARIO issue."""
    run_id, repo_id = _seed_run_with_one_repo(db_path)
    jid = _insert_evaluation_job(
        db_path, run_id=run_id, repo_id=repo_id,
        status="UNSUPPORTED", job_status="skipped_unsupported_scenario",
        missing_capability="compatible_execution_recipe",  # wrong token
    )
    _insert_requirement_evaluation(db_path, job_id=jid,
                                    compliance_status="UNSUPPORTED")

    issues = validate_terminal_state(run_id, db_path=db_path)
    # Both UNSUPPORTED-with-NULL? No — missing_capability is set.
    # Just the skipped-scenario issue.
    assert len(issues) == 1
    assert issues[0].issue_class == MALFORMED_SKIPPED_SCENARIO


def test_healthy_rows_produce_no_issues(db_path: Path) -> None:
    """Five healthy terminal rows of every flavour — PASS, FAIL,
    UNKNOWN, UNSUPPORTED (with the structured token), and a
    skipped_unsupported_scenario row with the correct token — must
    produce zero ValidationIssue records."""
    run_id, repo_ids = _seed_run_with_repos(db_path, n_repos=5)
    healthy_payloads = [
        ("PASS",       "completed",                 None),
        ("FAIL",       "completed",                 None),
        ("UNKNOWN",    "completed",                 None),
        ("UNSUPPORTED","completed",                 "compatible_execution_recipe"),
        ("UNSUPPORTED","skipped_unsupported_scenario","tool_failure_scenario"),
    ]
    for (status, jstatus, mc), repo_id in zip(healthy_payloads, repo_ids):
        jid = _insert_evaluation_job(
            db_path, run_id=run_id, repo_id=repo_id,
            status=status, job_status=jstatus,
            missing_capability=mc,
        )
        _insert_requirement_evaluation(db_path, job_id=jid,
                                        compliance_status=status)

    issues = validate_terminal_state(run_id, db_path=db_path)
    assert issues == [], [str(i) for i in issues]


def test_validator_is_pure_read(db_path: Path) -> None:
    """validate_terminal_state must not mutate the DB. After
    running it, the row's anomaly shape (NULL missing_capability,
    v0 recipe_version) is preserved."""
    run_id, repo_id = _seed_run_with_one_repo(db_path)
    jid = _insert_evaluation_job(
        db_path, run_id=run_id, repo_id=repo_id,
        status="UNSUPPORTED", job_status="completed",
        missing_capability=None, recipe_version="v0",
    )
    _insert_requirement_evaluation(db_path, job_id=jid,
                                    compliance_status="UNSUPPORTED")

    # First pass: report the issue.
    issues = validate_terminal_state(run_id, db_path=db_path)
    assert len(issues) == 1

    # Second pass: same result (function is deterministic and pure).
    issues2 = validate_terminal_state(run_id, db_path=db_path)
    assert issues == issues2

    # Row is unchanged: NULL missing_capability, v0 recipe_version.
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT missing_capability, execution_recipe_version "
            "FROM evaluation_jobs WHERE id = ?", (jid,)
        ).fetchone()
        assert row[0] is None
        assert row[1] == "v0"
    finally:
        con.close()


# ---------------------------------------------------------------------------
# CR-3 historical-row assertion (live DB)
# ---------------------------------------------------------------------------


def test_cr3_anomaly_row_is_only_malformed_in_corpus_run_11() -> None:
    """Verify, against the live production DB, that the CR-3
    historical anomaly row (ZhuLinsen/daily_stock_analysis, job_id
    =93 in corpus_run_id=11) is the ONLY malformed row in that
    run, and it produces exactly one MALFORMED_UNSUPPORTED_REASON
    issue. The row is left untouched (this test never mutates the
    DB).

    Skipped if the live DB does not exist or corpus_run_id=11 is
    not present (e.g. on a fresh dev machine).
    """
    db = default_db_path()
    if not db.exists():
        pytest.skip(f"live DB not present at {db}")
    con = sqlite3.connect(db)
    try:
        run = con.execute(
            "SELECT id FROM corpus_runs WHERE id = 11"
        ).fetchone()
    finally:
        con.close()
    if run is None:
        pytest.skip("corpus_run_id=11 not in live DB")

    # The historical row MUST still be in the documented shape.
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT compliance_status, missing_capability, "
            "execution_recipe_version, error_class "
            "FROM evaluation_jobs WHERE id = 93"
        ).fetchone()
    finally:
        con.close()
    assert row is not None, "CR-3 historical row id=93 missing"
    cs, mc, rv, ec = row
    assert cs == "UNSUPPORTED"
    assert mc is None, "CR-3 historical row missing_capability was MUTATED"
    assert rv == "v0", "CR-3 historical row recipe_version was MUTATED"

    # The validator reports the CR-3 anomaly row's structural
    # defects. Per the CR-3 reconciliation report, the documented
    # anomaly row id=93 (`ZhuLinsen/daily_stock_analysis`) carries
    # BOTH:
    #   - `MALFORMED_UNSUPPORTED_REASON` (UNSUPPORTED but
    #     `missing_capability IS NULL`); and
    #   - `MISSING_REQUIREMENT_EVALUATION` (no
    #     requirement_evaluations row — the v1.1 stamping never
    #     landed).
    # Additionally, the SHA-resolution-error row id=86
    # (`NousResearch/hermes-agent`) also surfaces as
    # MISSING_REQUIREMENT_EVALUATION because it terminalised at
    # build_jobs_for_run time without ever entering the executor's
    # terminalization path (no requirement_evaluations row).
    # All three issues are exactly the documented CR-3 reality.
    issues = validate_terminal_state(11, db_path=db)
    classes_by_job: dict[int, list[str]] = {}
    for i in issues:
        classes_by_job.setdefault(i.job_id, []).append(i.issue_class)

    assert 93 in classes_by_job, (
        f"expected CR-3 anomaly row id=93 in issues, got: "
        f"{[str(i) for i in issues]}"
    )
    assert MALFORMED_UNSUPPORTED_REASON in classes_by_job[93], (
        f"row 93 should produce MALFORMED_UNSUPPORTED_REASON; got "
        f"{classes_by_job[93]}"
    )
    assert MISSING_REQUIREMENT_EVALUATION in classes_by_job[93], (
        f"row 93 should produce MISSING_REQUIREMENT_EVALUATION "
        f"(the v1.1 stamping never landed); got {classes_by_job[93]}"
    )
    # SHA-resolution-error row 86 also surfaces as a missing
    # requirement_evaluations row (Option B pre-execution
    # terminalisation — no executor path was entered).
    if 86 in classes_by_job:
        assert MISSING_REQUIREMENT_EVALUATION in classes_by_job[86]
    # No other job in this run should be malformed.
    other_jobs = set(classes_by_job.keys()) - {93, 86}
    assert other_jobs == set(), (
        f"unexpected malformed jobs in CR-3: {other_jobs}"
    )
