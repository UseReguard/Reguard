"""Generic exec primitive for the repo-runtime container.

SECURITY: this is *execution*. The host-supplied command runs inside
an isolated copy of the repository at /workspace/repo. The host
checkout at /input is never modified.

Lifecycle inside a single container invocation:

    1. detect() the build strategy
    2. copy /input (read-only) into /workspace/repo
    3. install the project + dependencies (network=ENABLED for this step)
    4. run the host-supplied command with network=DISABLED
    5. record everything in commands[]

The command is treated as trusted orchestration configuration (host
supplies it; the runtime does not parse README text to derive it).
The network policy is split: install may need outbound pip traffic;
the command itself runs with no network.

This command is intentionally generic — it does not know about
compliance rules, Article 12(1), or any domain. Compliance callers
write a probe script to the host, bind-mount it in at a known path,
and read whatever the probe wrote to --output after the container
exits.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from ..detect import UNSUPPORTED_STRATEGIES, detect
from ..models import (
    Artifact, Environment, NetworkPolicy, RepoInfo, Result, Status,
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
    network_policy: NetworkPolicy = NetworkPolicy.NONE,
    command: Optional[list[str]] = None,
    extra_env: Optional[dict[str, str]] = None,
) -> Result:
    """Run a host-supplied command with the repo installed.

    `network_policy` applies to the exec step (step 4 above). The
    install step (step 3) always runs with ENABLED, regardless of the
    host's request, because pip dependency resolution needs network.

    `extra_env` is forwarded to the host-supplied command (step 4).
    If the host needs its env vars to influence the *install* step
    as well (typical when PYTHONUSERBASE etc. have to survive the
    install subprocess), it can additionally be passed to the
    container's outer env so it propagates into the runtime's
    env vars — those override the install subprocess allow-list.
    """
    started = time.monotonic()
    detection, strategy = detect(repo_path)

    if strategy.strategy in UNSUPPORTED_STRATEGIES or not strategy.command:
        result = _unsupported(
            repo_sha, repo_path, detection,
            strategy=strategy.strategy,
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    if not command:
        result = _error(
            repo_sha, repo_path, detection, network_policy,
            error="no command supplied",
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    # Always work from a writable copy. /input is read-only.
    try:
        host_checkout_copy(repo_path, WORKSPACE_REPO)
    except (FileNotFoundError, OSError) as exc:
        result = _error(
            repo_sha, repo_path, detection, network_policy,
            error=f"failed to copy repo to workspace: {exc}",
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    commands: list = []
    status = Status.SUCCESS

    # Optional setup step (e.g. uv sync). Network ENABLED.
    if strategy.setup:
        per_setup_timeout = max(30, timeout_seconds // 3)
        setup_cmd = run_subprocess(
            argv=strategy.setup,
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="00_setup",
            timeout_seconds=per_setup_timeout,
            extra_env={"REPO_RUNTIME_NETWORK": "enabled"},
        )
        commands.append(setup_cmd)
        if setup_cmd.timed_out:
            status = Status.TIMEOUT
        elif setup_cmd.exit_code != 0:
            status = Status.FAILED

    # Install. Network ENABLED.
    if status == Status.SUCCESS:
        install_budget = max(60, timeout_seconds // 3)
        install_cmd = run_subprocess(
            argv=strategy.command,
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="01_install",
            timeout_seconds=install_budget,
            extra_env={"REPO_RUNTIME_NETWORK": "enabled"},
        )
        commands.append(install_cmd)
        if install_cmd.timed_out:
            status = Status.TIMEOUT
        elif install_cmd.exit_code != 0:
            status = Status.FAILED

    # Exec step. Network DISABLED.
    if status == Status.SUCCESS:
        setup_time = sum(c.duration_ms for c in commands)
        remaining_ms = max(5_000, timeout_seconds * 1000 - setup_time)
        remaining_seconds = max(5, remaining_ms // 1000)

        exec_cmd = run_subprocess(
            argv=list(command),
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="02_exec",
            timeout_seconds=remaining_seconds,
            extra_env=extra_env,
        )
        commands.append(exec_cmd)
        if exec_cmd.timed_out:
            status = Status.TIMEOUT
        elif exec_cmd.exit_code != 0:
            status = Status.FAILED

    artifacts = log_artifacts(artifacts_dir)
    result = Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="exec",
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
            "exec_command": list(command),
            "network_policy_exec": network_policy.value,
            "network_policy_install": "enabled",
        },
    )
    if output_path is not None:
        write_result_atomic(result, output_path)
    return result


# ---------------------------------------------------------------------------

def _unsupported(
    repo_sha: str,
    repo_path: Path,
    detection,
    *,
    strategy: str,
) -> Result:
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
        mode="exec",
        status=Status.UNSUPPORTED,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=Environment(
            python_version="",
            network_policy=NetworkPolicy.NONE,
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
    detection,
    network_policy: NetworkPolicy,
    *,
    error: str,
) -> Result:
    return Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="exec",
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
