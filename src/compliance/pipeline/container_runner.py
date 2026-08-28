"""OCI-runtime-agnostic host-side runner for the repo-runtime container.

This module knows nothing about compliance rules or Article 12(1). It is
a thin wrapper that:

    1. discovers an available OCI runtime (podman first, then docker),
    2. invokes the runtime's `exec` subcommand against a target repo,
    3. surfaces the container's raw result.json + per-step stdout/stderr
       + exit code as a `ContainerRunResult` to the caller.

The caller is responsible for:
- writing any probe script to a host path before invocation,
- reading whatever the probe wrote under the artifacts directory after,
- mapping the container's structured result to its own domain (Evidence,
  RunStatus, etc.).

The runner enforces the host-side security flags described in
runtime/scripts/run-local.sh: cap-drop ALL, no-new-privileges,
pids/memory/cpu caps, tmpfs for /tmp, read-only bind of the target
checkout, writable bind of the artifacts directory, and an allow-listed
env (no host secrets forwarded).

The runner is intentionally generic. It does not know about
`recording_category`, `EvidenceOrigin`, `Article121AutomaticLoggingTest`,
PASS/FAIL semantics, or any adapter logic. Those stay in the
compliance/pipeline layer.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Default image tag. Overridable via env so CI / GHA can pin a different
# tag without code changes.
DEFAULT_IMAGE = os.environ.get(
    "REGUARD_RUNTIME_IMAGE",
    "python-agent-runtime:dev",
)

# Path inside the container where the probe script (if any) is bind-mounted.
PROBE_SCRIPT_CONTAINER_PATH = "/workspace/probe.py"

# Allow-listed env keys forwarded into the container exec step. We
# deliberately do not forward the host environment wholesale — that
# would leak secrets. The compliance layer decides what extra env the
# probe needs.
DEFAULT_ENV = {
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
}


@dataclass(frozen=True)
class ContainerRunResult:
    """Raw result of one container invocation.

    This is the surface the compliance pipeline consumes; the runner
    does not interpret any of these fields.
    """

    ok: bool
    exit_code: int
    runtime_stdout: str
    runtime_stderr: str
    result_json: Optional[dict] = None
    # Host-side path to the trajectory / artifact the probe wrote.
    # None when the probe never produced one.
    trajectory_path: Optional[Path] = None
    # Host-side path to result.json written by the runtime.
    result_json_path: Optional[Path] = None
    # Host-side path to the artifacts directory mounted at /artifacts.
    artifacts_dir: Optional[Path] = None
    duration_seconds: float = 0.0
    runtime_name: str = ""
    runtime_invocation: list[str] = field(default_factory=list)
    error: Optional[str] = None


class ContainerRunnerError(RuntimeError):
    """Raised when no usable OCI runtime is available."""


def _discover_runtime() -> tuple[str, list[str]]:
    """Return (runtime_binary, extra_flags_for_no_socket).

    Prefers podman. Falls back to docker. Raises if neither is on PATH.
    """
    for binary in ("podman", "docker"):
        path = shutil.which(binary)
        if path:
            return binary, []
    raise ContainerRunnerError(
        "no OCI runtime found on PATH; install podman or docker"
    )


def _read_result_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _find_trajectory(artifacts_dir: Path) -> Optional[Path]:
    """Locate the trajectory file the probe wrote.

    The compliance layer currently writes to `trajectory.json` next to
    the probe script. We accept either an exact `trajectory.json` or
    the most recent `.json` artifact written by the probe step.
    """
    exact = artifacts_dir / "trajectory.json"
    if exact.exists():
        return exact
    # Fall back to scanning the artifacts directory for any JSON file
    # produced by the exec step.
    candidates = sorted(
        p for p in artifacts_dir.rglob("*.json")
        if p.is_file() and p.name != "result.json"
    )
    if candidates:
        return candidates[-1]
    return None


def run_in_container(
    *,
    target_repo_path: Path,
    probe_script_path: Path,
    probe_task: str,
    probe_extra_env: Optional[dict[str, str]] = None,
    image: str = DEFAULT_IMAGE,
    timeout_seconds: int = 600,
    pids_limit: int = 256,
    memory_limit: str = "4g",
    cpus_limit: str = "2",
    tmp_size: str = "2g",
    workspace_size: str = "4g",
    result_json_filename: str = "container_result.json",
) -> ContainerRunResult:
    """Execute a Reguard probe inside the frozen runtime container.

    The probe script at `probe_script_path` is bind-mounted into the
    container at `/workspace/probe.py` and executed after the repo is
    installed. The probe is expected to write its trajectory to
    `COMPLIANCE_TRAJECTORY_PATH` (set inside the container by the runner).
    """
    target_repo_path = target_repo_path.resolve()
    probe_script_path = probe_script_path.resolve()
    if not target_repo_path.is_dir():
        raise FileNotFoundError(f"target_repo_path not a directory: {target_repo_path}")
    if not probe_script_path.is_file():
        raise FileNotFoundError(f"probe_script_path not a file: {probe_script_path}")

    runtime, _ = _discover_runtime()

    artifacts_dir = Path(tempfile.mkdtemp(prefix="reguard_container_"))
    # Pre-chown to a broad-readable mode so the host user can read the
    # artifacts dir after the container (whose bind mount gets remapped
    # to a rootless UID) writes to it. The container writes everything
    # as UID 10001; podman rootless remaps that to a high UID outside,
    # so we chmod here to dodge the permissions gap.
    try:
        artifacts_dir.chmod(0o777)
    except OSError:
        pass
    # Ensure the probe script is executable so subprocess.Popen can
    # invoke it inside the container. We copy it to a writable host
    # location under artifacts_dir so we can chmod without mutating
    # the original.
    probe_exec_copy = artifacts_dir / "probe.py"
    try:
        probe_exec_copy.write_bytes(probe_script_path.read_bytes())
        probe_exec_copy.chmod(0o755)
    except OSError:
        probe_exec_copy = probe_script_path
    trajectory_host_path = artifacts_dir / "trajectory.json"
    result_json_host_path = artifacts_dir / result_json_filename

    # Build the exec command argv. Each runtime uses slightly different
    # flag spellings for some security knobs, but the semantics are
    # close enough for our purposes.
    #
    # Outer-level env (container --env): control-side vars that the
    # runtime entrypoint itself needs (locale, tempdir).
    env_args: list[str] = []
    for k, v in DEFAULT_ENV.items():
        env_args += ["--env", f"{k}={v}"]

    # Inner-level env (exec subcommand --env): vars that need to reach
    # the host-supplied probe subprocess. The runtime's run_subprocess
    # builds the subprocess env from an allow-list and only adds
    # extra_env; setting outer --env alone would be dropped.
    exec_env_args: list[str] = []
    # The probe writes to the container-internal /artifacts path. The
    # bind mount maps /artifacts → artifacts_dir on the host, so the
    # file ends up at trajectory_host_path from the host's POV.
    exec_env_args += [
        "--env", "COMPLIANCE_TRAJECTORY_PATH=/artifacts/trajectory.json",
    ]
    for k, v in (probe_extra_env or {}).items():
        exec_env_args += ["--env", f"{k}={v}"]

    # We rely on the runtime's default bridge network. Install needs
    # PyPI access; the probe step is host-supplied deterministic
    # orchestration code and is not expected to make outbound calls.
    # Strict per-step network isolation (install=enabled, probe=disabled)
    # requires a two-container invocation with a shared /workspace
    # bind-mount and is tracked as a follow-up TODO.
    network_args: list[str] = []

    invocation = [
        runtime, "run", "--rm",
        *network_args,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(pids_limit),
        "--memory", memory_limit,
        "--cpus", cpus_limit,
        "--tmpfs", f"/tmp:rw,nosuid,size={tmp_size}",
        "--user", "10001:10001",
        "--mount", f"type=bind,src={target_repo_path},dst=/input,readonly",
        "--mount", f"type=bind,src={artifacts_dir},dst=/artifacts,U=true",
        "--mount", f"type=bind,src={probe_exec_copy},dst={PROBE_SCRIPT_CONTAINER_PATH},readonly,U=true",
        *env_args,
        image,
        "exec",
        "--repo-path", "/input",
        "--artifacts-dir", "/artifacts",
        "--output", "/artifacts/container_result.json",
        "--timeout-seconds", str(timeout_seconds),
        *exec_env_args,
        # Use /usr/local/bin/python3 explicitly. The runtime's
        # run_subprocess uses sys.executable which works, but passing
        # the probe.py path as the first arg of --command would
        # trigger Popen to try executing it directly (Exec format
        # error). The runtime then prepends sys.executable. So we
        # pass just the probe path + task and rely on the runtime's
        # exec semantics — but the runtime's exec_cmd currently
        # treats argv[0] as the executable. We must pass
        # `[python, probe.py, task]` as argv.
        "--command", f"/usr/local/bin/python3 {PROBE_SCRIPT_CONTAINER_PATH} {probe_task}",
    ]

    started = time.monotonic()
    proc = subprocess.run(
        invocation,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 60,  # outer guard above runtime's inner one
    )
    duration = time.monotonic() - started

    result_json = _read_result_json(result_json_host_path)
    trajectory = _find_trajectory(artifacts_dir)

    return ContainerRunResult(
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        runtime_stdout=proc.stdout or "",
        runtime_stderr=proc.stderr or "",
        result_json=result_json,
        trajectory_path=trajectory,
        result_json_path=result_json_host_path,
        artifacts_dir=artifacts_dir,
        duration_seconds=duration,
        runtime_name=runtime,
        runtime_invocation=invocation,
        error=None if proc.returncode == 0 else (
            f"{runtime} exited {proc.returncode}: {proc.stderr[:400] if proc.stderr else proc.stdout[:400]}"
        ),
    )


def is_container_runtime_available() -> tuple[bool, str]:
    """Return (available, binary_name) for diagnostic purposes."""
    try:
        name, _ = _discover_runtime()
        return True, name
    except ContainerRunnerError as exc:
        return False, str(exc)
