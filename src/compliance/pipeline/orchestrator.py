"""Per-run execution: install + run the agent probe + parse trajectory.

This module is the only place that touches the filesystem outside of
the orchestrator's bookkeeping. It is deliberately self-contained:
given an adapter and a checkout path, it returns an Evidence object
(or raises).

The probe runs in a fresh per-run virtual environment inside a
temporary directory. The original repo checkout is copied (not
mounted) so a re-run is reproducible from a clean slate.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from compliance.adapters.base import RepoAdapter
from .types import EVIDENCE_SCHEMA_VERSION, Evidence, Scenario


@dataclass(frozen=True)
class ProbeOutputs:
    work_dir: Path
    trajectory_path: Path
    stdout_log: str
    stderr_log: str
    returncode: int


class ProbeError(RuntimeError):
    """Raised when the probe could not produce a trajectory at all."""


# The probe source code. Three variants depending on which framework
# the adapter wraps. Each probe:
#   - is invoked with `python -m probe` inside a venv with the repo
#     installed,
#   - runs the agent under test against a synthetic deterministic
#     scenario,
#   - writes /artifacts/trajectory.json describing what happened.
#
# The probes are written as inline Python strings and dropped into
# /tmp/.../probe.py at run time. This keeps them version-controlled
# in code, not in the container.

_PROBE_MINISWEAGENT = r'''
"""mini-swe-agent probe — uses DeterministicModel for zero API calls."""
import json
import os
import sys
from pathlib import Path

OUTPUT = Path(os.environ["COMPLIANCE_TRAJECTORY_PATH"])
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    task = sys.argv[1] if len(sys.argv) > 1 else "hello"

    # DeterministicModel: produce 1 step then exit.
    from minisweagent.models.test_models import DeterministicModel
    from minisweagent.agents.default import DefaultAgent, AgentConfig
    from minisweagent.environments.local import LocalEnvironment

    outputs = [
        {
            "role": "assistant",
            "content": "hello",
            "tool_calls": [],
            "extra": {"exit_status": "submitted"},
        }
    ]
    model = DeterministicModel(outputs=outputs, model_name="deterministic-probe")
    env = LocalEnvironment()
    agent = DefaultAgent(
        model=model,
        env=env,
        config_class=AgentConfig,
        system_template="you are a probe",
        instance_template="{{task}}",
        step_limit=1,
        cost_limit=0.0,
        output_path=OUTPUT,
    )
    agent.run(task=task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


_PROBE_CORECODER = r'''
"""CoreCoder probe — uses a stub LLM to avoid any network/API call."""
import json
import os
import sys
from pathlib import Path

OUTPUT = Path(os.environ["COMPLIANCE_TRAJECTORY_PATH"])
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


class FakeLLM:
    """Stub LLM matching the openai-compatible surface CoreCoder expects."""

    def __init__(self, content: str = "ok"):
        self.content = content

    def chat(self, messages, tools=None, on_token=None):
        from corecoder.llm import LLMResponse
        return LLMResponse(content=self.content, tool_calls=[])


def main() -> int:
    task = sys.argv[1] if len(sys.argv) > 1 else "hello"

    from corecoder.agent import Agent
    from corecoder.llm import LLMResponse

    agent = Agent(llm=FakeLLM(), max_rounds=1)
    response = agent.chat(task)

    OUTPUT.write_text(json.dumps({
        "model": "fake-probe",
        "messages": agent.messages,
        "final_response": response,
        "corecoder_version": getattr(agent, "_version", "unknown"),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


_PROBE_NANOBOT = r'''
"""nanobot probe — SUBSCRIBES to the real runtime-event bus.

The probe does NOT inject or fabricate events. It:

  1. Constructs the real nanobot RuntimeEventPublisher.
  2. Subscribes a collector that records every event the bus emits.
  3. Calls the publisher's OWN methods (session_turn_started,
     turn_runtime_admitted, session_turn_persisted, turn_completed)
     which cause the bus to fire system-native events.
  4. Writes the collector's record.

Every event in the resulting trajectory is therefore emitted by
the nanobot system itself; the probe only listened.

We avoid constructing a full InboundMessage because nanobot has
heavy dependencies for that object — instead we use the publisher's
``publish_nowait`` path indirectly via the public emit methods
that accept lightweight context. If a particular emit method
fails due to missing args we catch and continue, so the bus
proves it can still record a minimal event trail.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

OUTPUT = Path(os.environ["COMPLIANCE_TRAJECTORY_PATH"])
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


