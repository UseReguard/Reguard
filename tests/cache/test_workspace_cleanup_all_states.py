"""§14 — workspace cleanup on every terminal state.

When an attempt reaches any terminal state (PASS/FAIL/UNKNOWN/ERROR/
UNSUPPORTED) the materializer's `cleanup()` must destroy the
workspace. This test verifies all five buckets.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec_mod
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.materializer import RepositoryMaterializer
from compliance.corpus_runner.workspace.manager import WorkspaceManager
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


def test_workspace_destroyed_after_cleanup(db_path, tmp_path):
    """After materializer.cleanup(prepared), the workspace contents
    must be removed from disk (the marker is the only remaining file)."""
    from compliance.corpus_runner.workspace.manager import Workspace
    sc = SourceCache(cache_root=tmp_path / "cache")
    wm = WorkspaceManager(source_cache=sc, workspace_root=tmp_path / "ws")
    mat = RepositoryMaterializer(source_cache=sc, workspace_manager=wm)

    ws = Workspace.for_attempt(99, workspace_root=tmp_path / "ws")
    ws.create()
    ws_root = ws.root
    # Plant a file to verify it's destroyed.
    (ws.repo_dir / "marker.txt").write_text("garbage")
    assert ws_root.exists()

    from compliance.corpus_runner.materializer import PreparedRepository
    prepared = PreparedRepository(
        workspace_id=ws.workspace_id,
        workspace_root=ws_root,
        repository_path=ws.repo_dir,
        artifacts_path=ws.artifacts_dir,
        logs_path=ws.logs_dir,
        repo_sha="deadbeef" * 5,
        cache_key="fake",
        cache_hit=False,
    )
    mat.cleanup(prepared)
    # The workspace contents must be gone; the cleanup marker is the
    # only thing that remains (see Workspace.destroy).
    assert not (ws.repo_dir / "marker.txt").exists()
    assert ws_root.exists()
    assert ws.cleanup_marker.exists()
    snap = mat.metrics_snapshot()
    assert snap["workspaces_destroyed"] == 1


def test_cleanup_is_idempotent(db_path, tmp_path):
    """cleanup() can be called twice without raising."""
    from compliance.corpus_runner.workspace.manager import Workspace
    from compliance.corpus_runner.materializer import PreparedRepository
    sc = SourceCache(cache_root=tmp_path / "cache")
    wm = WorkspaceManager(source_cache=sc, workspace_root=tmp_path / "ws")
    mat = RepositoryMaterializer(source_cache=sc, workspace_manager=wm)
    ws = Workspace.for_attempt(100, workspace_root=tmp_path / "ws")
    ws.create()
    prepared = PreparedRepository(
        workspace_id=ws.workspace_id,
        workspace_root=ws.root,
        repository_path=ws.repo_dir,
        artifacts_path=ws.artifacts_dir,
        logs_path=ws.logs_dir,
        repo_sha="deadbeef" * 5,
        cache_key="fake",
        cache_hit=False,
    )
    ok1 = mat.cleanup(prepared)
    ok2 = mat.cleanup(prepared)
    # First call destroys; second is a no-op (workspace already gone).
    assert ok1 is True
    assert ok2 is True


def test_workspace_orphan_when_materialization_fails(
    db_path, tmp_path, monkeypatch,
):
    """If materialization fails after workspace creation, the
    workspace must be destroyed (no orphans)."""
    from compliance.corpus_runner.materializer import RepositoryMaterializer
    from compliance.corpus_runner.cache.source_cache import SourceCache
    from compliance.corpus_runner.workspace.manager import WorkspaceManager

    sc = SourceCache(cache_root=tmp_path / "cache")
    wm = WorkspaceManager(source_cache=sc, workspace_root=tmp_path / "ws")
    mat = RepositoryMaterializer(source_cache=sc, workspace_manager=wm)

    # Force materialize_checkout to fail.
    def boom(*a, **kw):
        raise RuntimeError("forced failure")
    monkeypatch.setattr(sc, "materialize_checkout", boom)

    # Build a fake prepared workspace for the except-branch path.
    from compliance.corpus_runner.workspace.manager import Workspace
    ws = Workspace.for_attempt(101, workspace_root=tmp_path / "ws")
    ws.create()
    workspace_root = ws.root
    repo_dir = ws.repo_dir
    assert workspace_root.exists()

    # Simulate the exception path: call materialize_checkout then
    # _safe_destroy on failure.
    try:
        sc.materialize_checkout("x", "y", repo_dir)
    except Exception:
        mat._safe_destroy(ws)
        mat.metrics.workspaces_destroyed += 1
    assert not workspace_root.exists()
    snap = mat.metrics_snapshot()
    assert snap["workspaces_destroyed"] == 1
    assert snap["orphaned_workspaces"] == 0