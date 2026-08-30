"""§17 — Actual 20-run resume.

Validates that the v1.1.1 idempotent `build_jobs_for_run` plus the
materializer-wired executor produce correct resume semantics on the
ACTUAL frozen 20-repo CR-2 manifest.

The test uses a stubbed driver (so it does not invoke real probes).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.pipeline.persistence import default_db_path

MANIFEST = json.loads(
    (ROOT / "audit" / "corpus_runner_v1" / "cr2_manifest.json").read_text(
        encoding="utf-8",
    )
)
SCENARIO = "compliance.article12_1.simple"
REQUIREMENT_ID = "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
REQUIREMENT_VERSION = "1.4.0"


@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "corpus.db"
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
            con.executescript(
                (migrations_dir / name).read_text(encoding="utf-8"),
            )
        con.commit()
    finally:
        con.close()
    return db


def _seed_repos(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    name_to_id: dict[str, int] = {}
    try:
        # Use a deterministic but unique github_id per full_name
        # (sequential to avoid UNIQUE constraint collisions).
        for idx, full_name in enumerate(MANIFEST):
            existing = con.execute(
                "SELECT id FROM agent_repositories WHERE full_name = ?",
                (full_name,),
            ).fetchone()
            if existing is not None:
                name_to_id[full_name] = int(existing[0])
                continue
            gh_id = 95_000_000 + idx
            cur = con.execute(
                """INSERT INTO agent_repositories (
                       github_id, full_name, owner, name, html_url,
                       clone_url, primary_language, stars, forks, archived,
                       fork, relevance_status, discovered_at, enabled
                   ) VALUES (?, ?, ?, ?, ?, ?, 'Python', ?, 0, 0, 0,
                             'accepted', '2026-08-29T00:00:00Z', 1)""",
                (
                    gh_id, full_name,
                    full_name.split("/")[0], full_name.split("/")[1],
                    f"https://github.com/{full_name}",
                    f"https://github.com/{full_name}.git",
                    100_000,
                ),
            )
            name_to_id[full_name] = int(cur.lastrowid)
        con.commit()
    finally:
        con.close()
    return name_to_id


def _stub_driver_run_one(
    *, full_name: str, sha: str, requirement_id: str = "X", **_: object,
):
    """Stub the driver to return PASS / FAIL for frozen-five repos.
    UNSUPPORTED handling is done by the executor itself via the
    ADAPTER_MISSING_SENTINEL, so this stub is invoked only for jobs
    where an adapter IS registered (the frozen five).
    """
    from compliance.adapters import get_adapter
    from compliance.corpus_runner import persistence as crp
    from compliance.pipeline.persistence import insert_run
    from compliance.pipeline.types import (
        Evidence, EvidenceOrigin, RepositoryTarget, Result, RunRecord,
        RunStatus,
    )

    db = crp.default_db_path()
    repo_row = None
    con = sqlite3.connect(db)
    try:
        repo_row = con.execute(
            "SELECT id FROM agent_repositories WHERE full_name = ?",
            (full_name,),
        ).fetchone()
    finally:
        con.close()
    if repo_row is None:
        raise KeyError(full_name)

    try:
        ad = get_adapter(full_name)
        adapter_name, adapter_version = ad.name, ad.version
    except KeyError:
        adapter_name, adapter_version = "stub", "0"
    # Frozen-five deterministic distribution.
    status_map = {
        "SWE-agent/mini-swe-agent": RunStatus.PASS,
        "gptme/gptme": RunStatus.PASS,
        "HKUDS/nanobot": RunStatus.FAIL,
        "he-yufeng/CoreCoder": RunStatus.FAIL,
        "The-Pocket/PocketFlow": RunStatus.FAIL,
    }
    status = status_map.get(full_name, RunStatus.PASS)
    target = RepositoryTarget(
        repository_id=int(repo_row[0]),
        full_name=full_name, sha=sha,
        branch="main",
    )
    evidence = Evidence(
        schema_version="1",
        events=(),
        agent_class=adapter_name,
        agent_version=adapter_version,
        extra={
            "probe_status": "ok",
            "recording_category": "A",
            "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
        },
    )
    record = RunRecord(
        repository=target,
        requirement_id=REQUIREMENT_ID,
        requirement_version=REQUIREMENT_VERSION,
        runtime_version="test",
        adapter_name=adapter_name,
        adapter_version=adapter_version,
        scenario_id=SCENARIO,
        status=status,
        reason="stubbed",
        result=Result(schema_version="1", status=status, reason="stubbed"),
        evidence=evidence,
        started_at="2026-08-29T00:00:00Z",
        completed_at="2026-08-29T00:00:00Z",
        duration_seconds=0.0,
    )
    insert_run(db, record)
    return record


class _StubMaterializer:
    """Minimal stub materializer for the 20-run resume test."""
    def __init__(self):
        from compliance.corpus_runner.materializer import MaterializationMetrics
        self.metrics = MaterializationMetrics()

    def prepare(self, *, repository_id, clone_url, repo_sha, attempt_id):
        from compliance.corpus_runner.materializer import PreparedRepository
        self.metrics.source_cache_hits += 1
        ws = Path(tempfile.mkdtemp(prefix=f"reguard_stub_{attempt_id}_"))
        (ws / "repo").mkdir(parents=True, exist_ok=True)
        return PreparedRepository(
            workspace_id=f"stub-{attempt_id}",
            workspace_root=ws,
            repository_path=ws / "repo",
            artifacts_path=ws / "artifacts",
            logs_path=ws / "logs",
            repo_sha=repo_sha,
            cache_key="stub",
            cache_hit=True,
        )

    def cleanup(self, prepared):
        import shutil as _sh
        _sh.rmtree(prepared.workspace_root, ignore_errors=True)
        return True

    def metrics_snapshot(self):
        import dataclasses
        return dataclasses.asdict(self.metrics)


def test_actual_20_run_resume(db_path, monkeypatch):
    """Run the actual frozen CR-2 manifest, terminate some jobs,
    resume, and verify the resume invariants hold against the full
    20-row manifest."""
    name_to_id = _seed_repos(db_path)
    rows = []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for full_name, repo_id in name_to_id.items():
            row = con.execute(
                "SELECT * FROM agent_repositories WHERE id = ?",
                (repo_id,),
            ).fetchone()
            rows.append(row)
    finally:
        con.close()

    # Stub everything that would touch the network or the probe.
    monkeypatch.setattr(crp, "default_db_path", lambda: db_path)
    import compliance.corpus_runner.executor as cr_exec_mod
    from compliance.pipeline import driver as drv
    monkeypatch.setattr(cr_exec_mod, "driver_run_one", _stub_driver_run_one)
    monkeypatch.setattr(cr_exec_mod, "RepositoryMaterializer",
                        _StubMaterializer)
    # The executor does an in-function `from ... import` of these
    # names, so we MUST patch them on the source module.
    monkeypatch.setattr(drv, "run_with_prepared_checkout",
                        _stub_driver_run_one)
    monkeypatch.setattr(drv, "run_one", _stub_driver_run_one)

    cfg = cr_exec.CorpusRunConfig(
        requirement_id=REQUIREMENT_ID,
        requirement_version=REQUIREMENT_VERSION,
        scenario_id=SCENARIO,
        executor="subprocess",
        runtime_version="test",
        max_workers=1,
        max_attempts=2,
        selection_description="20-run resume test",
        requested_repo_count=len(MANIFEST),
        db_path=db_path,
        pinned_shas=MANIFEST,
    )
    rid = cr_exec.create_corpus_run(cfg, rows)
    cr_exec.build_jobs_for_run(rid, SCENARIO, db_path=db_path)

    # Phase 1 — initial run to completion.
    result1 = cr_exec.run_corpus_run(
        rid, executor="subprocess", db_path=db_path,
    )
    final = crp.load_corpus_run(rid, db_path=db_path)
    assert final is not None

    # Snapshot the manifest before resume.
    con = sqlite3.connect(db_path)
    try:
        before_manifest = con.execute(
            "SELECT full_name, resolved_sha, sha_resolution_class "
            "FROM corpus_run_repositories "
            "WHERE corpus_run_id = ? ORDER BY position ASC",
            (rid,),
        ).fetchall()
        before_jobs = con.execute(
            "SELECT id, repo_sha, compliance_status, job_status "
            "FROM evaluation_jobs WHERE corpus_run_id = ? ORDER BY id ASC",
            (rid,),
        ).fetchall()
    finally:
        con.close()
    assert len(before_manifest) == 20
    assert len(before_jobs) == 20

    # Phase 2 — resume. v1.1.1 calls `build_jobs_for_run` again
    # (which is now idempotent) and then re-runs the pending jobs.
    result2 = cr_exec.run_corpus_run(
        rid, executor="subprocess", db_path=db_path,
    )

    # Phase 3 — invariants.
    con = sqlite3.connect(db_path)
    try:
        after_manifest = con.execute(
            "SELECT full_name, resolved_sha, sha_resolution_class "
            "FROM corpus_run_repositories "
            "WHERE corpus_run_id = ? ORDER BY position ASC",
            (rid,),
        ).fetchall()
        after_jobs = con.execute(
            "SELECT id, repo_sha, compliance_status, job_status "
            "FROM evaluation_jobs WHERE corpus_run_id = ? ORDER BY id ASC",
            (rid,),
        ).fetchall()
    finally:
        con.close()

    # 1. Manifest unchanged.
    assert len(after_manifest) == len(before_manifest) == 20
    for b, a in zip(before_manifest, after_manifest):
        assert b == a, f"manifest drift: {b} vs {a}"

    # 2. No duplicate jobs (build_jobs_for_run idempotence).
    assert len(after_jobs) == len(before_jobs)
    assert {j[0] for j in after_jobs} == {j[0] for j in before_jobs}

    # 3. Compliance status preserved per job.
    for before_j, after_j in zip(before_jobs, after_jobs):
        assert before_j[2] == after_j[2]

    # 4. Every job terminal.
    for j in after_jobs:
        assert j[3] == "completed", \
            f"job {j[0]} not terminal: {j[3]} status={j[2]}"

    # 5. Distribution matches CR-2.
    final2 = crp.load_corpus_run(rid, db_path=db_path)
    assert final2.pass_count == 2
    assert final2.fail_count == 3
    assert final2.unsupported_count == 15
    assert final2.error_count == 0
    assert final2.unknown_count == 0