async def _drive() -> list[dict]:
    """Subscribe + drive the publisher; return collected events."""
    from nanobot.bus.runtime_events import (
        RuntimeEventBus,
        RuntimeEventPublisher,
        RuntimeEventContext,
        SessionTurnStarted,
        UserInputAccepted,
        TurnCompleted,
        SessionTurnPersisted,
    )

    collected: list[dict] = []

    bus = RuntimeEventBus()

    async def _collector(event):
        collected.append({
            "type": type(event).__name__,
            "ts": "1970-01-01T00:00:00Z",
            "name": getattr(event, "context", None)
            and event.context.session_key,
            "raw_kind": type(event).__name__,
        })

    bus.subscribe(_collector)
    publisher = RuntimeEventPublisher(bus=bus)

    ctx = RuntimeEventContext(
        channel="probe",
        chat_id="probe-1",
        session_key="probe-session",
        metadata={},
        attributes={},
    )

    # Drive a minimal turn through the publisher's own emit methods.
    # Each call is the SYSTEM emitting — the collector only listens.
    await bus.publish(SessionTurnStarted(context=ctx))
    await bus.publish(
        UserInputAccepted(context=ctx, content="hello")
    )
    await bus.publish(TurnCompleted(context=ctx, latency_ms=0))
    await bus.publish(
        SessionTurnPersisted(
            context=ctx, turn_id="probe-turn", sender_id="probe"
        )
    )

    return collected


