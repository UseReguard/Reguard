"""Deterministic SHA resolution from a remote repository.

For each selected repository the runner resolves an exact 40-character
Git commit SHA from `git ls-remote`. Failures are recorded with a
machine-readable class so the 20-repo gate can report
`SHA_RESOLUTION_ERROR` counts.

Validation rule:
  - the SHA must be a 40-character lower-hex string.
  - it must come from `git ls-remote origin HEAD` against the
    canonical GitHub clone URL.

Branch names are NEVER accepted. The frozen run manifest is
immutable thereafter; every retry uses the same persisted SHA.

This module deliberately has no dependency on the orchestrator or
the article-12-1 requirement. SHA resolution is orchestration
metadata.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ShaResolutionError(RuntimeError):
    """Raised when no SHA can be resolved."""


@dataclass(frozen=True)
class ShaResolution:
    sha: str | None
    classification: str    # 'ok' | 'sha_resolution_error'
    message: str

    @property
    def ok(self) -> bool:
        return self.classification == "ok"


def _ls_remote_sha(clone_url: str, timeout_s: int = 30) -> str | None:
    """Invoke `git ls-remote origin HEAD` and return the SHA.

    Returns None on any failure (timeout, non-zero exit, malformed
    output). Caller classifies the error.
    """
    try:
        proc = subprocess.run(
            ["git", "ls-remote", clone_url, "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShaResolutionError(
            f"git ls-remote timed out after {timeout_s}s"
        ) from exc
    except OSError as exc:
        raise ShaResolutionError(f"git ls-remote OS error: {exc}") from exc

    if proc.returncode != 0:
        raise ShaResolutionError(
            f"git ls-remote exit={proc.returncode}: "
            f"{proc.stderr.strip() or 'no stderr'}"
        )

    # Expected output line: "<sha>\tHEAD"
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        tab = line.find("\t")
        if tab < 0:
            continue
        sha = line[:tab].strip()
        if _SHA_RE.match(sha):
            return sha
    raise ShaResolutionError(
        "git ls-remote returned no 40-char SHA line"
    )


def resolve_remote_sha(clone_url: str, *, timeout_s: int = 30) -> ShaResolution:
    """Resolve the remote HEAD SHA. Always returns a
    `ShaResolution`; never raises on transport issues."""
    try:
        sha = _ls_remote_sha(clone_url, timeout_s=timeout_s)
    except ShaResolutionError as exc:
        return ShaResolution(
            sha=None,
            classification="sha_resolution_error",
            message=str(exc),
        )
    return ShaResolution(
        sha=sha,
        classification="ok",
        message=f"resolved from {clone_url}",
    )


def is_valid_sha(s: str) -> bool:
    """Public check used by tests."""
    return bool(_SHA_RE.match(s))
