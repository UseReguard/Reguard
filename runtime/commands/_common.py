"""Shared helpers for runtime subcommands.

Keeps command-records, timeout handling, and artifact paths in one
place so all three modes (inspect / build / test) behave identically.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Optional

from ..models import Artifact, CommandRecord, Status


log = logging.getLogger(__name__)


# Default working copy inside the container. Override via the
# `REPO_RUNTIME_WORKSPACE` env var for local host development where
# `/workspace` isn't a writable tmpfs (the Docker host runner sets
# `--tmpfs /workspace` so /workspace exists and is writable).
WORKSPACE_REPO = Path(os.environ.get("REPO_RUNTIME_WORKSPACE", "/workspace/repo"))


def _now_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def host_checkout_copy(src: Path, dst: Path) -> None:
    """Copy `src` (read-only) to `dst` (writable) deterministically.

    Copies file contents and permissions. Does NOT execute any
    hooks, does NOT run `setup.py`, does NOT install anything.

    We use `cp -a` semantics implemented in pure Python: walk the tree,
    `os.makedirs` for directories, `shutil.copy2` for files. Symlinks
    are copied as symlinks (no follow) so any repo-supplied symlink is
    preserved without being dereferenced into the workspace.
    """
    if not src.is_dir():
        raise FileNotFoundError(f"repo path not a directory: {src}")

    # Wipe dst first so we get a clean copy every time.
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        rel = Path(dirpath).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for fn in filenames:
            sp = Path(dirpath) / fn
            dp = target_dir / fn
            if sp.is_symlink():
                target = os.readlink(sp)
                if dp.exists() or dp.is_symlink():
                    dp.unlink()
                os.symlink(target, dp)
            else:
                shutil.copy2(sp, dp, follow_symlinks=False)


def write_result_atomic(result, output_path: Path) -> None:
    """Write the result JSON to `output_path`, creating parent dirs.

    `result` is a `runtime.models.Result` instance. The function
    always writes — even on error / timeout — so the host always
    receives a parseable document.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    result.write(str(tmp))
    os.replace(tmp, output_path)


def run_subprocess(
    *,
    argv: list[str],
    cwd: Path,
    artifacts_dir: Path,
    label: str,
    timeout_seconds: int,
    extra_env: Optional[dict[str, str]] = None,
) -> CommandRecord:
    """Run `argv` from `cwd` with a hard timeout, capturing stdout/stderr.

    stdout and stderr are streamed to per-command files under
    `artifacts_dir` (paths returned in the CommandRecord). Subprocess
    invocations use `subprocess.Popen` with `shell=False` so repo-
    supplied shell metacharacters cannot be interpreted.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_path = artifacts_dir / f"{label}.stdout.log"
    err_path = artifacts_dir / f"{label}.stderr.log"

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
    }
    if extra_env:
        env.update(extra_env)

    start = time.monotonic()
    timed_out = False
    exit_code = -1

    try:
        with out_path.open("wb") as out_fh, err_path.open("wb") as err_fh:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out_fh,
                stderr=err_fh,
                shell=False,
                start_new_session=True,  # group kill on timeout
            )
            try:
                exit_code = proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(proc)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    except FileNotFoundError as exc:
        # The binary itself does not exist.
        err_path.write_text(f"executable not found: {argv[0]!r}: {exc}\n",
                            encoding="utf-8")
        exit_code = 127
    duration_ms = _now_ms(start)

    return CommandRecord(
        label=label,
        argv=list(argv),
        cwd=str(cwd),
        exit_code=exit_code,
        duration_ms=duration_ms,
        timed_out=timed_out,
        stdout_artifact=str(out_path.relative_to(artifacts_dir.parent)),
        stderr_artifact=str(err_path.relative_to(artifacts_dir.parent)),
    )


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Send SIGKILL to the whole process group so children die too."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # Fallback: try the direct child.
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def log_artifacts(artifacts_dir: Path) -> list[Artifact]:
    """Inventory everything currently under `artifacts_dir` (sorted)."""
    out: list[Artifact] = []
    if not artifacts_dir.exists():
        return out
    for p in sorted(artifacts_dir.rglob("*")):
        if p.is_file():
            try:
                size = p.stat().st_size
            except OSError:
                size = None
            out.append(Artifact(
                path=str(p.relative_to(artifacts_dir)),
                description=p.name,
                bytes=size,
            ))
    return out


def python_version_string() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
