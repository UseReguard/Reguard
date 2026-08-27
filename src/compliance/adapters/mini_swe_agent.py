"""Adapter for SWE-agent/mini-swe-agent.

Recording category: A (framework creates + persists its own log).

Reconnaissance notes
--------------------
`DefaultAgent.run(task)` accumulates messages on `self.messages` and
auto-saves a trajectory JSON to `self.config.output_path` after every
loop iteration (the trajectory is written by `DefaultAgent.save`,
which runs inside `DefaultAgent.run`'s `finally` branch). The
framework therefore records durably during a normal agent invocation.

The trajectory already contains a `{"role": "exit", "extra": {...}}`
message appended by `DefaultAgent.run` when the loop terminates. The
adapter forwards that exit message into `Evidence.events` as
`kind="exit"`. The adapter does NOT synthesise an extra exit event.

Provenance
----------
Every event stamped on the Evidence bundle carries:

    origin     = SYSTEM_NATIVE
    producer   = "minisweagent.agents.default.DefaultAgent"
    collector  = "minisweagent_adapter_v1"

Extra metadata (v1.3 contract):

    recording_category        = "A"
    framework_persists_durably = True
    framework_artifact_paths  = (trajectory_path,)
    harness_artifact_paths    = ()
"""
from __future__ import annotations

import json
from pathlib import Path

from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    Scenario,
)

from .base import AdapterCapabilities, RepoAdapter

_COLLECTOR = "minisweagent_adapter_v1"
_PRODUCER = "minisweagent.agents.default.DefaultAgent"


# Trajectory message role -> normalised Evidence.kind.
_ROLE_KIND_MAP: dict[str, str] = {
    "user": "step",
    "assistant": "step",
    "tool": "tool",
    "exit": "exit",
}


class MiniSweAgentAdapter(RepoAdapter):
    name = "minisweagent"
    version = "1.1.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            python_version="3.12",
            needs_network=True,
            install_timeout_seconds=600,
            run_timeout_seconds=120,
            install_command="pip install -e .",
        )

    def resolve_agent(self, repo_root: str) -> str:
        return _PRODUCER

    def render_synthetic_task(self, scenario: Scenario) -> str:
        return scenario.user_prompt

    def parse_trajectory(self, trajectory_path: str, scenario: Scenario) -> Evidence:
        path = Path(trajectory_path)
        if not path.exists():
            return Evidence(
                schema_version=EVIDENCE_SCHEMA_VERSION,
                events=(),
                agent_class=_PRODUCER,
                agent_version="unknown",
                extra={
                    "reason": f"trajectory file missing: {trajectory_path}",
                    "recording_category": "A",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": (),
                    "harness_artifact_paths": (),
                    "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return Evidence(
                schema_version=EVIDENCE_SCHEMA_VERSION,
                events=(),
                agent_class=_PRODUCER,
                agent_version="unknown",
                extra={
                    "reason": f"trajectory parse error: {exc}",
                    "recording_category": "A",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": (),
                    "harness_artifact_paths": (),
                    "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        events: list[dict] = []
        messages = data.get("messages") or []
        for idx, msg in enumerate(messages):
            role = msg.get("role", "?")
            if role not in _ROLE_KIND_MAP:
                # System / unknown roles are not part of the article's
                # recorded-events assertion; skip them. The framework's
                # own loop emits only roles it knows about.
                continue
            kind = _ROLE_KIND_MAP[role]
            event: dict = {
                "kind": kind,
                "ts": "",
                "name": (
                    f"agent_exit:{msg.get('extra', {}).get('exit_status', '')}"
                    if role == "exit"
                    else f"message[{idx}]:{role}"
                ),
                "content": json.dumps(msg, sort_keys=True),
                "role": role,
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
                "type": "agent_message",
            }
            if role == "exit":
                extra = msg.get("extra") or {}
                event["exit_status"] = extra.get("exit_status", "")
                event["submission"] = extra.get("submission", "")
            events.append(event)

        info = data.get("info") or {}
        framework_persists = path.exists() and bool(messages)
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class=_PRODUCER,
            agent_version=str(info.get("mini_version", "")),
            extra={
                "recording_category": "A",
                "framework_persists_durably": framework_persists,
                "framework_artifact_paths": [str(path)] if framework_persists else [],
                "harness_artifact_paths": [],
                "trajectory_format": data.get("trajectory_format", ""),
                "model_stats": info.get("model_stats", {}),
                "exit_status": info.get("exit_status", ""),
                "scenario_id": scenario.scenario_id,
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
            },
        )
