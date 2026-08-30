"""v1.1.1 tests for cache-loss, malicious-mutation, concurrent materialization,
GC race, and materializer integration.

These tests exercise the source cache + materializer at a higher level
than `test_source_cache.py`. They use a local bare repository as the
"remote" so no network I/O is required.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.cache.source_cache import (
    SourceCache,
    cache_key_for_url,
)
from compliance.corpus_runner.materializer import (
    PreparedRepository,
    RepositoryMaterializer,
    gc_with_lock,
)
from compliance.corpus_runner.workspace.manager import WorkspaceManager


def _init_local_remote(parent: Path) -> tuple[Path, str, str]:
    """Build a local bare remote with two commits; return
    (bare_path, sha_v1, sha_v2)."""
    parent.mkdir(parents=True, exist_ok=True)
    work = parent / "work"
    bare = parent / "bare.git"
    work.mkdir()
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", "--initial-branch=main",
                    str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(bare), str(work)],
                   check=True, capture_output=True)
    env = {
        "GIT_AUTHOR_NAME": "x", "GIT_AUTHOR_EMAIL": "x@y.z",
        "GIT_COMMITTER_NAME": "x", "GIT_COMMITTER_EMAIL": "x@y.z",
        "PATH": os.environ["PATH"],
    }
    (work / "a.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "a"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    sha_v1 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(work),
        capture_output=True, text=True, env=env, check=True,
    ).stdout.strip()

    (work / "b.txt").write_text("world\n", encoding="utf-8")
    subprocess.run(["git", "add", "b.txt"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "b"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    sha_v2 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(work),
        capture_output=True, text=True, env=env, check=True,
    ).stdout.strip()
    return bare, sha_v1, sha_v2


# ---------------------------------------------------------------------------
# §10 — Cache loss / refetch
# ---------------------------------------------------------------------------

def test_cache_loss_refetches_with_same_semantics(tmp_path: Path) -> None:
    """Deleting the cache and re-materialising must produce the same
    file tree (and therefore the same compliance semantics)."""
    bare, sha, _ = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )
    p1 = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=1,
    )
    content_before = (p1.repository_path / "a.txt").read_text(encoding="utf-8")
    mat.cleanup(p1)

    # Delete the entire cache.
    shutil.rmtree(tmp_path / "cache")

    # Re-materialise: must succeed and produce the same content.
    p2 = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=2,
    )
    content_after = (p2.repository_path / "a.txt").read_text(encoding="utf-8")
    mat.cleanup(p2)
    assert content_before == content_after


# ---------------------------------------------------------------------------
# §11 — Malicious cache-mutation test
# ---------------------------------------------------------------------------

def test_malicious_cache_mutation_blocked(tmp_path: Path) -> None:
    """Operations from inside the workspace must not be able to mutate
    the shared cache. The cache's bare.git has no symlink path from
    the workspace."""
    bare, sha, _ = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )
    prepared = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=3,
    )

    # Snapshot the cache's bare.git HEAD before the malicious attempt.
    cache_key = cache_key_for_url(str(bare))
    cache_head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path / "cache" / cache_key / "bare.git"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    cache_files_before = set(
        str(p.relative_to(tmp_path / "cache" / cache_key / "bare.git"))
        for p in (tmp_path / "cache" / cache_key / "bare.git").rglob("*")
        if p.is_file()
    )

    # Try common malicious operations from inside the workspace.
    # All must fail or have no effect on the cache.
    operations = [
        ["git", "update-ref", "refs/heads/main", "deadbeef" * 5],
        ["git", "gc", "--prune=now"],
        ["git", "fetch", "origin", "+refs/heads/*:refs/heads/*"],
        ["git", "push", str(bare), "main"],
        # Write a fake `.git/HEAD` inside the workspace and try to use
        # it to reach into the cache.
    ]
    for op in operations:
        res = subprocess.run(
            op, cwd=str(prepared.repository_path),
            capture_output=True, text=True, timeout=30,
        )
        # We don't care if the operation succeeds or fails locally —
        # we care that the cache state is unchanged.

    # Verify the cache is unchanged.
    cache_head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path / "cache" / cache_key / "bare.git"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    cache_files_after = set(
        str(p.relative_to(tmp_path / "cache" / cache_key / "bare.git"))
        for p in (tmp_path / "cache" / cache_key / "bare.git").rglob("*")
        if p.is_file()
    )

    assert cache_head_before == cache_head_after, (
        f"cache HEAD changed: {cache_head_before} → {cache_head_after}"
    )
    assert cache_files_before == cache_files_after, (
        f"cache file set changed under malicious operations"
    )

    # The workspace must NOT contain any path that points back into
    # the cache's bare.git directory.
    for p in prepared.repository_path.rglob("*"):
        if p.is_symlink():
            target = str(p.resolve())
            assert str(tmp_path / "cache") not in target, (
                f"workspace contains a symlink into the cache: {p}"
            )

    mat.cleanup(prepared)


# ---------------------------------------------------------------------------
# §12 — Concurrent materialization
# ---------------------------------------------------------------------------

def test_concurrent_materialization_same_repo_same_sha(tmp_path: Path) -> None:
    """Two workers materialising the same repo + SHA produce two
    independent workspaces and do not corrupt the cache."""
    bare, sha, _ = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )

    results: list[PreparedRepository] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker(attempt_id: int) -> None:
        try:
            barrier.wait(timeout=30)
            p = mat.prepare(
                repository_id=1, clone_url=str(bare),
                repo_sha=sha, attempt_id=attempt_id,
            )
            results.append(p)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=(10,))
    t2 = threading.Thread(target=worker, args=(11,))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert errors == [], errors
    assert len(results) == 2
    # Both must have the same SHA but different workspace paths.
    assert all(p.repo_sha == sha for p in results)
    paths = {p.repository_path for p in results}
    assert len(paths) == 2
    for p in results:
        assert (p.repository_path / "a.txt").exists()
        mat.cleanup(p)


def test_concurrent_materialization_same_repo_different_sha(tmp_path: Path) -> None:
    """Two workers materialising different SHAs of the same repo both
    succeed and produce independent snapshots."""
    bare, sha_v1, sha_v2 = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )

    results: list[PreparedRepository] = []
    errors: list[Exception] = []

    def worker(attempt_id: int, sha: str) -> None:
        try:
            p = mat.prepare(
                repository_id=1, clone_url=str(bare),
                repo_sha=sha, attempt_id=attempt_id,
            )
            results.append(p)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=(20, sha_v1))
    t2 = threading.Thread(target=worker, args=(21, sha_v2))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert errors == [], errors
    assert {r.repo_sha for r in results} == {sha_v1, sha_v2}
    # Workspace A has a.txt only; B has both files.
    for p in results:
        assert (p.repository_path / "a.txt").exists()
        if p.repo_sha == sha_v2:
            assert (p.repository_path / "b.txt").exists()
        mat.cleanup(p)


# ---------------------------------------------------------------------------
# §13 — GC race test
# ---------------------------------------------------------------------------

def test_gc_does_not_evict_active_materializer_entry(tmp_path: Path) -> None:
    """While a materializer holds the per-cache-key lock, GC must
    skip that entry. After the materializer releases the lock, GC
    may evict."""
    bare, sha, _ = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )

    # Prime the cache.
    p = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=30,
    )
    mat.cleanup(p)

    # Now hold the lock manually and run GC; it must NOT evict.
    cache_key = cache_key_for_url(str(bare))
    lock_path = tmp_path / "cache" / (cache_key + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fh:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            plan = gc_with_lock(mat, max_bytes=0)
            assert plan["entries_considered"] >= 1
            assert plan["entries_protected"] >= 1
            assert plan["entries_evicted"] == 0
            # Cache entry must still be on disk.
            assert (tmp_path / "cache" / cache_key / "bare.git").exists()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    # Now run GC without holding the lock; it may evict.
    plan2 = gc_with_lock(mat, max_bytes=0, dry_run=True)
    # `dry_run=True` keeps the entry on disk but reports the plan.
    assert plan2["entries_considered"] >= 1
    assert plan2["bytes_reclaimable"] >= 0


# ---------------------------------------------------------------------------
# §18 — Metrics
# ---------------------------------------------------------------------------

def test_materialization_metrics_recorded(tmp_path: Path) -> None:
    """The materializer records hits/misses/fetches/workspaces
    created+destroyed on its `MaterializationMetrics`."""
    bare, sha, _ = _init_local_remote(tmp_path / "remote")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc,
            workspace_root=tmp_path / "ws",
        ),
    )
    # First prepare: cache miss + fetch + workspace created.
    p1 = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=40,
    )
    mat.cleanup(p1)
    metrics = mat.metrics_snapshot()
    assert metrics["source_cache_misses"] == 1
    assert metrics["source_cache_hits"] == 0
    assert metrics["source_cache_fetches"] == 1
    assert metrics["workspaces_created"] == 1
    assert metrics["workspaces_destroyed"] == 1

    # Second prepare: cache hit + workspace created.
    p2 = mat.prepare(
        repository_id=1, clone_url=str(bare), repo_sha=sha, attempt_id=41,
    )
    mat.cleanup(p2)
    metrics2 = mat.metrics_snapshot()
    assert metrics2["source_cache_hits"] == 1
    assert metrics2["source_cache_misses"] == 1
    assert metrics2["workspaces_created"] == 2
    assert metrics2["workspaces_destroyed"] == 2
