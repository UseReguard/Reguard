"""Adapter for gptme/gptme.

Recording category: B (persistent / recoverable framework-side
session state).

Reconnaissance notes
--------------------
gptme's `LogManager` (gptme/logmanager/manager.py) writes each
conversation turn as a JSONL append-only log. The constructor
takes a log directory; each append produces one JSON-line record
(role, content, hash). The log file is durable across process
restarts (the on-disk format is what `ConversationSession` reloads
when the user reopens the session).

The probe below:

    1. Instantiates LogManager against a workspace-relative log
       directory.
    2. Writes two synthetic "turns" through the framework's
       append-only log API.
    3. Reads the log file back and emits one normalised event per
       turn.

The framework wrote the file; the harness only inspects it.

Provenance
----------
    origin     = SYSTEM_STATE_EXPORTED_BY_HARNESS
                 (the framework wrote the file; the harness reads
                  the file. Per the v1.3 contract this is
                  PASS-eligible for A/B categories.)
    producer   = "gptme.logmanager.LogManager"
    collector  = "gptme_adapter_v1"
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    Scenario,
)

from .base import AdapterCapabilities, RepoAdapter

_COLLECTOR = "gptme_adapter_v1"
_PRODUCER = "gptme.logmanager.LogManager"


_KIND_BY_ROLE = {
    "user": "step",
    "assistant": "model",
    "system": "step",
    "tool": "tool",
}


class GptMeAdapter(RepoAdapter):
    name = "gptme"
    version = "1.0.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            python_version="3.12",
            needs_network=False,
            install_timeout_seconds=600,
            run_timeout_seconds=120,
            install_command="",
        )

    def resolve_agent(self, repo_root: str) -> str:
        return "gptme.logmanager.manager.LogManager"

    def render_synthetic_task(self, scenario: Scenario) -> str:
        return scenario.user_prompt

    def parse_trajectory(self, trajectory_path: str, scenario: Scenario) -> Evidence:
        path = Path(trajectory_path)
        if not path.exists():
            return Evidence(
                schema_version=EVIDENCE_SCHEMA_VERSION,
                events=(),
                agent_class="gptme.logmanager.manager.LogManager",
                agent_version="unknown",
                extra={
                    "reason": f"trajectory file missing: {trajectory_path}",
                    "recording_category": "B",
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
                agent_class="gptme.logmanager.manager.LogManager",
                agent_version="unknown",
                extra={
                    "reason": f"trajectory parse error: {exc}",
                    "recording_category": "B",
                    "framework_persists_durably": False,
                    "framework_artifact_paths": [],
                    "harness_artifact_paths": [],
                    "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
                    "producer": _PRODUCER,
                    "collector": _COLLECTOR,
                },
            )

        log_file_path = data.get("log_file_path", "")
        turns = data.get("turns", [])
        framework_persists = bool(log_file_path and Path(log_file_path).exists())
        events = self._normalise_turns(turns)

        extra = {
            "recording_category": "B",
            "framework_persists_durably": framework_persists,
            "framework_artifact_paths": [log_file_path] if framework_persists else [],
            "harness_artifact_paths": [str(path)] if path.exists() else [],
            "scenario_id": scenario.scenario_id,
            "log_file_path": log_file_path,
            "session_id": data.get("session_id", ""),
            "log_size_bytes": data.get("log_size_bytes", 0),
            "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
            "producer": _PRODUCER,
            "collector": _COLLECTOR,
        }
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class="gptme.logmanager.manager.LogManager",
            agent_version=str(data.get("gptme_version", "")),
            extra=extra,
        )

    @staticmethod
    def _normalise_turns(turns: list[dict]) -> list[dict]:
        out: list[dict] = []
        for idx, turn in enumerate(turns):
            role = (turn.get("role") or "?").lower()
            kind = _KIND_BY_ROLE.get(role, "step")
            out.append({
                "kind": kind,
                "ts": str(turn.get("ts", "")),
                "name": f"turn[{idx}]:{role}",
                "content": json.dumps(_scrub(turn), sort_keys=True),
                "role": role,
                "origin": EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value,
                "producer": _PRODUCER,
                "collector": _COLLECTOR,
                "type": "logmanager_turn",
            })
        return out


def _scrub(obj: Any) -> Any:
    """Drop any non-JSON-serialisable fields before stuffing turn content
    into Evidence.content."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if _scrub_key(k)}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


_SKIP_KEYS = {"hash", "tokens"}  # gptme may set volatile / oversize fields


def _scrub_key(k: str) -> bool:
    return k not in _SKIP_KEYS


__all__ = ["GptMeAdapter"]
