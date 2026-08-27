"""Run the test suite for a checked-out repository.

SECURITY: this is *execution*. The test command runs inside an isolated
copy of the repository at /workspace/repo. The host checkout at /input
is never modified.

The default test command is `python -m pytest -q` when the inspector
detected pytest. Otherwise the host must pass an explicit `--command`,
which is treated as trusted orchestration configuration and never
derived from README text.

If no deterministic test command can be established, the result is
`status=unsupported`.
"""
from __future__ import annotations

import logging
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


DEFAULT_PYTEST = [sys.executable, "-m", "pytest", "-q", "--no-header"]


def run(
    *,
    repo_path: Path,
    artifacts_dir: Path,
    timeout_seconds: int,
    repo_sha: str = "",
    output_path: Optional[Path] = None,
    network_policy: NetworkPolicy = NetworkPolicy.NONE,
    command: Optional[list[str]] = None,
    auto_setup: bool = True,
) -> Result:
    """Run the test suite for a checked-out repository.

    Lifecycle inside a single container invocation:

        1. detect() the build strategy + test framework
        2. (if auto_setup and the project is buildable) install the project
           into the container's own Python — this is what makes `test`
           self-contained. Each container starts with no third-party deps.
        3. run the test command (auto-detected pytest or explicit --command)
        4. record everything in commands[]

    `auto_setup=False` skips step 2 — useful when the host already
    prepared the environment in a previous `build` invocation that
    shared the same volume. The default is True because most
    orchestrators invoke the runtime with a fresh container per repo.
    """
    started = time.monotonic()
    detection, strategy = detect(repo_path)

    # Decide the test command.
    if command:
        argv = list(command)
        cmd_label = "user_command"
        command_source = "user"
    elif detection.test_framework == "pytest":
        argv = DEFAULT_PYTEST
        cmd_label = "pytest"
        command_source = "auto-detect"
    else:
        result = _unsupported(
            repo_sha, repo_path, detection, network_policy,
            reason="no deterministic test command: detection did not find "
                   "pytest and no --command was supplied",
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    if not argv:
        result = _unsupported(
            repo_sha, repo_path, detection, network_policy,
            reason="empty test command",
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if output_path is not None:
            write_result_atomic(result, output_path)
        return result

    # Always run from a writable copy.
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

    # Auto-setup: install the project + the test framework so the test
    # command can actually run. Skipped when the strategy is
    # unsupported (poetry/pipenv/none) or when the host explicitly
    # disabled it.
    if auto_setup and strategy.strategy not in UNSUPPORTED_STRATEGIES \
            and strategy.command:
        # Use up to half the budget for setup, with a floor.
        setup_budget = max(30, timeout_seconds // 2)
        remaining    = max(5, timeout_seconds - setup_budget)

        # Optional `uv sync --frozen` first if applicable.
        if strategy.setup:
            setup_cmd = run_subprocess(
                argv=strategy.setup,
                cwd=WORKSPACE_REPO,
                artifacts_dir=artifacts_dir,
                label="00_setup",
                timeout_seconds=setup_budget,
            )
            commands.append(setup_cmd)
            if setup_cmd.timed_out or setup_cmd.exit_code != 0:
                return _finalize_test(
                    repo_sha, repo_path, detection, network_policy,
                    commands, started, timeout_seconds,
                    command_source=command_source,
                    output_path=output_path,
                    artifacts_dir=artifacts_dir,
                )

        install_cmd = run_subprocess(
            argv=strategy.command,
            cwd=WORKSPACE_REPO,
            artifacts_dir=artifacts_dir,
            label="01_install",
            timeout_seconds=setup_budget,
        )
        commands.append(install_cmd)
        if install_cmd.timed_out or install_cmd.exit_code != 0:
            return _finalize_test(
                repo_sha, repo_path, detection, network_policy,
                commands, started, timeout_seconds,
                command_source=command_source,
                output_path=output_path,
                artifacts_dir=artifacts_dir,
            )

        # If pytest is the detected framework but is not yet importable,
        # install it now. The runtime image does not preinstall pytest
        # (keeps the image lean); we only install it when needed.
        if detection.test_framework == "pytest" and command_source != "user":
            probe = run_subprocess(
                argv=[sys.executable, "-c", "import pytest"],
                cwd=WORKSPACE_REPO,
                artifacts_dir=artifacts_dir,
                label="01a_pytest_probe",
                timeout_seconds=10,
            )
            if probe.exit_code != 0:
                pytest_install = run_subprocess(
                    argv=[sys.executable, "-m", "pip", "install", "pytest"],
                    cwd=WORKSPACE_REPO,
                    artifacts_dir=artifacts_dir,
                    label="01b_pytest_install",
                    timeout_seconds=setup_budget,
                )
                commands.append(pytest_install)
                if pytest_install.timed_out or pytest_install.exit_code != 0:
                    return _finalize_test(
                        repo_sha, repo_path, detection, network_policy,
                        commands, started, timeout_seconds,
                        command_source=command_source,
                        output_path=output_path,
                        artifacts_dir=artifacts_dir,
                    )

        # Adjust test budget to remaining time.
        test_timeout = remaining
    else:
        test_timeout = timeout_seconds

    test_cmd = run_subprocess(
        argv=argv,
        cwd=WORKSPACE_REPO,
        artifacts_dir=artifacts_dir,
        label="02_" + cmd_label,
        timeout_seconds=test_timeout,
    )
    commands.append(test_cmd)

    return _finalize_test(
        repo_sha, repo_path, detection, network_policy,
        commands, started, timeout_seconds,
        command_source=command_source,
        output_path=output_path,
        artifacts_dir=artifacts_dir,
    )


def _finalize_test(
    repo_sha, repo_path, detection, network_policy,
    commands, started, timeout_seconds, *,
    command_source: str,
    output_path,
    artifacts_dir: Path,
) -> Result:
    """Compose the final Result from the recorded commands[]."""
    last = commands[-1]
    if last.timed_out:
        status = Status.TIMEOUT
    elif last.exit_code == 0:
        status = Status.SUCCESS
    else:
        # includes pytest exit code 5 (no tests collected) — surface as failed
        status = Status.FAILED

    result = Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="test",
        status=status,
        repo=RepoInfo(sha=repo_sha, path=str(repo_path)),
        environment=Environment(
            python_version=python_version_string(),
            network_policy=network_policy,
        ),
        detection=detection,
        commands=commands,
        artifacts=log_artifacts(artifacts_dir),
        duration_ms=int((time.monotonic() - started) * 1000),
        exit_code=last.exit_code,
        error=None if status == Status.SUCCESS else
                (f"tests timed out after {timeout_seconds}s"
                 if status == Status.TIMEOUT else
                 f"test command exited with code {last.exit_code}; see {last.stderr_artifact}"),
        extra={
            "command_source": command_source,
        },
    )
    if output_path is not None:
        write_result_atomic(result, output_path)
    return result


def _unsupported(
    repo_sha: str,
    repo_path: Path,
    detection,
    network_policy: NetworkPolicy,
    *,
    reason: str,
) -> Result:
    return Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="test",
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
    detection,
    network_policy: NetworkPolicy,
    *,
    error: str,
) -> Result:
    return Result(
        schema_version="1",
        runtime_version="0.1.0",
        mode="test",
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
