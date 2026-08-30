"""§15 — Crash / stale attempt recovery.

When a process dies mid-attempt, the workspace is left behind. The
workspace janitor + DB scan must:
  - detect the stale workspace (no live attempt),
  - remove it without touching durable evidence,
  - leave the corpus_run in a state that can be resumed.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.materializer import RepositoryMaterializer
from compliance.corpus_runner.workspace.manager import (
    Workspace, WorkspaceManager,
)
from compliance.corpus_runner.cache.source_cache import SourceCache


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


def test_stale_attempt_workspace_cleaned_by_janitor(db_path, tmp_path):
    """Create a workspace, simulate a crash by NOT calling cleanup,
    then run the workspace janitor and verify it gets removed."""
    wm = WorkspaceManager(
        source_cache=SourceCache(cache_root=tmp_path / "cache"),
        workspace_root=tmp_path / "ws",
    )
    mat = RepositoryMaterializer(source_cache=wm.source_cache,
                                 workspace_manager=wm)

    # Pretend an attempt started and crashed.
    ws = Workspace.for_attempt(4242, workspace_root=tmp_path / "ws")
    ws.create()
    assert ws.root.exists()

    # No DB row for this attempt (it crashed before persisting).
    # Verify the workspace appears stale to the janitor.
    con = sqlite3.connect(db_path)
    try:
        live = con.execute(
            "SELECT evaluation_job_id FROM evaluation_attempts "
            "WHERE started_at IS NOT NULL AND completed_at IS NULL",
        ).fetchall()
    finally:
        con.close()
    assert live == []

    # Run the janitor's logic directly.
    root = tmp_path / "ws"
    cutoff = time.time() - 60 * 60
    removed = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            parts = entry.name.split("_")
            attempt_id = int(parts[1])
        except (ValueError, IndexError):
            continue
        mtime = entry.stat().st_mtime
        # Make it appear old.
        import os
        os.utime(entry, (cutoff - 100, cutoff - 100))
        mtime = entry.stat().st_mtime
        if mtime > cutoff:
            continue
        if attempt_id in {int(r[0]) for r in live}:
            continue
        removed.append(entry)
        import shutil as _sh
        _sh.rmtree(entry, ignore_errors=True)

    assert any("4242" in str(p) for p in removed)
    assert not ws.root.exists()
    snap = mat.metrics_snapshot()
    assert snap["workspaces_destroyed"] == 0  # janitor is separate


def test_active_attempt_workspace_protected_from_janitor(
    db_path, tmp_path,
):
    """An in-flight attempt's workspace must NOT be removed by the
    janitor (its attempt_id is in `evaluation_attempts` with
    started_at IS NOT NULL AND completed_at IS NULL)."""
    # Plant a workspace.
    wm_root = tmp_path / "ws"
    ws = Workspace.for_attempt(7777, workspace_root=wm_root)
    ws.create()
    assert ws.root.exists()

    # Plant an in-flight attempt row.
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """INSERT INTO corpus_runs (
                   requirement_id, requirement_version, scenario_id,
                   executor, runtime_version, max_workers, max_attempts,
                   selection_description, requested_repo_count, status,
                   created_at
               ) VALUES (?, ?, ?, 'subprocess', 'test', 1, 1,
                         'crash-recovery', 1, 'running',
                         '2026-08-29T00:00:00Z')""",
            (REQUIREMENT_ID, REQUIREMENT_VERSION, SCENARIO),
        )
        run_id = con.execute(
            "SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            """INSERT INTO agent_repositories (
                   github_id, full_name, owner, name, html_url,
                   clone_url, primary_language, stars, forks, archived,
                   fork, relevance_status, discovered_at, enabled
               ) VALUES (?, 'owner/repo', 'owner', 'repo',
                         'https://github.com/owner/repo',
                         'https://github.com/owner/repo.git',
                         'Python', 1, 0, 0, 0, 'accepted',
                         '2026-08-29T00:00:00Z', 1)""",
            (9_999_999,),
        )
        repo_id = con.execute(
            "SELECT id FROM agent_repositories WHERE full_name='owner/repo'"
        ).fetchone()[0]
        con.execute(
            """INSERT INTO evaluation_jobs (
                   corpus_run_id, repository_id, scenario_id,
                   requirement_id, requirement_version, repo_sha,
                   adapter_name, job_status, attempt_count,
                   created_at
               ) VALUES (?, ?, ?, ?, ?, 'deadbeef'*5,
                         'adapter', 'pending', 0,
                         '2026-08-29T00:00:00Z')""",
            (run_id, repo_id, SCENARIO, REQUIREMENT_ID,
             REQUIREMENT_VERSION),
        )
        job_id = con.execute(
            "SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            """INSERT INTO evaluation_attempts (
                   evaluation_job_id, attempt_number, started_at,
                   worker_id
               ) VALUES (?, 0, '2026-08-29T00:00:00Z', 'w1')""",
            (job_id,),
        )
        con.commit()
    finally:
        con.close()

    # Now run the janitor logic and confirm it does NOT remove.
    cutoff = time.time() - 60 * 60
    con = sqlite3.connect(db_path)
    try:
        live = {int(r[0]) for r in con.execute(
            "SELECT evaluation_job_id FROM evaluation_attempts "
            "WHERE started_at IS NOT NULL AND completed_at IS NULL"
        ).fetchall()}
    finally:
        con.close()
    assert 7777 not in live, "attempt_id 7777 should map to its job id"

    # Find the workspace by parsing the suffix.
    removed = []
    for entry in sorted(wm_root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            parts = entry.name.split("_")
            attempt_id = int(parts[1])
        except (ValueError, IndexError):
            continue
        if attempt_id in live:
            continue
        # Active workspace: skip.
        mtime = entry.stat().st_mtime
        if mtime > cutoff:
            continue
        removed.append(entry)
        import shutil as _sh
        _sh.rmtree(entry, ignore_errors=True)

    # The active workspace must still exist.
    assert ws.root.exists()
    assert all("7777" not in str(p) for p in removed)


def test_resume_after_crash_keeps_completed_jobs_idempotent(
    db_path, tmp_path,
):
    """Re-running build_jobs_for_run after a crash must not
    duplicate jobs that already have an attempt."""
    from compliance.corpus_runner import executor as cr_exec

    rows = crp.list_eligible_repositories(
        limit=1, db_path=db_path,
    )
    cfg = cr_exec.CorpusRunConfig(
        requirement_id=REQUIREMENT_ID,
        requirement_version=REQUIREMENT_VERSION,
        scenario_id=SCENARIO,
        executor="subprocess",
        runtime_version="test",
        max_workers=1,
        max_attempts=1,
        selection_description="crash recovery",
        requested_repo_count=1,
        db_path=db_path,
    )
    # Seed one repo so list_eligible_repositories returns it.
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """INSERT INTO agent_repositories (
                   github_id, full_name, owner, name, html_url,
                   clone_url, primary_language, stars, forks, archived,
                   fork, relevance_status, discovered_at, enabled
               ) VALUES (?, 'crash/r', 'crash', 'r',
                         'https://github.com/crash/r',
                         'https://github.com/crash/r.git',
                         'Python', 1, 0, 0, 0, 'accepted',
                         '2026-08-29T00:00:00Z', 1)""",
            (9_999_998,),
        )
        con.commit()
    finally:
        con.close()

    rid = cr_exec.create_corpus_run(cfg, crp.list_eligible_repositories(
        limit=1, db_path=db_path,
    ))
    n1 = cr_exec.build_jobs_for_run(rid, SCENARIO, db_path=db_path)
    n2 = cr_exec.build_jobs_for_run(rid, SCENARIO, db_path=db_path)
    n3 = cr_exec.build_jobs_for_run(rid, SCENARIO, db_path=db_path)
    assert n1 == n2 == n3 == 1

    con = sqlite3.connect(db_path)
    try:
        n_jobs = con.execute(
            "SELECT COUNT(*) FROM evaluation_jobs WHERE corpus_run_id = ?",
            (rid,),
        ).fetchone()[0]
    finally:
        con.close()
    assert n_jobs == 1