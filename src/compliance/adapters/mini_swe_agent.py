"""Adapter for SWE-agent/mini-swe-agent.

Reconnaissance notes
--------------------
  - `DefaultAgent.run(task)` accumulates messages on self.messages
    and auto-saves a trajectory JSON to `self.config.output_path`
    after every step (DefaultAgent.run calls self.save() in its
    `finally` clause, line 121 of agents/default.py).
  - The trajectory file is therefore written by the agent system
    itself, not by the probe. Origin is SYSTEM_NATIVE.
  - We use `DeterministicModel` (test_models.py) so no API key is
    needed.

Provenance
----------
Every event stamped on the Evidence bundle carries:

    origin     = SYSTEM_NATIVE
    producer   = "minisweagent.agents.default.DefaultAgent"
    collector  = "minisweagent_adapter_v1"

The harness only reads the file; the agent wrote it.
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
        # The task itself is small and deterministic. mini-swe-agent
        # has its own system_template but for this probe we just feed
        # a literal task.
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
                    "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        events: list[dict] = []
        messages = data.get("messages") or []
        for idx, msg in enumerate(messages):
            role = msg.get("role", "?")
            events.append({
                "kind": "step",
                "ts": "",
                "name": f"message[{idx}]",
                "content": json.dumps(msg, sort_keys=True),
                "role": role,
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
                "type": "agent_step",
            })

        exit_status = (data.get("info") or {}).get("exit_status", "")
        events.append({
            "kind": "exit",
            "ts": "",
            "name": "agent_run",
            "content": "",
            "exit_status": exit_status,
            "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
            "producer": _PRODUCER,
            "collector": _COLLECTOR,
            "type": "agent_exit",
        })

        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class=_PRODUCER,
            agent_version=str(data.get("info", {}).get("mini_version", "")),
            extra={
                "trajectory_format": data.get("trajectory_format", ""),
                "model_stats": data.get("info", {}).get("model_stats", {}),
                "scenario_id": scenario.scenario_id,
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
            },
        )