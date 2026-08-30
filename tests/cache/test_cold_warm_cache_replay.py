"""Cold-cache and warm-cache materialization replay.

Verifies that the materializer produces the canonical metrics:

    Cold-cache replay (5 distinct repos):
        source_cache_misses == 5
        source_cache_hits   == 0
        source_cache_fetches == 5
        workspaces_created   == 5
        workspaces_destroyed == 5
        orphaned_workspaces  == 0

    Warm-cache replay (same 5 repos, same SHAs):
        source_cache_misses == 0
        source_cache_hits   == 5
        source_cache_fetches == 0
        workspaces_created   == 5
        workspaces_destroyed == 5
        orphaned_workspaces  == 0

Uses local bare remotes so no network I/O is required.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner.cache.source_cache import SourceCache
from compliance.corpus_runner.materializer import RepositoryMaterializer
from compliance.corpus_runner.workspace.manager import WorkspaceManager


def _init_local_remote(parent: Path, label: str) -> tuple[Path, str]:
    """Build a local bare remote with a single commit; return
    (bare_path, sha)."""
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
    (work / "README.md").write_text(f"# {label}\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", f"init {label}"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(work),
                   check=True, capture_output=True, env=env)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(work),
        capture_output=True, text=True, env=env, check=True,
    ).stdout.strip()
    return bare, sha


def test_cold_then_warm_5_repos(tmp_path: Path) -> None:
    """Cold-cache replay: 5 distinct repos, 5 misses, 5 fetches,
    5 workspaces created+destroyed, 0 orphans.

    Warm-cache replay: same 5 repos, same SHAs, 5 hits, 0 misses,
    5 workspaces created+destroyed, 0 orphans."""
    remote_root = tmp_path / "remote"
    repos: list[tuple[Path, str]] = []
    for i in range(5):
        bare, sha = _init_local_remote(remote_root / f"r{i}", f"r{i}")
        repos.append((bare, sha))

    cache_root = tmp_path / "cache"
    ws_root = tmp_path / "ws"
    sc = SourceCache(cache_root=cache_root)
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc, workspace_root=ws_root,
        ),
    )

    # === Cold-cache replay ===
    cold_prepared = []
    for i, (bare, sha) in enumerate(repos):
        p = mat.prepare(
            repository_id=i + 1, clone_url=str(bare), repo_sha=sha,
            attempt_id=100 + i,
        )
        cold_prepared.append(p)
    cold_snap = mat.metrics_snapshot()
    assert cold_snap["source_cache_misses"] == 5, cold_snap
    assert cold_snap["source_cache_hits"] == 0, cold_snap
    assert cold_snap["source_cache_fetches"] == 5, cold_snap
    assert cold_snap["workspaces_created"] == 5, cold_snap
    assert cold_snap["workspaces_destroyed"] == 0, cold_snap
    assert cold_snap["orphaned_workspaces"] == 0, cold_snap

    # Snapshot content BEFORE cleanup so we can compare to warm.
    # The `.reguard-materialized` marker carries a timestamp, so we
    # parse it and compare the structural fields (repo_sha, cache_key)
    # only — not the wall-clock `materialized_at`.
    cold_contents = []
    for p in cold_prepared:
        marker = (p.repository_path / ".reguard-materialized"
                  ).read_text(encoding="utf-8")
        kv = {}
        for line in marker.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k] = v
        cold_contents.append({
            "readme": (p.repository_path / "README.md").read_text(
                encoding="utf-8",
            ),
            "marker_repo_sha": kv.get("repo_sha", ""),
            "marker_cache_key": kv.get("cache_key", ""),
        })

    # Now destroy them.
    for p in cold_prepared:
        mat.cleanup(p)

    # === Warm-cache replay ===
    warm_prepared = []
    for i, (bare, sha) in enumerate(repos):
        p = mat.prepare(
            repository_id=i + 1, clone_url=str(bare), repo_sha=sha,
            attempt_id=200 + i,
        )
        warm_prepared.append(p)
    warm_snap = mat.metrics_snapshot()
    assert warm_snap["source_cache_misses"] == 5, warm_snap  # accumulated
    assert warm_snap["source_cache_hits"] == 5, warm_snap
    assert warm_snap["source_cache_fetches"] == 5, warm_snap  # no new fetch
    assert warm_snap["workspaces_created"] == 10, warm_snap  # +5 more
    assert warm_snap["workspaces_destroyed"] == 5, warm_snap
    assert warm_snap["orphaned_workspaces"] == 0, warm_snap

    # Compare cold vs warm content BEFORE destroying warm workspaces.
    for cold_content, warm_p in zip(cold_contents, warm_prepared):
        assert cold_content["readme"] == (
            warm_p.repository_path / "README.md"
        ).read_text(encoding="utf-8")
        warm_marker = (warm_p.repository_path / ".reguard-materialized"
                       ).read_text(encoding="utf-8")
        warm_kv = {}
        for line in warm_marker.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                warm_kv[k] = v
        assert cold_content["marker_repo_sha"] == warm_kv.get("repo_sha", "")
        assert cold_content["marker_cache_key"] == warm_kv.get("cache_key", "")

    # Destroy warm workspaces.
    for p in warm_prepared:
        mat.cleanup(p)
    final = mat.metrics_snapshot()
    assert final["workspaces_destroyed"] == 10
    assert final["workspaces_created"] == 10
    assert final["orphaned_workspaces"] == 0


def test_cache_hit_avoids_reclone_metrics(tmp_path: Path) -> None:
    """Per-repo metric: the second prepare against the same SHA must
    be a HIT, not a MISS + FETCH."""
    remote_root = tmp_path / "remote"
    bare, sha = _init_local_remote(remote_root / "r0", "r0")
    sc = SourceCache(cache_root=tmp_path / "cache")
    mat = RepositoryMaterializer(
        source_cache=sc,
        workspace_manager=WorkspaceManager(
            source_cache=sc, workspace_root=tmp_path / "ws",
        ),
    )
    p1 = mat.prepare(repository_id=1, clone_url=str(bare),
                     repo_sha=sha, attempt_id=1)
    p2 = mat.prepare(repository_id=1, clone_url=str(bare),
                     repo_sha=sha, attempt_id=2)
    snap = mat.metrics_snapshot()
    assert snap["source_cache_hits"] == 1
    assert snap["source_cache_misses"] == 1
    assert snap["source_cache_fetches"] == 1
    # Both workspaces were created.
    assert snap["workspaces_created"] == 2
    mat.cleanup(p1)
    mat.cleanup(p2)