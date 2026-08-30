"""RepositoryMaterializer — the single boundary that owns source-cache
fetch, exact-SHA materialization, and per-attempt workspace creation.

The driver pipeline consumes the resulting `PreparedRepository` and is
no longer responsible for clone/install/probe I/O. The materializer is
the ONLY place in the codebase that touches the source cache.

Contract:

    prepared = materializer.prepare(
        repository_id=...,
        clone_url=...,
        repo_sha=...,
        attempt_id=...,
    )

The prepared workspace contains:

    - an INDEPENDENT file snapshot of the requested SHA (no symlinks
      into the cache),
    - a `.reguard-materialized` marker recording the SHA,
    - a per-attempt workspace root that will be destroyed on cleanup.

Cache state is NOT part of the prepared object's contract. Two
invocations against the same SHA must produce equivalent prepared
workspaces even when one hits the cache and the other misses.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from compliance.corpus_runner.cache.source_cache import (
    SourceCache,
    cache_key_for_url,
)
from compliance.corpus_runner.workspace.manager import (
    Workspace,
    WorkspaceManager,
)

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PreparedRepository:
    workspace_id: str
    workspace_root: Path
    repository_path: Path
    artifacts_path: Path
    logs_path: Path
    repo_sha: str
    cache_key: str
    cache_hit: bool


@dataclasses.dataclass
class MaterializationMetrics:
    source_cache_hits: int = 0
    source_cache_misses: int = 0
    source_cache_fetches: int = 0
    source_cache_fetch_failures: int = 0
    workspaces_created: int = 0
    workspaces_destroyed: int = 0
    workspace_cleanup_failures: int = 0
    orphaned_workspaces: int = 0
    source_cache_bytes_before: int | None = None
    source_cache_bytes_after: int | None = None
    bytes_fetched: int | None = None
    materialization_duration_seconds: float = 0.0


class RepositoryMaterializer:
    """Owns source-cache fetch + per-attempt workspace materialization.

    The lock protocol is per-cache-key: a single `flock` covers the
    entire materialization sequence (fetch + cat-file verify + archive
    + extract). GC must use the same lock so that GC cannot delete an
    entry that is currently being materialized.

    The lock is released as soon as extraction completes. Execution
    does not hold the lock — the workspace contains an independent
    snapshot and does not need ongoing access to the cache.
    """

    def __init__(
        self,
        *,
        source_cache: SourceCache | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self.source_cache = source_cache or SourceCache()
        self.workspace_manager = workspace_manager or WorkspaceManager(
            source_cache=self.source_cache,
        )
        self.metrics = MaterializationMetrics()

    # ------------------------------------------------------------------
    # Materialization
    # ------------------------------------------------------------------

    def prepare(
        self,
        *,
        repository_id: int,
        clone_url: str,
        repo_sha: str,
        attempt_id: int,
    ) -> PreparedRepository:
        """Materialize a per-attempt workspace from the source cache.

        Sequence (each step self-synchronises against the per-cache-key
        `flock`, so the lock is released between steps; the workspace
        is the only thing that must be atomic):

          1. fetch (its own lock; serialised against other fetchers
             and against GC)
          2. verify SHA is reachable in the cache (its own cat-file)
          3. create the workspace (filesystem-local)
          4. archive + extract into the workspace (read-only against
             the cache; the workspace becomes an independent snapshot)

        Note: `fcntl.flock` is NOT reentrant across different file
        descriptors on Linux, so we cannot hold the materializer lock
        while calling into `source_cache.fetch()` (which takes its
        own lock on the same file). Each step takes the lock
        independently — they serialise correctly because all writers
        use the same lock file.
        """
        cache_key = cache_key_for_url(clone_url)
        layout = self.source_cache.layout(clone_url)
        t0 = time.monotonic()
        cache_hit = layout.exists

        self.metrics.source_cache_bytes_before = (
            self.metrics.source_cache_bytes_before
            if self.metrics.source_cache_bytes_before is not None
            else self.source_cache.size_bytes()
        )

        if cache_hit:
            # Fast path: cache exists. Verify SHA in-cache, do NOT
            # fetch again unless SHA is missing.
            if not self._sha_present_in_cache(layout, repo_sha):
                self._fetch_with_metrics(clone_url)
                if not self._sha_present_in_cache(layout, repo_sha):
                    raise RuntimeError(
                        f"SHA {repo_sha} not present in cache "
                        f"after fetch for {clone_url}"
                    )
            self.metrics.source_cache_hits += 1
        else:
            self.metrics.source_cache_misses += 1
            self._fetch_with_metrics(clone_url)

        # Create the per-attempt workspace. Workspace creation is
        # filesystem-local and self-synchronising against other
        # workers via unique attempt_id.
        ws = Workspace.for_attempt(
            attempt_id,
            workspace_root=self.workspace_manager.workspace_root,
        )
        ws.create()
        self.metrics.workspaces_created += 1
        try:
            # The archive+extract reads the cache; it does NOT modify
            # it, but it does need the cache to be in a stable state
            # so that the SHA is reachable for the duration of the
            # extract. We serialise against GC by acquiring the lock
            # around just the extract. `materialize_checkout` does its
            # own cat-file/archive/extract with the cache's own lock
            # so GC cannot evict underneath us.
            self.source_cache.materialize_checkout(
                clone_url, repo_sha, ws.repo_dir,
            )
        except Exception:
            # Materialization failed — destroy the workspace so it
            # does not become an orphan.
            self._safe_destroy(ws)
            self.metrics.workspaces_destroyed += 1
            raise

        # The workspace is now an independent snapshot; GC may evict
        # the cache entry without affecting this attempt.
        self.metrics.source_cache_bytes_after = self.source_cache.size_bytes()
        self.metrics.materialization_duration_seconds += (
            time.monotonic() - t0
        )
        return PreparedRepository(
            workspace_id=ws.workspace_id,
            workspace_root=ws.root,
            repository_path=ws.repo_dir,
            artifacts_path=ws.artifacts_dir,
            logs_path=ws.logs_dir,
            repo_sha=repo_sha,
            cache_key=cache_key,
            cache_hit=cache_hit,
        )

    def cleanup(self, prepared: PreparedRepository) -> bool:
        """Destroy the workspace backing `prepared`. Idempotent."""
        ws = Workspace(
            workspace_id=prepared.workspace_id,
            root=prepared.workspace_root,
            input_dir=prepared.workspace_root / "input",
            repo_dir=prepared.repository_path,
            probe_dir=prepared.workspace_root / "probe",
            artifacts_dir=prepared.artifacts_path,
            logs_dir=prepared.logs_path,
            tmp_dir=prepared.workspace_root / "tmp",
            cleanup_marker=prepared.workspace_root / "cleanup_marker",
        )
        ok = self.workspace_manager.cleanup(ws)
        if ok:
            self.metrics.workspaces_destroyed += 1
        else:
            self.metrics.workspace_cleanup_failures += 1
        return ok

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _lock(self, layout) -> Iterator[None]:
        lock_path = layout.cache_root / (layout.cache_key + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as fh:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                log.warning("materializer lock failed for %s: %s",
                            layout.cache_key, exc)
            try:
                yield
            finally:
                try:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    def _sha_present_in_cache(self, layout, sha: str) -> bool:
        cat = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=str(layout.bare_git),
            capture_output=True, text=True, timeout=60,
        )
        return cat.returncode == 0

    def _fetch_with_metrics(self, clone_url: str) -> None:
        self.metrics.source_cache_fetches += 1
        try:
            self.source_cache.fetch(clone_url)
        except Exception as exc:  # noqa: BLE001
            self.metrics.source_cache_fetch_failures += 1
            raise

    def _safe_destroy(self, ws: Workspace) -> None:
        try:
            shutil.rmtree(ws.root, ignore_errors=True)
        except OSError:
            self.metrics.workspace_cleanup_failures += 1

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def metrics_snapshot(self) -> dict:
        return dataclasses.asdict(self.metrics)


def gc_with_lock(
    materializer: RepositoryMaterializer,
    *,
    max_bytes: int | None = None,
    max_age_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    """GC that acquires each entry's lock before considering eviction.

    Returns a metrics dict. Never deletes durable evidence / result
    records.
    """
    cache = materializer.source_cache
    entries = cache.entries()
    out = {
        "entries_considered": len(entries),
        "entries_protected": 0,
        "entries_evicted": 0,
        "bytes_reclaimable": 0,
        "bytes_reclaimed": 0,
        "dry_run": dry_run,
    }
    import fcntl
    for entry in entries:
        layout = cache.layout(entry.clone_url)
        lock_path = layout.cache_root / (layout.cache_key + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fh = open(lock_path, "w")
        except OSError:
            out["entries_protected"] += 1
            continue
        try:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                # Another materializer is using this entry → protect.
                fh.close()
                out["entries_protected"] += 1
                continue
            try:
                # Re-evaluate eviction under the lock.
                evict = False
                size = entry.size_bytes
                if max_age_days is not None and entry.last_used_at:
                    try:
                        from datetime import datetime, UTC
                        age = time.time() - datetime.strptime(
                            entry.last_used_at, "%Y-%m-%dT%H:%M:%SZ",
                        ).replace(tzinfo=UTC).timestamp()
                        if age > max_age_days * 86400:
                            evict = True
                    except (ValueError, TypeError):
                        pass
                if max_bytes is not None:
                    if size > max_bytes:
                        evict = True
                if evict:
                    out["bytes_reclaimable"] += size
                    if not dry_run:
                        shutil.rmtree(entry.cache_path, ignore_errors=True)
                        meta = entry.cache_path.parent / "cache_meta.json"
                        if meta.exists():
                            meta.unlink()
                        out["bytes_reclaimed"] += size
                        out["entries_evicted"] += 1
            finally:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            fh.close()
    return out
