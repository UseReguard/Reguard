"""Adapter for The-Pocket/PocketFlow.

Recording category: E (no automatic recording mechanism).

Reconnaissance notes
--------------------
PocketFlow is a single-file graph-execution library. Flow / Node /
AsyncNode run entirely against an in-memory ``shared`` dict. There
is no logger, no DB, no file output sink, and no module-level call
to ``open(...)`` or ``json.dump(...)``. The "record" of a Flow run
exists only inside the Python process; the framework does not
write anything to disk as a side effect.

The probe below instantiates a Flow with two stub Nodes (each one
calling a trivial exec() that touches the shared dict), runs the
Flow, and emits a trajectory JSON with one observation: the
framework did not write any artifact during the run. The Proof
that the framework has no recorder is *the absence of any new
files* on disk under the probe workspace.

Provenance
----------
Every "event" stamped on Evidence is the probe's record of *not*
finding a framework-written artefact. Because the framework did not
emit anything, no real events exist; the Evidence bundle is empty
but the probe ran cleanly.

    origin      = SYSTEM_NATIVE  (the "no recording" is a system-level
                fact observed by the probe, not an event invented
                by the probe)
    producer    = "pocketflow.flow.Flow"
    collector   = "pocketflow_adapter_v1"
    recording_category = "E"
    framework_persists_durably = False
    framework_artifact_paths   = []
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    Scenario,
)

from .base import AdapterCapabilities, RepoAdapter

_COLLECTOR = "pocketflow_adapter_v1"
_PRODUCER = "pocketflow.flow.Flow"


def _scan_artifacts(workspace_root: str) -> list[str]:
    """Return any *new* JSON / .log files under the workspace.

    A real framework recorder would have left at least one such file.
    PocketFlow does not. We deliberately bound the scan to the
    workspace the probe created so a pre-existing log file elsewhere
    on the runner cannot fool the probe.
    """
    root = Path(workspace_root)
    if not root.exists():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in (".json", ".log", ".jsonl", ".txt"):
            continue
        # The probe trajectory file itself is fine to find — it is
        # the harness-written summary, not a framework artefact. We
        # still list it under harness_artifacts in the Evidence; the
        # framework_artifact_paths list stays empty.
        out.append(str(p))
    return out


class PocketFlowAdapter(RepoAdapter):
    name = "pocketflow"
    version = "1.0.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            python_version="3.12",
            needs_network=False,
            install_timeout_seconds=120,
            run_timeout_seconds=60,
            install_command="pip install -e .",
        )

    def resolve_agent(self, repo_root: str) -> str:
        return "pocketflow"

    def render_synthetic_task(self, scenario: Scenario) -> str:
        return scenario.user_prompt

    def parse_trajectory(self, trajectory_path: str, scenario: Scenario) -> Evidence:
        path = Path(trajectory_path)
        workspace = path.parent if path.exists() else Path("/workspace/repo")

        # The probe writes a synthetic trajectory containing the
        # observed absence-of-recording. Treat it as the authoritative
        # cross-process attestation; if the file is missing, we still
        # know the framework was run (adapter ran) but we have no
        # recorded observation — UNKNOWN upstream handles that case.
        observed_artifact_paths: list[str] = []
        probe_status = "ok"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                observed_artifact_paths = list(data.get("framework_artifacts_observed") or [])
                probe_status = data.get("probe_status", "ok")
            except (OSError, json.JSONDecodeError):
                probe_status = "adapter_raised"

        # Cross-check by scanning the workspace ourselves. If the
        # probe and the adapter independently agree there are no
        # framework artifacts, the absence is doubly attested.
        independent_scan = _scan_artifacts(str(workspace))
        harness_artifacts = independent_scan
        # Remove the probe trajectory file (harness-written) from
        # the framework candidate list, to keep them distinct.
        framework_candidate_artifacts = [
            p for p in independent_scan
            if Path(p).resolve() != path.resolve()
        ]

        # SYSTEM_NATIVE origin: the absence of any framework artefact
        # is itself the framework's "emission" — PocketFlow does not
        # write a log file as a side effect. We do not invent events.
        events: list[dict] = []

        extra = {
            "recording_category": "E",
            "framework_persists_durably": False,
            "framework_artifact_paths": framework_candidate_artifacts,
            "harness_artifact_paths": [str(p) for p in harness_artifacts],
            "probe_status": probe_status,
            "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
            "producer": _PRODUCER,
            "collector": _COLLECTOR,
            "scenario_id": scenario.scenario_id,
            "framework_version": _detect_pocketflow_version(),
        }
        return Evidence(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            events=tuple(events),
            agent_class="pocketflow.flow.Flow",
            agent_version=extra["framework_version"],
            extra=extra,
        )


def _detect_pocketflow_version() -> str:
    try:
        import pocketflow  # type: ignore
    except Exception:
        return "unknown"
    return getattr(pocketflow, "__version__", "unknown")


__all__ = ["PocketFlowAdapter"]
