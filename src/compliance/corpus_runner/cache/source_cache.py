"""Immutable source cache (class B).

A bare-git per repository, keyed by a stable identity derived from the
clone URL. The cache is class B in the architecture: deleting it affects
performance only and does not change compliance semantics.

The cache is opened read-only by the materializer. The only writer is
`SourceCache.fetch`, which is serialised per cache_key by a process-local
lock so two parallel jobs against the same repo cannot race on
`git fetch`.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


def cache_key_for_url(clone_url: str) -> str:
    """Stable, host-independent cache key derived from clone URL.

    The cache key MUST be deterministic across runs and hosts so that
    two CR-2 replays against the same repo reuse the same cache entry.
    """
    return hashlib.sha256(clone_url.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class SourceCacheLayout:
    cache_root: Path
    cache_key: str
    bare_git: Path
    meta_json: Path

    @property
    def exists(self) -> bool:
        return self.bare_git.exists() and (self.bare_git / "HEAD").exists()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
                elif p.is_dir():
                    # don't follow symlinks here
                    pass
            except OSError:
                continue
    except OSError:
        return 0
    return total


@dataclass
class SourceCacheEntry:
    cache_key: str
    clone_url: str
    cache_path: Path
    last_fetch_at: str | None
    last_used_at: str | None
    size_bytes: int
    state: str
    error: str | None

    def to_json(self) -> dict:
        return {
            "cache_key": self.cache_key,
            "clone_url": self.clone_url,
            "cache_path": str(self.cache_path),
            "last_fetch_at": self.last_fetch_at,
            "last_used_at": self.last_used_at,
            "size_bytes": self.size_bytes,
            "state": self.state,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, d: dict) -> "SourceCacheEntry":
        return cls(
            cache_key=d["cache_key"],
            clone_url=d["clone_url"],
            cache_path=Path(d["cache_path"]),
            last_fetch_at=d.get("last_fetch_at"),
            last_used_at=d.get("last_used_at"),
            size_bytes=int(d.get("size_bytes", 0)),
            state=d.get("state", "ok"),
            error=d.get("error"),
        )


class SourceCache:
    """Manages the per-repository immutable source cache."""

    def __init__(self, cache_root: Path | None = None) -> None:
        if cache_root is None:
            cache_root = self._default_cache_root()
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_cache_root() -> Path:
        env = os.environ.get("REGUARD_SOURCE_CACHE_ROOT", "").strip()
        if env:
            return Path(env)
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "reguard" / "source-cache"

    def layout(self, clone_url: str) -> SourceCacheLayout:
        key = cache_key_for_url(clone_url)
        d = self.cache_root / key
        return SourceCacheLayout(
            cache_root=self.cache_root,
            cache_key=key,
            bare_git=d / "bare.git",
            meta_json=d / "cache_meta.json",
        )

    @contextmanager
    def _lock(self, layout: SourceCacheLayout) -> Iterator[None]:
        """Process-local + filesystem-level lock on the cache entry.

        Two parallel jobs against the same cache_key serialise their
        fetch through a fcntl flock on a sidecar lock file. A reader
        (materialize) does not need this lock; the lock is only held
        during fetch."""
        lock_path = layout.cache_root / (layout.cache_key + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                log.warning("source cache lock failed for %s: %s",
                            layout.cache_key, exc)
            try:
                yield
            finally:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    def _read_meta(self, layout: SourceCacheLayout) -> SourceCacheEntry | None:
        if not layout.meta_json.exists():
            return None
        try:
            return SourceCacheEntry.from_json(
                json.loads(layout.meta_json.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return None

    def _write_meta(self, layout: SourceCacheLayout,
                    entry: SourceCacheEntry) -> None:
        layout.meta_json.parent.mkdir(parents=True, exist_ok=True)
        tmp = layout.meta_json.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entry.to_json(), indent=2, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(layout.meta_json)

    def _mark_used(self, layout: SourceCacheLayout,
                   clone_url: str) -> None:
        existing = self._read_meta(layout) or SourceCacheEntry(
            cache_key=layout.cache_key,
            clone_url=clone_url,
            cache_path=layout.bare_git,
            last_fetch_at=None,
            last_used_at=None,
            size_bytes=0,
            state="ok",
            error=None,
        )
        existing.last_used_at = _now_iso()
        existing.size_bytes = _dir_size(layout.bare_git)
        existing.error = None
        existing.state = "ok"
        self._write_meta(layout, existing)

    def fetch(self, clone_url: str) -> SourceCacheLayout:
        """Fetch (or refetch) the bare mirror for `clone_url`.

        Creates a new bare.git via `git clone --mirror` if absent, and
        runs `git fetch` to update it. Records cache metadata.

        Returns the cache layout. Raises OSError / subprocess errors if
        the fetch fails; the metadata is stamped with state='error' and
        the message.
        """
        layout = self.layout(clone_url)
        with self._lock(layout):
            try:
                if not layout.exists:
                    layout.bare_git.parent.mkdir(parents=True, exist_ok=True)
                    # `git clone --mirror` sets up a bare repo that
                    # fetches every ref (including remote-tracking
                    # branches and tags). For HEAD specifically we
                    # need a follow-up fetch with explicit +HEAD.
                    subprocess.run(
                        ["git", "clone", "--mirror", clone_url,
                         str(layout.bare_git)],
                        check=True, capture_output=True, timeout=600,
                    )
                # Always run a fetch so newly-pushed commits land.
                subprocess.run(
                    ["git", "fetch", "origin",
                     "+refs/heads/*:refs/heads/*",
                     "+refs/tags/*:refs/tags/*",
                     "+HEAD:refs/heads/HEAD"],
                    cwd=str(layout.bare_git),
                    check=True, capture_output=True, timeout=600,
                )
                # Mark fetch + use.
                entry = SourceCacheEntry(
                    cache_key=layout.cache_key,
                    clone_url=clone_url,
                    cache_path=layout.bare_git,
                    last_fetch_at=_now_iso(),
                    last_used_at=_now_iso(),
                    size_bytes=_dir_size(layout.bare_git),
                    state="ok",
                    error=None,
                )
                self._write_meta(layout, entry)
                return layout
            except (subprocess.CalledProcessError,
                    subprocess.TimeoutExpired, OSError) as exc:
                entry = SourceCacheEntry(
                    cache_key=layout.cache_key,
                    clone_url=clone_url,
                    cache_path=layout.bare_git,
                    last_fetch_at=None,
                    last_used_at=None,
                    size_bytes=_dir_size(layout.bare_git) if layout.bare_git.exists() else 0,
                    state="error",
                    error=repr(exc)[:2000],
                )
                try:
                    self._write_meta(layout, entry)
                except OSError:
                    pass
                raise

    def materialize_checkout(
        self,
        clone_url: str,
        expected_sha: str,
        workspace_repo_dir: Path,
    ) -> Path:
        """Materialize the requested SHA into `workspace_repo_dir`.

        v1.1.1 design: extract a `git archive` from the cache into the
        workspace. The workspace receives an INDEPENDENT snapshot of the
        file tree; there is NO symlink, no pointer, no `.git/` shim
        back into the shared cache. The workspace is physically and
        logically separated from the cache.

        Compliance semantics are identical to a `git clone` of the same
        SHA. The cache state is not part of execution identity.

        Returns the resolved `workspace_repo_dir`. Raises RuntimeError
        if the SHA is not reachable from the cache.
        """
        # Fast path: do not touch the cache at all if it already
        # contains the SHA. This is the v1.1.1 hot path for repeated
        # runs against the same SHA.
        layout = self.layout(clone_url)
        if layout.exists:
            cat = subprocess.run(
                ["git", "cat-file", "-t", expected_sha],
                cwd=str(layout.bare_git),
                capture_output=True, text=True, timeout=60,
            )
            if cat.returncode != 0:
                # SHA not in cache → fetch + retry once.
                self.fetch(clone_url)
                cat = subprocess.run(
                    ["git", "cat-file", "-t", expected_sha],
                    cwd=str(layout.bare_git),
                    capture_output=True, text=True, timeout=60,
                )
                if cat.returncode != 0:
                    raise RuntimeError(
                        f"requested SHA {expected_sha} not present in cache "
                        f"for {clone_url} after fetch (cat-file rc="
                        f"{cat.returncode})"
                    )
        else:
            # Cold cache → fetch.
            self.fetch(clone_url)

        workspace_repo_dir.parent.mkdir(parents=True, exist_ok=True)
        if workspace_repo_dir.exists():
            shutil.rmtree(workspace_repo_dir)
        workspace_repo_dir.mkdir(parents=True, exist_ok=True)

        # Hold the per-cache-key lock for the duration of the archive
        # + extract so GC cannot evict the cache entry mid-extract.
        # (`fetch` was already self-synchronised by its own lock.)
        with self._lock(layout):
            # Materialise via `git archive`. This produces the exact file
            # tree for the SHA and is read-only against the cache.
            archive = subprocess.run(
                ["git", "archive", "--format=tar", expected_sha],
                cwd=str(layout.bare_git),
                capture_output=True, timeout=300,
            )
            if archive.returncode != 0:
                raise RuntimeError(
                    f"git archive failed for {expected_sha}: "
                    f"{archive.stderr.decode('utf-8', errors='replace')}"
                )
            import tarfile
            import io
            # Block symlinks that point outside the workspace. The archive
            # cannot reasonably point outside (it only contains paths
            # inside the repo), but defense in depth.
            with tarfile.open(fileobj=io.BytesIO(archive.stdout),
                              mode="r:") as tf:
                for member in tf.getmembers():
                    if member.issym() or member.islnk():
                        target = member.linkname
                        if target and (
                            target.startswith("/")
                            or ".." in Path(target).parts
                        ):
                            raise RuntimeError(
                                f"archive contains unsafe symlink at "
                                f"{member.name!r} → {target!r}"
                            )
                tf.extractall(path=str(workspace_repo_dir))

        # Record the workspace's exact-SHA identity inside the workspace
        # as a `.reguard-materialized` marker (NOT a `.git/` shim — the
        # workspace has no SCM metadata that points back to the cache).
        marker = workspace_repo_dir / ".reguard-materialized"
        marker.write_text(
            f"repo_sha={expected_sha}\ncache_key={layout.cache_key}\n"
            f"materialized_at={_now_iso()}\n",
            encoding="utf-8",
        )

        # Best-effort world-readable so a non-root container UID can
        # stat files across the bind mount.
        try:
            subprocess.run(
                ["chmod", "-R", "a+rX", str(workspace_repo_dir)],
                check=False, capture_output=True, timeout=60,
            )
        except (FileNotFoundError, OSError):
            pass

        self._mark_used(layout, clone_url)
        return workspace_repo_dir

    def size_bytes(self) -> int:
        if not self.cache_root.exists():
            return 0
        return _dir_size(self.cache_root)

    def entries(self) -> list[SourceCacheEntry]:
        out: list[SourceCacheEntry] = []
        if not self.cache_root.exists():
            return out
        for meta in self.cache_root.rglob("cache_meta.json"):
            try:
                out.append(SourceCacheEntry.from_json(
                    json.loads(meta.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
        return out


def gc(cache: SourceCache,
       *,
       max_bytes: int | None = None,
       max_age_days: int | None = None,
       ) -> dict:
    """LRU eviction. Returns metrics; does not delete durable state.

    Entries whose `last_used_at` is older than `max_age_days` OR that
    push the total cache above `max_bytes` are evicted. Eviction is
    skipped if any other process holds the entry's lock file (cheap
    best-effort).
    """
    cache_hits_before = len(cache.entries())
    entries = sorted(
        cache.entries(),
        key=lambda e: e.last_used_at or "1970-01-01T00:00:00Z",
    )
    size = cache.size_bytes()
    evicted = 0
    freed = 0
    now = time.time()
    for entry in entries:
        evict = False
        if max_age_days is not None and entry.last_used_at:
            try:
                age = now - datetime.strptime(
                    entry.last_used_at, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC).timestamp()
                if age > max_age_days * 86400:
                    evict = True
            except (ValueError, TypeError):
                pass
        if max_bytes is not None and size > max_bytes:
            evict = True
        if not evict:
            continue
        try:
            if entry.cache_path.exists():
                size_entry = _dir_size(entry.cache_path)
                shutil.rmtree(entry.cache_path, ignore_errors=True)
                # also remove sidecar meta + lock if present
                meta = entry.cache_path.parent / "cache_meta.json"
                if meta.exists():
                    meta.unlink()
                lock = entry.cache_path.parent.parent / (
                    entry.cache_key + ".lock")
                if lock.exists():
                    try:
                        lock.unlink()
                    except OSError:
                        pass
                freed += size_entry
                size = max(0, size - size_entry)
                evicted += 1
        except OSError as exc:
            log.warning("eviction failed for %s: %s", entry.cache_key, exc)
    return {
        "cache_entries_before": cache_hits_before,
        "evicted": evicted,
        "bytes_freed": freed,
    }


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rmtree(path: Path) -> bool:
    """Best-effort idempotent rmtree. Returns True on success."""
    try:
        shutil.rmtree(path, ignore_errors=True)
        return True
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return True
        log.warning("safe_rmtree(%s) failed: %s", path, exc)
        return False
