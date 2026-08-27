"""Adapter for HKUDS/nanobot.

Recording category: C (framework emits events but requires an external
recorder to persist them).

Reconnaissance notes
--------------------
nanobot exposes `nanobot.bus.runtime_events` containing a real
`RuntimeEventBus` and `RuntimeEventPublisher`. The Publisher has its
OWN emit methods (`session_turn_started`, `turn_runtime_admitted`,
`turn_completed`, `session_turn_persisted`, ...) that call
`await self.bus.publish(...)`. Subscribers register via
`RuntimeEventBus.subscribe(...)`.

The framework emits lifecycle events to the bus during a normal
turn but does not, by itself, persist them. Persistence is the
responsibility of whatever subscribers are registered. Reguard is
one such subscriber.

Under v1.3 we do NOT synthesise a terminal event. The framework's
own `TurnCompleted` event (kind="completed") satisfies the terminal
check on its own.

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
SYSTEM_NATIVE (the bus emitted it; we only listened). The harness
subscribes but does not persist; there is no framework-side
artifact written by nanobot itself.

Provenance metadata (v1.3 contract):

    recording_category         = "C"
    framework_persists_durably  = False
    framework_artifact_paths   = ()
    harness_artifact_paths     = (collector_record_path,)

The framework's automatic recording capability depends on an
external recorder (Reguard's subscriber). Reguard's stored
collector record is in `harness_artifact_paths`, not framework.
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


# nanobot stream-event type -> our normalised Evidence.kind.
# TurnCompleted -> "completed" satisfies TERMINAL_KIND_PRESENT.
_NANOBOT_KIND_MAP: dict[str, str] = {
    "SessionTurnStarted": "step",
    "UserInputAccepted": "step",
    "TurnRuntimeAdmitted": "model",
    "TurnRunStatusChanged": "step",
    "TurnCompleted": "completed",
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
                    "recording_category": "C",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": [],
                    "harness_artifact_paths": [],
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
                    "recording_category": "C",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": [],
                    "harness_artifact_paths": [],
                    "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        events: list[dict] = []
        raw_events = data.get("events") or []
        for idx, ev in enumerate(raw_events):
            ev_type = ev.get("type") or ev.get("kind") or "step"
            if ev_type not in _NANOBOT_KIND_MAP:
                # Skip event types the article contract is silent on.
                # The article contract does not define what counts as
                # a step/tool/model event beyond the kind set in the
                # RequirementTest.
                continue
            kind = _NANOBOT_KIND_MAP[ev_type]
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

        # No framework-side artefact. The collector's record was
        # written by Reguard, not nanobot.
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class=_PRODUCER,
            agent_version=str(data.get("nanobot_version", "")),
            extra={
                "recording_category": "C",
                "framework_persists_durably": False,
                "framework_artifact_paths": [],
                "harness_artifact_paths": [str(path)] if path.exists() else [],
                "scenario_id": scenario.scenario_id,
                "result_status": data.get("result_status", ""),
                "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
            },
        )
