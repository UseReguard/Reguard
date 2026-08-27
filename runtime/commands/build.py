"""Build an installable environment for the checked-out repository.

SECURITY: build is *execution*. It runs the detected build command
inside an isolated copy of the repository at /workspace/repo. The host
checkout at /input is never modified — it is mounted read-only.

This module does NOT interpret the README, does NOT auto-fall-through
to alternative strategies after a failure, and does NOT attempt to
`pip install` everything in `requirements-dev.txt` just because it
exists.

If the strategy is unsupported (Pipfile, no recognised files), the
result is `status=unsupported`, which is the host's signal to skip
build for this repository.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from ..detect import BuildStrategy, UNSUPPORTED_STRATEGIES, detect
from ..models import (
    Artifact, Detection, Environment, NetworkPolicy, RepoInfo, Result, Status,
)
from ._common import (
    WORKSPACE_REPO, host_checkout_copy, log_artifacts, python_version_string,
    run_subprocess, write_result_atomic,
)


log = logging.getLogger(__name__)


def run(
    *,
    repo_path: Path,
    artifacts_dir: Path,
    timeout_seconds: int,
    repo_sha: str = "",
    output_path: Optional[Path] = None,
    network_policy: NetworkPolicy = NetworkPolicy.ENABLED,
) -> Result:
    started = time.monotonic()
    detection, strategy = detect(repo_path)

    # Unsupported detection → unsupported result.
    if strategy.strategy in UNSUPPORTED_STRATEGIES or not strategy.command:
        result = _unsupported(
            repo_sha, repo_path, detection, network_policy,
            strategy=strategy.strategy,
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    # Always work from a writable copy. /input is read-only.
    try:
        host_checkout_copy(repo_path, WORKSPACE_REPO)
    except (FileNotFoundError, OSError) as exc:
        result = _error(repo_sha, repo_path, detection, network_policy,
                        error=f"failed to copy repo to workspace: {exc}")
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    commands: list = []
    artifacts: list[Artifact] = []
    status = Status.SUCCESS

    # Optional setup step (e.g. `uv sync --frozen`).
    if strategy.setup:
        per_setup_timeout = max(30, timeout_seconds // 2)
        cmd = run_subprocess(
            argv=strategy.setup,
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="00_setup",
            timeout_seconds=per_setup_timeout,
        )
        commands.append(cmd)
        if cmd.timed_out:
            status = Status.TIMEOUT
        elif cmd.exit_code != 0:
            status = Status.FAILED

    # Main install command — only when setup succeeded (or wasn't needed).
    if status == Status.SUCCESS:
        setup_time = sum(c.duration_ms for c in commands)
        remaining_ms = max(5_000, timeout_seconds * 1000 - setup_time)
        remaining_seconds = max(5, remaining_ms // 1000)

        cmd = run_subprocess(
            argv=strategy.command,
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="01_install",
            timeout_seconds=remaining_seconds,
        )
        commands.append(cmd)
        if cmd.timed_out:
            status = Status.TIMEOUT
        elif cmd.exit_code != 0:
            status = Status.FAILED

    artifacts.extend(log_artifacts(artifacts_dir))
    result = Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="build",
        status=status,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=Environment(
            python_version=python_version_string(),
            network_policy=network_policy,
        ),
        detection=detection,
        commands=commands,
        artifacts=artifacts,
        duration_ms=int((time.monotonic() - started) * 1000),
        exit_code=commands[-1].exit_code if commands else 0,
        error=None if status == Status.SUCCESS else _summarize_error(commands),
        extra={
            "strategy": strategy.strategy,
            "build_command": list(strategy.command),
            "setup_command": list(strategy.setup),
        },
    )
    if output_path is not None:
        write_result_atomic(result, output_path)
    return result


# ---------------------------------------------------------------------------

def _unsupported(
    repo_sha: str,
    repo_path: Path,
    detection: Detection,
    network_policy: NetworkPolicy,
    *,
    strategy: str,
) -> Result:
    """Build a clear `unsupported` result explaining why."""
    if strategy == "poetry":
        reason = (
            "build strategy 'poetry' is not supported: the runtime image "
            "installs uv only. Convert the project to uv, or extend the "
            "Dockerfile to install Poetry."
        )
    elif strategy == "pipenv":
        reason = (
            "build strategy 'pipenv' is not supported by the MVP runtime"
        )
    elif strategy == "none":
        reason = (
            "build strategy 'none': no recognised packaging files "
            "(pyproject.toml, setup.py, setup.cfg, requirements*.txt, "
            "uv.lock, poetry.lock, Pipfile) were found"
        )
    else:
        reason = f"build strategy {strategy!r} is not supported"
    return Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="build",
        status=Status.UNSUPPORTED,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=Environment(
            python_version=python_version_string(),
            network_policy=network_policy,
        ),
        detection=detection,
        commands=[],
        artifacts=[],
        duration_ms=0,
        exit_code=0,
        error=reason,
    )


def _error(
    repo_sha: str,
    repo_path: Path,
    detection: Detection,
    network_policy: NetworkPolicy,
    *,
    error: str,
) -> Result:
    return Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="build",
        status=Status.ERROR,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=Environment(
            python_version=python_version_string(),
            network_policy=network_policy,
        ),
        detection=detection,
        commands=[],
        artifacts=[],
        duration_ms=0,
        exit_code=1,
        error=error,
    )


def _summarize_error(commands) -> Optional[str]:
    last = commands[-1]
    return (f"command {last.argv!r} failed with exit_code={last.exit_code}; "
            f"see {last.stderr_artifact}")
