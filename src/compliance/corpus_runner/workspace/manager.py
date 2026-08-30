"""Ephemeral per-attempt workspace (class C).

A workspace is created for one EvaluationAttempt, used by the orchestrator
to materialise the source cache checkout, hold probe artefacts, capture
logs, and is destroyed when the attempt reaches a terminal state.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from compliance.corpus_runner.cache.source_cache import (
    SourceCache,
    safe_rmtree,
    sha256_bytes,
    sha256_path,
)

log = logging.getLogger(__name__)


def _default_workspace_root() -> Path:
    env = os.environ.get("REGUARD_WORKSPACE_ROOT", "").strip()
    if env:
        return Path(env)
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if xdg_runtime:
        return Path(xdg_runtime) / "reguard" / "workspaces"
    return Path("/tmp") / "reguard" / "workspaces"


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    root: Path
    input_dir: Path
    repo_dir: Path
    probe_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    tmp_dir: Path
    cleanup_marker: Path

    @classmethod
    def for_attempt(cls, attempt_id: int,
                    workspace_root: Path | None = None) -> "Workspace":
        root_parent = workspace_root or _default_workspace_root()
        root_parent.mkdir(parents=True, exist_ok=True)
        suffix = (
            f"{int(time.time())}_{attempt_id}_"
            f"{uuid.uuid4().hex[:8]}"
        )
        root = root_parent / suffix
        return cls(
            workspace_id=suffix,
            root=root,
            input_dir=root / "input",
            repo_dir=root / "repo",
            probe_dir=root / "probe",
            artifacts_dir=root / "artifacts",
            logs_dir=root / "logs",
            tmp_dir=root / "tmp",
            cleanup_marker=root / "cleanup_marker",
        )

    def create(self) -> None:
        for d in (self.root, self.input_dir, self.repo_dir, self.probe_dir,
                  self.artifacts_dir, self.logs_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)

    def destroy(self) -> bool:
        ok = safe_rmtree(self.root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.cleanup_marker.write_text(
                f"destroyed_at={time.time()}\n", encoding="utf-8",
            )
        except OSError:
            pass
        return ok


class WorkspaceManager:
    """Owns the source cache + workspace lifecycle."""

    def __init__(
        self,
        *,
        source_cache: SourceCache | None = None,
        workspace_root: Path | None = None,
        retain_error_workspace_minutes: int = 0,
    ) -> None:
        self.source_cache = source_cache or SourceCache()
        self.workspace_root = workspace_root
        self.retain_error_workspace_minutes = retain_error_workspace_minutes

    def prepare(
        self,
        *,
        attempt_id: int,
        clone_url: str,
        expected_sha: str,
    ) -> Workspace:
        """Create a workspace and materialise the requested SHA into it.

        Returns the workspace. The workspace is left intact for the
        caller to use. Cleanup is the caller's responsibility.
        """
        ws = Workspace.for_attempt(
            attempt_id, workspace_root=self.workspace_root,
        )
        ws.create()
        # Ensure cache exists & is up to date for this repo.
        if not self.source_cache.layout(clone_url).exists:
            self.source_cache.fetch(clone_url)
        self.source_cache.materialize_checkout(
            clone_url, expected_sha, ws.repo_dir,
        )
        return ws

    def cleanup(self, ws: Workspace, *, error: bool = False) -> bool:
        """Destroy the workspace. Idempotent.

        For `error=True`, retain for `retain_error_workspace_minutes`
        (default 0 → destroy immediately). Cleanup failure is logged but
        never mutates the compliance verdict."""
        if error and self.retain_error_workspace_minutes > 0:
            log.info(
                "workspace %s retained for %d minutes (error path)",
                ws.workspace_id, self.retain_error_workspace_minutes,
            )
            return True
        return ws.destroy()

    def capture_artifact(
        self,
        ws: Workspace,
        *,
        logical_name: str,
        src_path: Path,
        producer: str,
        origin: str,
        mime_or_ext: str,
        max_bytes: int = 16 * 1024 * 1024,
    ) -> Optional[dict]:
        """Record an artifact for retention. Returns metadata dict
        suitable for `execution_artifacts` insertion.

        Truncates if `max_bytes` exceeded and stamps the truncation.
        """
        if not src_path.exists():
            return None
        size = src_path.stat().st_size
        truncated = False
        bytes_to_hash: bytes
        try:
            if size > max_bytes:
                truncated = True
                with open(src_path, "rb") as fh:
                    bytes_to_hash = fh.read(max_bytes)
            else:
                with open(src_path, "rb") as fh:
                    bytes_to_hash = fh.read()
        except OSError as exc:
            log.warning("artifact capture failed for %s: %s",
                        logical_name, exc)
            return None

        sha = sha256_bytes(bytes_to_hash)
        size_recorded = len(bytes_to_hash) if truncated else size

        # Persist into the workspace's artifacts dir under a stable
        # logical name. The DB row is what survives cleanup; the byte
        # file may be evicted later.
        dest = ws.artifacts_dir / f"{logical_name}.bin"
        try:
            dest.write_bytes(bytes_to_hash)
        except OSError as exc:
            log.warning("artifact write failed for %s: %s",
                        logical_name, exc)
            return None

        return {
            "artifact_logical_name": logical_name,
            "producer": producer,
            "origin": origin,
            "size_bytes": size_recorded,
            "sha256": sha,
            "mime_or_ext": mime_or_ext,
            "created_during_execution": True,
            "framework_created": producer.startswith("framework:"),
            "truncated": truncated,
            "host_path": str(dest),
        }


def truncate_log(text: str, max_bytes: int) -> tuple[str, bool]:
    """Truncate `text` to `max_bytes` and return (text, truncated_flag).

    Truncation marker is appended so downstream readers know the log
    was cut. We measure bytes, not characters.
    """
    if not text:
        return "", False
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes]
    # Drop the last partial line so we don't return half a record.
    nl = truncated.rfind(b"\n")
    if nl > 0:
        truncated = truncated[:nl]
    marker = f"\n... [truncated to {max_bytes} bytes]"
    return truncated.decode("utf-8", errors="replace") + marker, True
