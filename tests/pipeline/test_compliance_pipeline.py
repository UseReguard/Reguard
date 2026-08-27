"""Tests for compliance_pipeline.

This suite is the v1.3 synthetic test set: each test names a known shape
of input and pins the expected output. The point is to lock the
behaviour of the Article 12(1) v1.3 contract, the A-E category
verdict map, the adapters, and the persistence layer.

Cases
-----
T01  PASS — category A, step + tool + framework-emitted exit
T02  FAIL — category A but no terminal event
T03  FAIL — category A but only steps, no terminal
T04  UNKNOWN — empty event list (handled upstream; here re-produced)
T05  ERROR — schema_version mismatch
T06  FAIL — category B without framework_persists_durably flag set
T07  FAIL — HARNESS_GENERATED event present (hard boundary)
T08  FAIL — HARNESS_GENERATED on the step event
T09  PASS — multiple tools same kind, all SYSTEM_NATIVE, category A
T10  PASS — adapter parser: mini-swe-agent fixture (SYSTEM_NATIVE, A)
T11  PASS — adapter parser: CoreCoder fixture (D)
T12  PASS — adapter parser: nanobot fixture (C, framework's
     TurnCompleted is the terminal event)
T13  PASS — registry exposes Article121 at v1.3.0
T14  PASS — persistence roundtrip + dedup, category A
T15  PASS — probe_status='ok' fall-through, category C is FAIL
T16  PASS — load_run_by_dedup_key roundtrip, category D
T17  FAIL — category C: framework emits events but no automatic
     recording. harness persists; framework does not. Verdict FAIL.
T18  FAIL — category D: framework has only ephemeral state;
     no terminal event exists; verdict FAIL.
T19  FAIL — category E with framework observed recording
     contradiction; verdict FAIL with detail.
T20  FAIL — category E with absence observable (some non-eligible
     events, no framework artefact); verdict FAIL.
T21  PASS — category B with framework_persists_durably True and
     eligible events (e.g. session state).
T22  PASS — A-E category map: probe_status short-circuit still
     yields ERROR regardless of category.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.adapters import get_adapter
from compliance.pipeline.persistence import insert_run, load_run_by_dedup_key
from compliance.requirements.ai_act.article_12_1 import (
    Article121AutomaticLoggingTest,
)
from compliance.requirements.base import (
    REQUIREMENT_REGISTRY,
    get_requirement,
)
from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    RepositoryTarget,
    Result,
    RunRecord,
    RunStatus,
)
from compliance.pipeline.driver import (
    DEFAULT_SCENARIO_12_1,
    list_registered_requirements,
)


_REQ = Article121AutomaticLoggingTest()

NATIVE = EvidenceOrigin.SYSTEM_NATIVE.value
EXPORTED = EvidenceOrigin.SYSTEM_STATE_EXPORTED_BY_HARNESS.value
GENERATED = EvidenceOrigin.HARNESS_GENERATED.value


def _ev(events: list[dict], category: str = "A", **extra) -> Evidence:
    """Build an Evidence bundle. Events default to SYSTEM_NATIVE.

    `category` and any further keys go into `extra`. The Category
    default is A; tests that exercise other categories pass it
    explicitly.
    """
    normalised = []
    for e in events:
        if "origin" not in e:
            e = {**e, "origin": NATIVE}
        normalised.append(e)
    merged_extra = {
        "recording_category": category,
        "framework_persists_durably": category in ("A", "B"),
        "framework_artifact_paths": ["/fake/framework/artifact.json"]
        if category in ("A", "B")
        else [],
        "harness_artifact_paths": ["/fake/harness/artifact.json"]
        if category in ("C", "D")
        else [],
    }
    merged_extra.update(extra)
    return Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=tuple(normalised),
        agent_class="probe.Agent",
        agent_version="1.0.0",
        extra=merged_extra,
    )


def _ev_step_tool_exit(category: str = "A") -> Evidence:
    return _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "tool", "ts": "t2", "name": "bash", "content": "ls"},
        {"kind": "exit", "ts": "t3", "name": "agent", "content": "",
         "exit_status": "submitted"},
    ], category=category)


def _ev_step_tool_completed() -> Evidence:
    return _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "tool", "ts": "t2", "name": "bash", "content": "ls"},
        {"kind": "completed", "ts": "t3", "name": "turn",
         "result_status": "ok"},
    ], category="B")


# ----- T01 -----
def test_t01_pass_full_path_category_a():
    record = _ev_step_tool_exit(category="A")
    result = _REQ.evaluate(record)
    assert result.status == RunStatus.PASS, result.reason
    assert all(c["passed"] for c in result.checks)


# ----- T02 -----
def test_t02_fail_category_a_missing_terminal():
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "tool", "ts": "t2", "name": "bash", "content": "ls"},
    ], category="A")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed_names = {c["name"] for c in result.checks if not c["passed"]}
    assert "TERMINAL_KIND_PRESENT" in failed_names


# ----- T03 -----
def test_t03_fail_category_a_only_steps():
    ev = _ev([{"kind": "step", "ts": "t1", "name": "x"}], category="A")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "TERMINAL_KIND_PRESENT" in failed


# ----- T04 -----
def test_t04_unknown_empty_events():
    ev = _ev([], category="A")
    result = _REQ.evaluate(ev)
    # Empty event list maps to UNKNOWN in the base class.
    assert result.status == RunStatus.UNKNOWN


# ----- T05 -----
def test_t05_error_schema_mismatch():
    ev = Evidence(
        schema_version="999",
        events=(
            {"kind": "step", "origin": NATIVE},
            {"kind": "exit", "origin": NATIVE},
        ),
        agent_class="x",
        agent_version="x",
        extra={"recording_category": "A"},
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR


# ----- T06 -----
def test_t06_fail_category_b_without_persists_flag():
    """Category B is PASS-eligible only when the framework's own
    state is recoverable. If the adapter forgot to set
    framework_persists_durably, the contract flags it as FAIL.
    """
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "completed", "ts": "t2", "name": "turn"},
    ], category="B", framework_persists_durably=False,
       framework_artifact_paths=[])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed_names = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_FRAMEWORK_PERSISTS" in failed_names


# ----- T07 -----
def test_t07_fail_harness_generated_on_terminal():
    ev = _ev([
        {"kind": "step", "origin": NATIVE},
        {"kind": "exit", "origin": GENERATED, "exit_status": "fake"},
    ], category="A")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "NO_HARNESS_GENERATED_EVENTS" in failed


# ----- T08 -----
def test_t08_fail_harness_generated_on_step():
    ev = _ev([
        {"kind": "step", "origin": GENERATED},
        {"kind": "exit", "origin": NATIVE, "exit_status": "ok"},
    ], category="A")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "NO_HARNESS_GENERATED_EVENTS" in failed
    assert "STEP_OR_TOOL_KIND_PRESENT" in failed


# ----- T09 -----
def test_t09_pass_multiple_tools_same_kind_category_a():
    ev = _ev([
        {"kind": "tool", "origin": NATIVE, "name": "bash"},
        {"kind": "tool", "origin": NATIVE, "name": "edit"},
        {"kind": "completed", "origin": NATIVE, "name": "turn"},
    ], category="A")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


# ----- T10 -----
def test_t10_minisweagent_parser_category_a(tmp_path: Path):
    """Fixture includes a role=exit message (DefaultAgent.run emits
    one). The adapter forwards it as kind=exit. No synthetic event.
    """
    traj = tmp_path / "trajectory.json"
    traj.write_text(json.dumps({
        "info": {
            "model_stats": {"instance_cost": 0.0, "api_calls": 1},
            "mini_version": "1.0.0",
            "exit_status": "submitted",
        },
        "messages": [
            {"role": "system", "content": "you are a probe"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "exit", "extra": {"exit_status": "submitted", "submission": ""}},
        ],
        "trajectory_format": "mini-swe-agent-1.1",
    }))
    adapter = get_adapter("SWE-agent/mini-swe-agent")
    ev = adapter.parse_trajectory(str(traj), DEFAULT_SCENARIO_12_1)
    assert "DefaultAgent" in ev.agent_class
    kinds = [e["kind"] for e in ev.events]
    assert "step" in kinds
    assert "exit" in kinds
    # All events are SYSTEM_NATIVE.
    assert all(e["origin"] == NATIVE for e in ev.events)
    # Category A metadata is set by the adapter.
    assert ev.extra["recording_category"] == "A"
    assert ev.extra["framework_persists_durably"] is True
    assert str(traj) in ev.extra["framework_artifact_paths"]
    assert ev.extra["harness_artifact_paths"] == []
    # The synthesis-free contract: the ONLY exit-kind event is the
    # framework's role=exit message. Number of events = number of
    # forwardable messages, no +1.
    assert len(ev.events) == len([
        m for m in json.loads(traj.read_text())["messages"]
        if m.get("role") in {"user", "assistant", "exit"}
    ])


# ----- T11 -----
def test_t11_corecoder_parser_category_d(tmp_path: Path):
    traj = tmp_path / "trajectory.json"
    traj.write_text(json.dumps({
        "model": "fake-probe",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        "final_response": "ok",
        "corecoder_version": "0.0.1",
    }))
    adapter = get_adapter("he-yufeng/CoreCoder")
    ev = adapter.parse_trajectory(str(traj), DEFAULT_SCENARIO_12_1)
    assert "Agent" in ev.agent_class
    kinds = [e["kind"] for e in ev.events]
    assert "step" in kinds
    # CoreCoder framework has no terminal event. Adapter does NOT
    # synthesise one.
    assert "exit" not in kinds
    assert "completed" not in kinds
    assert all(e["origin"] == EXPORTED for e in ev.events)
    # Category D + harness-side persistence.
    assert ev.extra["recording_category"] == "D"
    assert ev.extra["framework_persists_durably"] is False
    assert ev.extra["framework_artifact_paths"] == []
    assert str(traj) in ev.extra["harness_artifact_paths"]


# ----- T12 -----
def test_t12_nanobot_parser_category_c(tmp_path: Path):
    traj = tmp_path / "trajectory.json"
    traj.write_text(json.dumps({
        "events": [
            {"type": "SessionTurnStarted", "ts": "t1", "name": "r"},
            {"type": "UserInputAccepted", "ts": "t2", "name": "r"},
            {"type": "TurnCompleted", "ts": "t3", "name": "r"},
        ],
        "result_status": "ok",
        "nanobot_version": "0.3.0",
    }))
    adapter = get_adapter("HKUDS/nanobot")
    ev = adapter.parse_trajectory(str(traj), DEFAULT_SCENARIO_12_1)
    kinds = [e["kind"] for e in ev.events]
    # SessionTurnStarted/UserInputAccepted -> step; TurnCompleted ->
    # completed. NO synthetic exit is appended.
    assert "step" in kinds
    assert "completed" in kinds
    assert "exit" not in kinds
    assert all(e["origin"] == NATIVE for e in ev.events)
    # Category C: harness persists, framework emits.
    assert ev.extra["recording_category"] == "C"
    assert ev.extra["framework_persists_durably"] is False
    assert ev.extra["framework_artifact_paths"] == []
    assert str(traj) in ev.extra["harness_artifact_paths"]


# ----- T13 -----
def test_t13_registry_exposes_article_121_v1_3():
    req_ids = list_registered_requirements()
    assert "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING" in req_ids
    r = get_requirement("AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING")
    assert r.id == "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
    assert r.version  # non-empty
    assert r.version == "1.3.0"


# ----- T14 -----
def test_t14_persistence_roundtrip_and_dedup_category_a(tmp_path: Path):
    db_path = tmp_path / "test.db"
    schema_sql = (ROOT / "migrations" / "005_compliance_runtime_runs.sql").read_text()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    evidence = _ev_step_tool_exit(category="A")
    result = _REQ.evaluate(evidence)
    record = RunRecord(
        repository=RepositoryTarget(
            repository_id=999, full_name="owner/test", sha="abc123", branch="main"
        ),
        requirement_id=_REQ.id,
        requirement_version=_REQ.version,
        runtime_version="1.0.0",
        adapter_name="test",
        adapter_version="1.0.0",
        scenario_id="test",
        status=result.status,
        reason=result.reason,
        result=result,
        evidence=evidence,
        started_at="2026-08-27T00:00:00Z",
        completed_at="2026-08-27T00:00:01Z",
        duration_seconds=1.0,
    )
    rid = insert_run(db_path, record)
    assert rid > 0

    with pytest.raises(sqlite3.IntegrityError):
        insert_run(db_path, record)

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM compliance_runtime_runs WHERE id = ?", (rid,)
        ).fetchone()
        assert row["status"] == "PASS"
        ev_loaded = json.loads(row["evidence_json"])
        assert ev_loaded["schema_version"] == EVIDENCE_SCHEMA_VERSION
        assert ev_loaded["events"][0]["origin"] == NATIVE
        result_loaded = json.loads(row["result_json"])
        assert result_loaded["schema_version"] == "2"
    finally:
        conn.close()


# ----- T15 -----
def test_t15_probe_status_short_circuits_to_error():
    ev = _ev([], probe_status="probe_failed", probe_returncode=1)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "probe_failed" in result.reason


# ----- T16 -----
def test_t16_load_run_by_dedup_key_roundtrip_category_d(tmp_path: Path):
    db_path = tmp_path / "test.db"
    schema_sql = (ROOT / "migrations" / "005_compliance_runtime_runs.sql").read_text()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    evidence = _ev([
        {"kind": "step", "ts": "t1", "name": "x", "origin": EXPORTED},
    ], category="D")
    result = _REQ.evaluate(evidence)
    record = RunRecord(
        repository=RepositoryTarget(
            repository_id=999, full_name="owner/test", sha="abc123", branch="main"
        ),
        requirement_id=_REQ.id,
        requirement_version=_REQ.version,
        runtime_version="1.0.0",
        adapter_name="test",
        adapter_version="1.0.0",
        scenario_id="test",
        status=result.status,
        reason=result.reason,
        result=result,
        evidence=evidence,
        started_at="2026-08-27T00:00:00Z",
        completed_at="2026-08-27T00:00:01Z",
        duration_seconds=1.0,
    )
    rid = insert_run(db_path, record)
    assert rid > 0

    loaded = load_run_by_dedup_key(
        db_path,
        repository_id=record.repository.repository_id,
        requirement_id=record.requirement_id,
        requirement_version=record.requirement_version,
        repo_sha=record.repository.sha,
        scenario_id=record.scenario_id,
        adapter_name=record.adapter_name,
        adapter_version=record.adapter_version,
    )
    assert loaded is not None
    assert loaded.status == RunStatus.FAIL
    assert loaded.evidence.extra["recording_category"] == "D"


# ----- T17 -----
def test_t17_category_c_non_pass():
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "turn_started"},
        {"kind": "completed", "ts": "t2", "name": "turn_completed"},
    ], category="C")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_C" in failed


# ----- T18 -----
def test_t18_category_d_non_pass_no_terminal():
    """CoreCoder-shaped evidence: only step-kind events, no
    framework-side terminal signal. Category D verdict is FAIL."""
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "user"},
        {"kind": "step", "ts": "t2", "name": "assistant"},
    ], category="D")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_D" in failed


# ----- T19 -----
def test_t19_category_e_with_observable_contradiction_is_fail():
    """Adapter declared E but evidence shows eligible events.
    The contradiction is itself a contract violation -> FAIL."""
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "x", "origin": NATIVE},
        {"kind": "completed", "ts": "t2", "name": "y", "origin": NATIVE},
    ], category="E")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL


# ----- T20 -----
def test_t20_category_e_absence_observable_is_fail():
    """Adapter declared E; only non-eligible events present; no
    framework artefact. Absence is observable -> FAIL."""
    ev = _ev([
        # kind="error" events are excluded from non-error counts but
        # still count toward events list size; the assertion evaluates
        # AT_LEAST_ONE_EVENT after stripping errors.
        {"kind": "error", "ts": "t1", "name": "noise", "origin": NATIVE},
    ], category="E")
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL


# ----- T21 -----
def test_t21_category_b_persistent_session_state_is_pass():
    """Category B: framework has recoverable session state. As long
    as the framework_persists_durably flag is set and kinds are
    right, PASS."""
    ev = _ev_step_tool_completed()
    # _ev_step_tool_completed uses category="B" already and sets
    # framework_persists_durably=True through _ev()'s default.
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


# ----- T22 -----
def test_t22_probe_status_short_circuit_independent_of_category():
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "x", "origin": NATIVE},
    ], category="A", probe_status="adapter_raised", probe_returncode=0)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "adapter_raised" in result.reason
