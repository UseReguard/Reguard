"""Adapter for he-yufeng/CoreCoder.

Recording category: D (framework exposes only ephemeral in-memory state).

Reconnaissance notes
--------------------
CoreCoder does NOT auto-persist a trajectory. `Agent.messages` lives in
memory only and is the canonical execution record. During `Agent.chat`
the agent appends to `self.messages` on every round (user message,
assistant tool_calls, tool replies, final assistant message). That
list is the system's own execution record.

The list ends with the last assistant tool-call message; there is no
framework-emitted terminal event. Under v1.3 we do NOT synthesise a
terminal `exit` event. The harness writes the trajectory JSON itself,
which is why the persistent durable artifact is harness-side.

Provenance
----------
Every event stamped on the Evidence bundle carries:

    origin     = SYSTEM_STATE_EXPORTED_BY_HARNESS
    producer   = "corecoder.agent.Agent.messages"
    collector  = "corecoder_adapter_v1"

Extra metadata (v1.3 contract):

    recording_category         = "D"
    framework_persists_durably  = False
    framework_artifact_paths   = ()
    harness_artifact_paths     = (trajectory_path,)
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

_COLLECTOR = "corecoder_adapter_v1"
_PRODUCER = "corecoder.agent.Agent.messages"


# Trajectory message role -> normalised Evidence.kind.
_ROLE_KIND_MAP: dict[str, str] = {
    "user": "step",
    "assistant": "step",
    "tool": "tool",
}


class CoreCoderAdapter(RepoAdapter):
    name = "corecoder"
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
        return "corecoder.agent.Agent"

    def render_synthetic_task(self, scenario: Scenario) -> str:
        return scenario.user_prompt

    def parse_trajectory(self, trajectory_path: str, scenario: Scenario) -> Evidence:
        path = Path(trajectory_path)
        if not path.exists():
            return Evidence(
                schema_version=EVIDENCE_SCHEMA_VERSION,
                events=(),
                agent_class="corecoder.agent.Agent",
                agent_version="unknown",
                extra={
                    "reason": f"trajectory file missing: {trajectory_path}",
                    "recording_category": "D",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": [],
                    "harness_artifact_paths": [],
                    "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
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
                agent_class="corecoder.agent.Agent",
                agent_version="unknown",
                extra={
                    "reason": f"trajectory parse error: {exc}",
                    "recording_category": "D",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": [],
                    "harness_artifact_paths": [],
                    "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        events: list[dict] = []
        messages = data.get("messages") or []
        for idx, msg in enumerate(messages):
            role = msg.get("role", "?")
            if role not in _ROLE_KIND_MAP:
                continue
            kind = _ROLE_KIND_MAP[role]
            events.append({
                "kind": kind,
                "ts": "",
                "name": f"message[{idx}]:{role}",
                "content": json.dumps(msg, sort_keys=True),
                "role": role,
                "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
                "type": "agent_message",
            })

        # The durable trajectory JSON was written by the harness,
        # not by CoreCoder. The framework did not produce any
        # persistent artifact.
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class="corecoder.agent.Agent",
            agent_version=str(data.get("corecoder_version", "")),
            extra={
                "recording_category": "D",
                "framework_persists_durably": False,
                "framework_artifact_paths": [],
                "harness_artifact_paths": [str(path)] if path.exists() else [],
                "model": data.get("model", ""),
                "scenario_id": scenario.scenario_id,
                "final_response": data.get("final_response", ""),
                "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
            },
        )