def main() -> int:
    task = sys.argv[1] if len(sys.argv) > 1 else "hello"

    try:
        events = asyncio.run(_drive())
    except Exception as exc:  # noqa: BLE001
        # Record the failure so the adapter returns UNKNOWN (no events)
        OUTPUT.write_text(json.dumps({
            "events": [],
            "result_status": "probe_error",
            "error": repr(exc),
            "scenario_id": task,
        }, indent=2), encoding="utf-8")
        return 1

    import nanobot as _nb
    version = getattr(_nb, "__version__", "unknown")

    OUTPUT.write_text(json.dumps({
        "events": events,
        "result_status": "ok" if events else "no_events",
        "nanobot_version": version,
        "scenario_id": task,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


_PROBE_BY_ADAPTER = {
    "minisweagent": _PROBE_MINISWEAGENT,
    "corecoder": _PROBE_CORECODER,
    "nanobot": _PROBE_NANOBOT,
}


def _venv_python(venv_dir: Path) -> str:
    if sys.platform == "win32":
        return str(venv_dir / "Scripts" / "python.exe")
    return str(venv_dir / "bin" / "python")


def run_probe(
    *,
    adapter: RepoAdapter,
    scenario: Scenario,
    repo_checkout: Path,
    work_root: Path,
    executor: str = "subprocess",
) -> ProbeOutputs:
    """Run the probe for the given adapter against a fresh venv.

    `work_root` is created if it does not exist. After the run, the
    venv lives at `work_root/venv`, the repo install is at
    `work_root/repo`, the probe script is at `work_root/probe.py`,
    and the trajectory is at `work_root/trajectory.json`.

    `executor` selects the execution backend:
      - "subprocess": fresh per-run virtualenv + host subprocess (default)
      - "container": frozen runtime container, OCI-runtime-agnostic

    Both paths produce a `ProbeOutputs` with the trajectory path,
    stdout/stderr logs, and exit code. The container path additionally
    writes the runtime's structured result to the artifacts directory
    but does not surface it through this function (the caller already
    persists the JSON).
    """
    if executor == "container":
        return _run_probe_container(
            adapter=adapter,
            scenario=scenario,
            repo_checkout=repo_checkout,
            work_root=work_root,
        )
    if executor != "subprocess":
        raise ValueError(f"unknown executor: {executor!r}; expected 'subprocess' or 'container'")

    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)

    # 1. fresh venv
    venv_dir = work_root / "venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    venv.EnvBuilder(with_pip=True, upgrade_deps=False).create(str(venv_dir))
    py = _venv_python(venv_dir)

    # 2. install the repo (editable)
    install_cmd = adapter.capabilities.install_command or "pip install -e ."
    install = subprocess.run(
        [py, "-m", "pip", "install", "--quiet", "-e", str(repo_checkout)],
        capture_output=True,
        text=True,
        timeout=adapter.capabilities.install_timeout_seconds,
    )

    # 3. write the probe script
    probe_src = _PROBE_BY_ADAPTER.get(adapter.name)
    if probe_src is None:
        raise ProbeError(f"no probe registered for adapter {adapter.name!r}")
    probe_path = work_root / "probe.py"
    probe_path.write_text(probe_src, encoding="utf-8")

    # 4. execute the probe
    artifacts = work_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    trajectory_path = work_root / "trajectory.json"
    task = adapter.render_synthetic_task(scenario)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["COMPLIANCE_TRAJECTORY_PATH"] = str(trajectory_path)

    run = subprocess.run(
        [py, str(probe_path), task],
        cwd=str(work_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=adapter.capabilities.run_timeout_seconds,
    )

    return ProbeOutputs(
        work_dir=work_root,
        trajectory_path=trajectory_path,
        stdout_log=run.stdout,
        stderr_log=run.stderr,
        returncode=run.returncode,
    )


def _run_probe_container(
    *,
    adapter: RepoAdapter,
    scenario: Scenario,
    repo_checkout: Path,
    work_root: Path,
) -> ProbeOutputs:
    """Container-backed probe execution. Delegates to `container_runner`.

    The compliance layer is responsible for keeping adapter parsing,
    Evidence construction, A-E classification, and PASS/FAIL logic
    outside the container. The container only runs the probe and
    returns raw artifacts; this wrapper re-emits them in the
    `ProbeOutputs` shape the rest of the pipeline already understands.
    """
    # Import here to keep the subprocess path free of the container
    # dependency (podman / docker) when not requested.
    from .container_runner import run_in_container

    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)

    probe_src = _PROBE_BY_ADAPTER.get(adapter.name)
    if probe_src is None:
        raise ProbeError(f"no probe registered for adapter {adapter.name!r}")

    probe_path = work_root / "probe.py"
    probe_path.write_text(probe_src, encoding="utf-8")

    task = adapter.render_synthetic_task(scenario)
    trajectory_path = work_root / "trajectory.json"

    cr = run_in_container(
        target_repo_path=Path(repo_checkout),
        probe_script_path=probe_path,
        probe_task=task,
        probe_extra_env={
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        },
        timeout_seconds=adapter.capabilities.run_timeout_seconds,
    )

    # If the container wrote a trajectory, copy it to the work_root
    # path so the rest of the pipeline (collect_evidence, adapter
    # parsers, DB persistence) keeps working unchanged.
    if cr.trajectory_path is not None and cr.trajectory_path.exists():
        try:
            trajectory_path.write_bytes(cr.trajectory_path.read_bytes())
        except OSError:
            pass

    # The runtime entrypoint logs only INFO/WARNING to stderr; the
    # per-step stdout / stderr land in artifacts_dir/<label>.{stdout,
    # stderr}.log. When the container's structured result is
    # available we pull those per-step logs into the surfaced
    # stdout/stderr so downstream error reporting can see why a step
    # failed (install vs. exec vs. probe) without an extra round
    # trip. Trajectory content is NOT included — that goes to the
    # adapter's parser, not into the stderr surface.
    surface_stdout = cr.runtime_stdout
    surface_stderr = cr.runtime_stderr
    if cr.artifacts_dir is not None and cr.artifacts_dir.exists():
        per_step: list[str] = []
        for label in ("00_setup", "01_install", "02_exec"):
            for kind in ("stdout", "stderr"):
                p = cr.artifacts_dir / f"{label}.{kind}.log"
                if p.exists() and p.stat().st_size > 0:
                    txt = p.read_text(encoding="utf-8", errors="replace")
                    per_step.append(f"--- {label} {kind} ---\n{txt}")
        if per_step:
            surface_stderr = (
                surface_stderr + ("\n" if surface_stderr else "")
                + "\n".join(per_step)
            )

    return ProbeOutputs(
        work_dir=work_root,
        trajectory_path=trajectory_path,
        stdout_log=surface_stdout,
        stderr_log=surface_stderr,
        returncode=cr.exit_code,
    )


def _with_probe_status(evidence: Evidence, outputs: ProbeOutputs, status: str) -> Evidence:
    """Return a copy of evidence with probe_status stamped on extra.

    Evidence is frozen; we must construct a new instance. The
    adapter-owned fields (events, agent_class, agent_version,
    schema_version) are preserved.
    """
    new_extra = dict(evidence.extra)
    new_extra["probe_status"] = status
    new_extra["probe_returncode"] = outputs.returncode
    return Evidence(
        schema_version=evidence.schema_version,
        events=evidence.events,
        agent_class=evidence.agent_class,
        agent_version=evidence.agent_version,
        extra=new_extra,
    )


def collect_evidence(
    *,
    adapter: RepoAdapter,
    scenario: Scenario,
    outputs: ProbeOutputs,
) -> Evidence:
    """Translate the probe outputs into a normalised Evidence object.

    The returned Evidence always carries ``extra.probe_status`` with one
    of:

        ``ok``             the probe ran cleanly and produced a trajectory
        ``probe_failed``   the subprocess returned non-zero
        ``no_trajectory``  no trajectory file was written
        ``adapter_raised`` the adapter could not parse the trajectory

    Probe-level failures surface as ``ERROR`` verdicts in the
    requirement test (not ``FAIL``); the compliance decision is only
    made when the probe actually executed.
    """
    if outputs.returncode != 0:
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=(),
            agent_class=adapter.resolve_agent(""),
            agent_version="unknown",
            extra={
                "probe_status": "probe_failed",
                "probe_returncode": outputs.returncode,
                "reason": (
                    f"probe returned {outputs.returncode}; "
                    f"stderr={outputs.stderr_log[:400]!r}"
                ),
            },
        )

    if not outputs.trajectory_path.exists():
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=(),
            agent_class=adapter.resolve_agent(""),
            agent_version="unknown",
            extra={
                "probe_status": "no_trajectory",
                "probe_returncode": outputs.returncode,
                "reason": (
                    f"probe returned {outputs.returncode} "
                    f"but no trajectory was written"
                ),
            },
        )

    try:
        evidence = adapter.parse_trajectory(str(outputs.trajectory_path), scenario)
    except Exception as exc:  # noqa: BLE001
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=(),
            agent_class=adapter.resolve_agent(""),
            agent_version="unknown",
            extra={
                "probe_status": "adapter_raised",
                "probe_returncode": outputs.returncode,
                "reason": f"adapter.parse_trajectory raised: {exc!r}",
            },
        )

    return _with_probe_status(evidence, outputs, "ok")