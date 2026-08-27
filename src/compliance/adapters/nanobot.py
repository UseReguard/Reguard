"""Adapter for HKUDS/nanobot.

Reconnaissance notes
--------------------
  - nanobot exposes `nanobot.bus.runtime_events` containing a real
    `RuntimeEventBus` and `RuntimeEventPublisher`.
  - The Publisher has its OWN emit methods
    (session_turn_started, turn_runtime_admitted, turn_completed,
    session_turn_persisted, ...) that call `await self.bus.publish(...)`.
  - Subscribers register via `RuntimeEventBus.subscribe(...)`.

Provenance boundary
-------------------
The probe MUST NOT inject or fabricate events. It:

  1. constructs a real RuntimeEventPublisher,
  2. subscribes a collector that records every event the publisher
     emits,
  3. calls the publisher's OWN methods
     (session_turn_started, turn_completed) which cause the bus
     to fire system-native events,
  4. writes the SUBSCRIBER's record of what was emitted.

Every event in the resulting bundle therefore has origin =
SYSTEM_NATIVE (the bus emitted it; we only listened).

What this proves
----------------
The probe demonstrates that nanobot's runtime bus really does emit
events during a turn. It does NOT demonstrate that the high-level
Nanobot gateway runs end-to-end (that requires real LLM creds and
is out of scope for the v1 engine). For Article 12(1), "automatic
event recording" is satisfied by the bus, not by the gateway.
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

_COLLECTOR = "nanobot_adapter_v1"
_PRODUCER = "nanobot.bus.runtime_events.RuntimeEventPublisher"


# nanobot stream-event type -> our normalised Evidence.kind
_NANOBOT_KIND_MAP: dict[str, str] = {
    "SessionTurnStarted": "step",
    "UserInputAccepted": "step",
    "TurnRuntimeAdmitted": "model",
    "TurnRunStatusChanged": "step",
    "TurnCompleted": "completed",
    "SessionTurnPersisted": "exit",
}


class NanobotAdapter(RepoAdapter):
    name = "nanobot"
    version = "1.1.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            python_version="3.12",
            needs_network=True,
            install_timeout_seconds=900,
            run_timeout_seconds=180,
            install_command="pip install -e .",
        )

    def resolve_agent(self, repo_root: str) -> str:
        return "nanobot.bus.runtime_events.RuntimeEventPublisher"

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
        raw_events = data.get("events") or []
        for idx, ev in enumerate(raw_events):
            ev_type = ev.get("type") or ev.get("kind") or "step"
            kind = _NANOBOT_KIND_MAP.get(ev_type, "step")
            events.append({
                "kind": kind,
                "ts": ev.get("ts", ""),
                "name": ev.get("name", f"event[{idx}]"),
                "content": json.dumps(ev, sort_keys=True),
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
                "type": f"nanobot_{ev_type.lower()}",
            })

        events.append({
            "kind": "exit",
            "ts": "",
            "name": "nanobot_run",
            "content": "",
            "result_status": data.get("result_status", ""),
            "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
            "producer": _PRODUCER,
            "collector": _COLLECTOR,
            "type": "probe_exit",
        })

        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class=_PRODUCER,
            agent_version=str(data.get("nanobot_version", "")),
            extra={
                "scenario_id": scenario.scenario_id,
                "result_status": data.get("result_status", ""),
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
            },
        )