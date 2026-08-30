"""Tests for the observation_quality generic dispatch in the base class.

These tests verify Blocker 1 of the Gate 3 resolution: empty events
with positive observed absence must dispatch to ``assert_evidence``
so a requirement can produce a deterministic FAIL, while empty
events without the marker must continue to map to UNKNOWN. The
generic base class is not permitted to encode requirement-specific
logic; only the marker dispatch is exercised here.

Required cases:
  1. category=E + probe_status=ok + observation_quality=observed_absence
     + events=[]                -> FAIL
  2. probe_status=ok + observation_quality absent (indeterminate)
     + events=[]                -> UNKNOWN
  3. probe_status != ok        -> ERROR (regardless of events / marker)
  4. existing A/B/C/D behaviour unchanged
  5. no synthetic event is introduced on the observed_absence path
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    RunStatus,
)
from compliance.requirements.ai_act.article_12_1 import (
    Article121AutomaticLoggingTest,
)
from compliance.requirements.base import (
    RequirementTest,
    CheckResult,
)
from compliance.adapters.pocketflow import PocketFlowAdapter


_REQ = Article121AutomaticLoggingTest()
NATIVE = EvidenceOrigin.SYSTEM_NATIVE.value
EXPORTED = EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value


def _ev(
    events: list[dict],
    category: str = "E",
    *,
    probe_status: str | None = "ok",
    observation_quality: str | None = None,
    **extra,
) -> Evidence:
    """Build an Evidence bundle.

    Defaults are chosen to reproduce the PocketFlow-shaped empty
    bundle: probe ran cleanly, no events, category=E. Tests override
    what they need.
    """
    normalised = []
    for e in events:
        if "origin" not in e:
            e = {**e, "origin": NATIVE}
        normalised.append(e)
    merged_extra: dict = {
        "recording_category": category,
        "framework_persists_durably": category in ("A", "B"),
        "framework_artifact_paths": [],
        "harness_artifact_paths": [],
    }
    if probe_status is not None:
        merged_extra["probe_status"] = probe_status
    if observation_quality is not None:
        merged_extra["observation_quality"] = observation_quality
    merged_extra.update(extra)
    return Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=tuple(normalised),
        agent_class="probe.Agent",
        agent_version="1.0.0",
        extra=merged_extra,
    )


# ---------------------------------------------------------------------------
# Case 1 — observed_absence + empty events + category=E -> FAIL
# ---------------------------------------------------------------------------
def test_observed_absence_empty_events_category_e_is_fail():
    ev = _ev(
        events=[],
        category="E",
        observation_quality="observed_absence",
        probe_status="ok",
    )
    assert len(ev.events) == 0
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL, result.reason
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_E_NON_PASS" in failed
    # The base class recognises the marker and forwards to assert_evidence
    # without inventing a synthetic event.
    assert result.summary.get("observation_quality") == "observed_absence"
    assert result.summary.get("event_count") == 0


# ---------------------------------------------------------------------------
# Case 2 — indeterminate observation + empty events -> UNKNOWN
# ---------------------------------------------------------------------------
def test_indeterminate_empty_events_is_unknown():
    # No observation_quality marker at all -> base class keeps UNKNOWN.
    ev = _ev(
        events=[],
        category="E",
        probe_status="ok",
        observation_quality=None,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.UNKNOWN, result.reason
    assert result.summary.get("event_count") == 0


def test_indeterminate_explicit_empty_events_is_unknown():
    # Explicit "indeterminate" must behave the same as absent.
    ev = _ev(
        events=[],
        category="E",
        probe_status="ok",
        observation_quality="indeterminate",
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.UNKNOWN, result.reason


# ---------------------------------------------------------------------------
# Case 3 — probe_status != "ok" -> ERROR (before any event/marker logic)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_status",
    ["probe_failed", "adapter_raised", "unsupported", "container_error"],
)
def test_probe_not_ok_is_error_regardless_of_marker(bad_status):
    # Even with observed_absence set, a non-ok probe must short-circuit
    # to ERROR — the marker only relaxes the empty-events branch, never
    # the probe-cleanliness gate.
    ev = _ev(
        events=[],
        category="E",
        probe_status=bad_status,
        observation_quality="observed_absence",
        probe_returncode=1,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert bad_status in result.reason


# ---------------------------------------------------------------------------
# Case 4 — A/B/C/D behaviour unchanged when events are present
# ---------------------------------------------------------------------------
def test_category_a_full_path_still_passes():
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "plan"},
            {"kind": "tool", "ts": "t2", "name": "bash"},
            {"kind": "exit", "ts": "t3", "name": "agent", "exit_status": "submitted"},
        ],
        category="A",
        framework_persists_durably=True,
        framework_artifact_paths=["/fake/framework.json"],
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


def test_category_b_persistent_state_still_passes():
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "plan"},
            {"kind": "completed", "ts": "t2", "name": "turn"},
        ],
        category="B",
        framework_persists_durably=True,
        framework_artifact_paths=["/fake/session.json"],
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


def test_category_c_still_fails():
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "turn_started"},
            {"kind": "completed", "ts": "t2", "name": "turn_completed"},
        ],
        category="C",
        framework_persists_durably=False,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_C" in failed


def test_category_d_still_fails():
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "user"},
            {"kind": "step", "ts": "t2", "name": "assistant"},
        ],
        category="D",
        framework_persists_durably=False,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_D" in failed


def test_category_e_with_events_present_still_fails():
    """E + non-empty events is the contradiction case the requirement
    already handles. The new observed_absence dispatch must not change
    it."""
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "x"},
            {"kind": "completed", "ts": "t2", "name": "y"},
        ],
        category="E",
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL


# ---------------------------------------------------------------------------
# gptme-shaped regression — category B without terminal event is PASS
# ---------------------------------------------------------------------------
def test_category_b_gptme_shaped_without_terminal_is_pass_v1_4():
    """gptme's runtime evidence shape:
    category=B, framework_persists_durably=True, non-empty
    framework_artifact_paths, eligible runtime events present,
    NO exit/completed event. v1.4.0 contract: PASS."""
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "turn[0]:user", "origin": EXPORTED},
            {"kind": "model", "ts": "t2", "name": "turn[1]:assistant", "origin": EXPORTED},
        ],
        category="B",
        framework_persists_durably=True,
        framework_artifact_paths=["/workspace/probe/framework_conversation.jsonl"],
        harness_artifact_paths=[],
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS, result.reason
    # No TERMINAL_KIND_PRESENT check should exist in v1.4.0.
    check_names = {c["name"] for c in result.checks}
    assert "TERMINAL_KIND_PRESENT" not in check_names


# ---------------------------------------------------------------------------
# Case 5 — no synthetic event is introduced on the observed_absence path
# ---------------------------------------------------------------------------
def test_pocketflow_adapter_emits_zero_events_with_observed_absence(tmp_path: Path):
    """The PocketFlow adapter must not pad the events list to make the
    base class happy. We simulate a clean probe trajectory (no
    framework artefacts observed) and confirm the adapter returns an
    empty events tuple plus the observed_absence marker.
    """
    traj = tmp_path / "trajectory.json"
    traj.write_text(
        '{"probe_status": "ok", "framework_artifacts_observed": []}'
    )

    from compliance.pipeline.types import Scenario
    scenario = Scenario(scenario_id="test-pocketflow", user_prompt="run flow")
    adapter = PocketFlowAdapter()
    ev = adapter.parse_trajectory(str(traj), scenario)
    assert ev.events == ()
    assert ev.extra["observation_quality"] == "observed_absence"
    assert ev.extra["recording_category"] == "E"
    assert ev.extra["framework_persists_durably"] is False


def test_pocketflow_adapter_drops_to_indeterminate_when_artefacts_observed(
    tmp_path: Path,
):
    """If the probe did observe framework-written artefacts, the
    adapter must not stamp observed_absence — the runtime did emit
    something and the contradiction should fall through to
    assert_evidence on the non-empty branch."""
    traj = tmp_path / "trajectory.json"
    traj.write_text(
        '{"probe_status": "ok", '
        '"framework_artifacts_observed": ["/tmp/PocketFlow/agent.log"]}'
    )
    # Also drop a matching file in the workspace so the cross-check
    # scan finds it; without this the scan would invalidate the
    # adapter's own list and force observation_quality back to
    # "indeterminate" via the cross-check rule.
    workspace = tmp_path / "framework_artefact.json"
    workspace.write_text("{}")
    # Re-point the trajectory file path so workspace = traj.parent.
    from compliance.pipeline.types import Scenario
    scenario = Scenario(scenario_id="test-pocketflow", user_prompt="run flow")
    adapter = PocketFlowAdapter()
    ev = adapter.parse_trajectory(str(traj), scenario)
    # Even if the probe reports an artefact, the bundle should not
    # carry the observed_absence marker (so the empty-events branch
    # is not falsely entered) — but here we have non-empty candidate
    # artefacts so observation_quality must be "indeterminate" by the
    # cross-check rule.
    assert ev.extra["observation_quality"] == "indeterminate"


# ---------------------------------------------------------------------------
# Generic RequirementTest — verify the new branch lives in the base
# class and is requirement-agnostic. A minimal stub test is used.
# ---------------------------------------------------------------------------
class _ObservedAbsenceStub(RequirementTest):
    id = "STUB_OBSERVED_ABSENCE"
    version = "0.0.1"

    def assert_evidence(self, evidence):
        # If dispatched, FAIL. This proves the dispatch happens.
        yield CheckResult(
            name="STUB_REACHED",
            passed=False,
            detail="base class dispatched empty observed_absence bundle",
        )


def test_generic_base_dispatches_observed_absence_to_assert_evidence():
    stub = _ObservedAbsenceStub()
    ev = Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=(),
        agent_class="x",
        agent_version="1.0.0",
        extra={
            "probe_status": "ok",
            "observation_quality": "observed_absence",
        },
    )
    result = stub.evaluate(ev)
    assert result.status == RunStatus.FAIL
    names = {c["name"] for c in result.checks}
    assert "STUB_REACHED" in names


def test_generic_base_keeps_unknown_when_marker_absent():
    stub = _ObservedAbsenceStub()
    ev = Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=(),
        agent_class="x",
        agent_version="1.0.0",
        extra={"probe_status": "ok"},
    )
    result = stub.evaluate(ev)
    assert result.status == RunStatus.UNKNOWN
    assert result.checks == ()
