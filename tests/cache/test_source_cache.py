"""Source cache tests (architecture §25).

These tests exercise the bare-git source cache without performing
real network I/O against GitHub. The fixture uses a local bare
git repository as the "remote" and a small set of synthetic commits.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.cache.source_cache import (
    SourceCache,
    cache_key_for_url,
    sha256_bytes,
    sha256_path,
)


# ---------------------------------------------------------------------------
# Local "remote" fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def local_remote(tmp_path: Path) -> Path:
    """Build a local bare repository with two commits at known SHAs."""
    work = tmp_path / "work"
    bare = tmp_path / "bare.git"
    work.mkdir()
    bare.mkdir()
    # Init bare first, then clone to work, commit, push.
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

    # Second commit on a new SHA.
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


def _head_sha(path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(path),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# §25 — source-cache tests
# ---------------------------------------------------------------------------

def test_cache_key_is_stable() -> None:
    a = cache_key_for_url("https://github.com/foo/bar.git")
    b = cache_key_for_url("https://github.com/foo/bar.git")
    c = cache_key_for_url("https://github.com/foo/baz.git")
    assert a == b
    assert a != c
    assert len(a) == 32


def test_cache_miss_fetches_and_materializes(tmp_path: Path, local_remote) -> None:
    bare, sha_v1, _sha_v2 = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    ws_dir = tmp_path / "ws" / "repo"
    cache.materialize_checkout(str(bare), sha_v1, ws_dir)
    # v1.1.1: archive-only materialization. The .reguard-materialized
    # marker records the exact SHA; there is no `.git/` shim.
    marker = ws_dir / ".reguard-materialized"
    assert marker.exists()
    assert f"repo_sha={sha_v1}" in marker.read_text(encoding="utf-8")
    # File from the first commit is present.
    assert (ws_dir / "a.txt").read_text(encoding="utf-8") == "hello\n"


def test_cache_hit_avoids_reclone(
    tmp_path: Path, local_remote, monkeypatch,
) -> None:
    bare, sha_v1, _ = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "ws1" / "repo")

    # Patch `git fetch` to record invocation; we want to verify it is
    # NOT invoked when materialising a SHA already present in the cache.
    fetch_calls: list[list[str]] = []
    clone_calls: list[list[str]] = []
    real_run = subprocess.run

    def spy_run(args, **kwargs):
        if isinstance(args, (list, tuple)) and len(args) >= 2 \
                and args[0] == "git":
            if "fetch" in args:
                fetch_calls.append(list(args))
            if "clone" in args:
                clone_calls.append(list(args))
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "ws2" / "repo")
    marker = tmp_path / "ws2" / "repo" / ".reguard-materialized"
    assert marker.exists()
    assert f"repo_sha={sha_v1}" in marker.read_text(encoding="utf-8")
    assert fetch_calls == [], f"unexpected git fetch calls: {fetch_calls}"
    assert clone_calls == [], f"unexpected git clone calls: {clone_calls}"


def test_different_sha_fetches_missing_objects(
    tmp_path: Path, local_remote,
) -> None:
    bare, sha_v1, sha_v2 = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "ws1" / "repo")
    cache.materialize_checkout(str(bare), sha_v2, tmp_path / "ws2" / "repo")
    assert (tmp_path / "ws1" / "repo" / "a.txt").exists()
    assert not (tmp_path / "ws1" / "repo" / "b.txt").exists()
    assert (tmp_path / "ws2" / "repo" / "a.txt").exists()
    assert (tmp_path / "ws2" / "repo" / "b.txt").exists()
    # Each workspace records its own SHA in the marker.
    m1 = (tmp_path / "ws1" / "repo" / ".reguard-materialized").read_text(
        encoding="utf-8")
    m2 = (tmp_path / "ws2" / "repo" / ".reguard-materialized").read_text(
        encoding="utf-8")
    assert sha_v1 in m1
    assert sha_v2 in m2


def test_workspace_isolation(tmp_path: Path, local_remote) -> None:
    bare, sha_v1, _ = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "A" / "repo")
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "B" / "repo")

    # Mutate A; B must not see the change.
    (tmp_path / "A" / "repo" / "scratch.txt").write_text(
        "A-only", encoding="utf-8",
    )
    assert not (tmp_path / "B" / "repo" / "scratch.txt").exists()

    # Cache bare.git must not see the change either.
    assert not (tmp_path / "cache" /
                cache_key_for_url(str(bare)) /
                "bare.git" / "scratch.txt").exists()

    # v1.1.1: there must be NO .git shim pointing back to the cache.
    assert not (tmp_path / "A" / "repo" / ".git").exists()
    assert not (tmp_path / "B" / "repo" / ".git").exists()


def test_terminal_attempt_destroys_workspace(
    tmp_path: Path, local_remote,
) -> None:
    bare, sha_v1, _ = local_remote
    from compliance.corpus_runner.workspace.manager import Workspace, WorkspaceManager
    wm = WorkspaceManager(
        source_cache=SourceCache(cache_root=tmp_path / "cache"),
        workspace_root=tmp_path / "ws_root",
    )
    ws = wm.prepare(
        attempt_id=1,
        clone_url=str(bare),
        expected_sha=sha_v1,
    )
    assert (ws.repo_dir / "a.txt").exists()
    # Cleanup destroys the workspace but keeps the cache.
    ok = wm.cleanup(ws)
    assert ok
    assert not ws.repo_dir.exists()
    cache_key = cache_key_for_url(str(bare))
    assert (tmp_path / "cache" / cache_key / "bare.git").exists()


def test_cache_loss_refetches(tmp_path: Path, local_remote) -> None:
    bare, sha_v1, _ = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "ws1" / "repo")
    # Wipe the cache.
    shutil.rmtree(tmp_path / "cache")
    # Re-materialise against the same SHA: must succeed and produce
    # the same checkout contents.
    cache.materialize_checkout(str(bare), sha_v1, tmp_path / "ws2" / "repo")
    marker = tmp_path / "ws2" / "repo" / ".reguard-materialized"
    assert marker.exists()
    assert f"repo_sha={sha_v1}" in marker.read_text(encoding="utf-8")
    assert (tmp_path / "ws2" / "repo" / "a.txt").read_text(
        encoding="utf-8") == "hello\n"


def test_no_git_shim_after_materialization(tmp_path: Path, local_remote) -> None:
    """v1.1.1 security invariant: the materialized workspace must NOT
    contain any `.git/` shim that points back into the cache's
    `objects/` or `packed-refs`. The only metadata file written into
    the workspace is `.reguard-materialized`."""
    bare, sha_v1, _ = local_remote
    cache = SourceCache(cache_root=tmp_path / "cache")
    ws = tmp_path / "ws" / "repo"
    cache.materialize_checkout(str(bare), sha_v1, ws)
    entries = sorted(p.name for p in ws.iterdir())
    # Must contain the marker + the repo file but NO .git.
    assert ".reguard-materialized" in entries
    assert "a.txt" in entries
    assert ".git" not in entries


def test_sha256_helpers_are_correct(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"abc")
    assert sha256_path(p) == sha256_bytes(b"abc")
