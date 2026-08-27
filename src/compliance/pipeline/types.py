"""Frozen dataclasses describing one compliance pipeline run.

These are the values the orchestrator, the adapter, and the requirement
test pass around. They are deliberately small, immutable, and JSON-safe
so they can be persisted directly into compliance_runtime_runs without
further translation.

Schema versions are pinned so a future change can be detected.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

# Pinned schema versions. Bump when an evidence or result field changes
# in a way that is not backward compatible.
EVIDENCE_SCHEMA_VERSION = "2"
RESULT_SCHEMA_VERSION = "2"


class EvidenceOrigin(str, Enum):
    """Provenance of one event in an Evidence bundle.

    The compliance decision must never treat an event as evidence
    of system behaviour unless the event was either produced by
    the agent system itself, or exported from state that the agent
    system itself populated. The harness writing the evidence
    artifact is fine; the harness inventing the underlying event
    is not.

    Stamped on every event dict by the adapter. See the Article 12(1)
    requirement test for the eligibility rule.
    """

    SYSTEM_NATIVE = "SYSTEM_NATIVE"
    """Event was emitted by the agent system itself during normal
    execution (e.g. DefaultAgent auto-saves a trajectory; the bus
    fires a TOOL_COMPLETED event). The harness only collects."""

    SYSTEM_STATE_EXPORTED_BY_HARNESS = "SYSTEM_STATE_EXPORTED_BY_HARNESS"
    """Event was reconstructed from a state container that the
    agent system itself populated as a side effect of running
    (e.g. CoreCoder.Agent.messages). The harness exports the
    record; the system created it. Eligible for PASS."""

    HARNESS_GENERATED = "HARNESS_GENERATED"
    """Event was synthesised by the probe / harness and does NOT
    reflect anything the agent system did on its own. NEVER
    eligible for PASS. Article 12(1) rejects this."""


class RunStatus(str, Enum):
    """Deterministic compliance verdict for one requirement against one repo.

    Stored verbatim in compliance_runtime_runs.status.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"

    @classmethod
    def parse(cls, raw: str) -> "RunStatus":
        try:
            return cls(raw)
        except ValueError as exc:
            raise ValueError(f"invalid run status: {raw!r}") from exc


@dataclass(frozen=True)
class Scenario:
    """The controlled stimulus fed to the agent under test.

    The same scenario is replayed identically for every repository;
    adapters are expected to translate it into whatever the agent's
    native task format is.
    """

    scenario_id: str
    user_prompt: str
    expected_tool_calls: tuple[str, ...] = ()
    """Tool names we expect to observe during the run, in order.

    Empty tuple means "do not require a specific sequence, just observe
    some events". The requirement test interprets this as either:
      - having at least one observed event of any kind, or
      - having all named tools called, depending on the requirement.
    """
    max_steps: int = 4


@dataclass(frozen=True)
class RepositoryTarget:
    """What the orchestrator needs to know about a target repo."""

    repository_id: int
    full_name: str            # "owner/name"
    sha: str
    branch: str = "main"


@dataclass(frozen=True)
class Evidence:
    """What the probe collected from inside the runtime container.

    The requirement test inspects only this object. Adapters translate
    whatever the agent's native log format is into one of these.
    """

    schema_version: str
    events: tuple[dict, ...] = ()
    """Sequence of normalised runtime events. Each event dict contains at
    minimum: kind (one of step/tool/model/exit/error), ts (ISO8601),
    name (optional tool or model name), content (optional raw body)."""

    agent_class: str = ""
    agent_version: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class Result:
    """What the requirement test decided about one piece of evidence."""

    schema_version: str
    status: RunStatus
    reason: str
    """Human-readable deterministic description of WHY this status was
    reached. Always set; never blank."""
    checks: tuple[dict, ...] = ()
    """List of {name: str, passed: bool, detail: str}. The full
    decision trace."""
    summary: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class RunRecord:
    """One full pipeline run, ready to persist."""

    repository: RepositoryTarget
    requirement_id: str
    requirement_version: str
    runtime_version: str
    adapter_name: str
    adapter_version: str
    scenario_id: str
    status: RunStatus
    reason: str
    result: Result
    evidence: Evidence
    started_at: str            # ISO8601 UTC
    completed_at: str          # ISO8601 UTC
    duration_seconds: float

    def result_json(self) -> str:
        return self.result.to_json()

    def evidence_json(self) -> str:
        return self.evidence.to_json()


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses / enums into JSON-safe primitives."""
    if hasattr(obj, "to_json") and callable(obj.to_json):
        return json.loads(obj.to_json())
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj