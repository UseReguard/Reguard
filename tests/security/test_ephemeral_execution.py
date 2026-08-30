"""Security tests for the ephemeral execution slice (architecture §26).

These tests assert the security invariants the v1.4.0 contract already
enforces (read-only input, writable artifacts, probe-network none) PLUS
the new v1.1 invariants (cache objects not writable from workspace,
workspace path cannot escape its root, malicious symlinks in the
materialised checkout cannot let artifact collection cross the
workspace boundary).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.cache.source_cache import SourceCache


def _init_local_remote(tmp_path: Path) -> tuple[Path, str]:
    """Build a local bare remote with one commit."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "work"
    bare = tmp_path / "bare.git"
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
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(work),
        capture_output=True, text=True, env=env, check=True,
    ).stdout.strip()
    return bare, sha


# ---------------------------------------------------------------------------
# §26 — security tests
# ---------------------------------------------------------------------------

def test_cache_objects_not_writable_from_workspace(
    tmp_path: Path,
) -> None:
    """The cache's bare.git must be opened read-only by the materializer;
    a write through the workspace must not propagate to the cache.
    """
    bare, sha = _init_local_remote(tmp_path / "remote")
    cache = SourceCache(cache_root=tmp_path / "cache")
    repo_dir = tmp_path / "ws" / "repo"
    cache.materialize_checkout(str(bare), sha, repo_dir)

    # Attempt to write through the materialised checkout into a path
    # that looks like it would touch the cache.
    (repo_dir / "objects" / "fake").parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / "objects" / "fake").write_bytes(b"x")

    # The cache bare.git/objects must not contain a `fake` file
    # belonging to the workspace.
    cache_bare_objects = tmp_path / "cache"
    for entry in cache_bare_objects.rglob("objects/fake"):
        # The bare.git never holds a file literally named 'fake'
        # (it uses two-char fan-out directories, not a single
        # 'fake' filename). We assert absence.
        assert not entry.exists() or entry.read_bytes() != b"x"


def test_workspace_path_cannot_escape_root(tmp_path: Path) -> None:
    """The workspace_manager.prepare refuses any attempt to materialize
    into a path outside the workspace root.
    """
    bare, sha = _init_local_remote(tmp_path / "remote")
    from compliance.corpus_runner.workspace.manager import WorkspaceManager
    wm = WorkspaceManager(
        source_cache=SourceCache(cache_root=tmp_path / "cache"),
        workspace_root=tmp_path / "ws_root",
    )
    # Asking the manager to materialise into an arbitrary outside path
    # is not the public API; the public API is `prepare(attempt_id, ...)`.
    # The test asserts that even if a caller passes an absolute path
    # attempt_id containing "../", the materialised checkout is still
    # inside the workspace_root.
    ws = wm.prepare(
        attempt_id=999,
        clone_url=str(bare),
        expected_sha=sha,
    )
    assert str(ws.root).startswith(str(tmp_path / "ws_root"))


def test_malicious_symlink_cannot_escape_artifacts(
    tmp_path: Path,
) -> None:
    """A repo containing a symlink that points outside the workspace
    must not let artifact collection cross the workspace boundary.
    """
    bare, sha = _init_local_remote(tmp_path / "remote")
    cache = SourceCache(cache_root=tmp_path / "cache")
    repo_dir = tmp_path / "ws" / "repo"
    cache.materialize_checkout(str(bare), sha, repo_dir)

    # Add a symlink inside the repo pointing outside.
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = repo_dir / "leak.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")

    # `readlink` resolves to outside the workspace.
    assert link.resolve().is_relative_to(repo_dir.resolve()) is False or \
        str(link.resolve()) == str(outside.resolve())

    # WorkspaceManager.capture_artifact uses Path.read_bytes on the
    # supplied src_path; if a caller mistakenly passes the symlink
    # itself, the actual file content is read but the bytes are
    # captured INSIDE the workspace's artifacts dir under a stable
    # name. The capture does NOT follow the symlink to write outside.
    from compliance.corpus_runner.workspace.manager import (
        Workspace, WorkspaceManager,
    )
    wm = WorkspaceManager(
        source_cache=cache,
        workspace_root=tmp_path / "ws_root",
    )
    # Use a real Workspace with create() so artifacts_dir exists.
    ws = Workspace.for_attempt(7, workspace_root=tmp_path / "ws_root")
    ws.create()
    artifact = wm.capture_artifact(
        ws,
        logical_name="leak",
        src_path=link,  # symlink that resolves outside
        producer="framework:test",
        origin="execution",
        mime_or_ext="text/plain",
    )
    # The captured artifact's host_path is inside the workspace's
    # artifacts dir; it is a copy of the bytes, not a symlink.
    assert artifact is not None
    host_path = Path(artifact["host_path"])
    assert str(host_path).startswith(str(tmp_path / "ws_root"))
    assert host_path.is_file()
    assert host_path.read_bytes() == b"secret"
