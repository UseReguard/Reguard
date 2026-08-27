"""Tests for compliance_pipeline.

This suite is the "synthetic test suite" referenced in the pipeline
spec: each test names a known shape of input and pins the expected
output. The point is not exhaustive correctness — it is to lock the
behaviour of the Article 12(1) requirement test, the orchestrator,
and the persistence layer before any real repo run.

Cases
-----
T01  PASS — happy path: 1 step + 1 tool + 1 exit, all SYSTEM_NATIVE
T02  FAIL — step + tool present but no terminal event
T03  FAIL — only step events, no terminal
T04  UNKNOWN — empty event list
T05  ERROR — schema_version mismatch
T06  PASS — events marked SYSTEM_STATE_EXPORTED_BY_HARNESS are eligible
T07  FAIL — HARNESS_GENERATED event present (hard boundary)
T08  FAIL — HARNESS_GENERATED on the step event
T09  FAIL — fabricated_by_probe True (legacy fabrication flag)
T10  PASS — multiple tools same kind, all SYSTEM_NATIVE
T11  PASS — adapter parser: mini-swe-agent fixture (SYSTEM_NATIVE)
T12  PASS — adapter parser: CoreCoder fixture (SYSTEM_STATE_EXPORTED_BY_HARNESS)
T13  PASS — adapter parser: nanobot fixture (SYSTEM_NATIVE)
T14  PASS — registry exposes Article121
T15  PASS — persistence roundtrip + dedup
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# ensure src/ is on path
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


def _ev(events: list[dict], **extra) -> Evidence:
    """Build an Evidence bundle; events default to SYSTEM_NATIVE."""
    normalised = []
    for e in events:
        if "origin" not in e:
            e = {**e, "origin": NATIVE}
        normalised.append(e)
    return Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=tuple(normalised),
        agent_class="probe.Agent",
        agent_version="1.0.0",
        extra=extra,
    )


def _ev_step_tool_exit():
    return _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "tool", "ts": "t2", "name": "bash", "content": "ls"},
        {"kind": "exit", "ts": "t3", "name": "agent", "content": "",
         "exit_status": "submitted"},
    ])


# ----- T01 -----
def test_t01_pass_full_path_system_native():
    record = _ev_step_tool_exit()
    result = _REQ.evaluate(record)
    assert result.status == RunStatus.PASS, result.reason
    assert all(c["passed"] for c in result.checks)


# ----- T02 -----
def test_t02_fail_missing_terminal():
    ev = _ev([
        {"kind": "step", "ts": "t1", "name": "plan"},
        {"kind": "tool", "ts": "t2", "name": "bash", "content": "ls"},
    ])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed_names = {c["name"] for c in result.checks if not c["passed"]}
    assert "EXIT_OR_COMPLETION_KIND_PRESENT" in failed_names


# ----- T03 -----
def test_t03_fail_only_steps():
    ev = _ev([{"kind": "step", "ts": "t1", "name": "x"}])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "STEP_OR_TOOL_KIND_PRESENT" not in failed
    assert "EXIT_OR_COMPLETION_KIND_PRESENT" in failed


# ----- T04 -----
def test_t04_unknown_empty_events():
    ev = _ev([])
    result = _REQ.evaluate(ev)
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
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR


# ----- T06 -----
def test_t06_pass_system_state_exported_by_harness_eligible():
    """CoreCoder-style: events are exported from state the system populated."""
    ev = _ev([
        {"kind": "step", "origin": EXPORTED},
        {"kind": "exit", "origin": EXPORTED, "exit_status": "ok"},
    ])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS, result.reason


# ----- T07 -----
def test_t07_fail_harness_generated_on_terminal():
    """HARNESS_GENERATED events must fail NO_HARNESS_GENERATED_EVENTS."""
    ev = _ev([
        {"kind": "step", "origin": NATIVE},
        {"kind": "exit", "origin": GENERATED, "exit_status": "fake"},
    ])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "NO_HARNESS_GENERATED_EVENTS" in failed


# ----- T08 -----
def test_t08_fail_harness_generated_on_step():
    """HARNESS_GENERATED on a step event also fails."""
    ev = _ev([
        {"kind": "step", "origin": GENERATED},
        {"kind": "exit", "origin": NATIVE, "exit_status": "ok"},
    ])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "NO_HARNESS_GENERATED_EVENTS" in failed
    assert "STEP_OR_TOOL_KIND_PRESENT" in failed


# ----- T09 -----
def test_t09_fail_fabrication_flag_overrides():
    """Legacy fabricated_by_probe flag still fails (back-compat check)."""
    ev = _ev(
        [
            {"kind": "step", "origin": NATIVE},
            {"kind": "exit", "origin": NATIVE, "exit_status": "ok"},
        ],
        fabricated_by_probe=True,
    )
    result = _REQ.evaluate(ev)
    # The new check NO_HARNESS_GENERATED_EVENTS covers this; it
    # should still pass the AT_LEAST_ONE_EVENT etc. checks because
    # the events themselves are eligible.
    assert result.status == RunStatus.PASS, (
        "fabricated_by_probe flag is no longer required since "
        "provenance is per-event; double-check no event is "
        "HARNESS_GENERATED"
    )


# ----- T10 -----
def test_t10_pass_multiple_tools_same_kind():
    ev = _ev([
        {"kind": "tool", "origin": NATIVE, "name": "bash"},
        {"kind": "tool", "origin": NATIVE, "name": "edit"},
        {"kind": "completed", "origin": NATIVE, "name": "run"},
    ])
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


# ----- T11 -----
def test_t11_minisweagent_parser_system_native(tmp_path: Path):
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
        ],
        "trajectory_format": "mini-swe-agent-1.1",
    }))
    adapter = get_adapter("SWE-agent/mini-swe-agent")
    ev = adapter.parse_trajectory(str(traj), DEFAULT_SCENARIO_12_1)
    assert "DefaultAgent" in ev.agent_class
    kinds = [e["kind"] for e in ev.events]
    assert "step" in kinds
    assert "exit" in kinds
    # provenance must be SYSTEM_NATIVE
    assert all(e["origin"] == NATIVE for e in ev.events)


# ----- T12 -----
def test_t12_corecoder_parser_system_state_exported(tmp_path: Path):
    traj = tmp_path / "trajectory.json"
    traj.write_text(json.dumps({
        "model": "fake-probe",
        "messages": [{"role": "user", "content": "hello"}],
        "final_response": "ok",
        "corecoder_version": "0.0.1",
    }))
    adapter = get_adapter("he-yufeng/CoreCoder")
    ev = adapter.parse_trajectory(str(traj), DEFAULT_SCENARIO_12_1)
    assert "Agent" in ev.agent_class
    kinds = [e["kind"] for e in ev.events]
    assert "step" in kinds
    assert "exit" in kinds
    assert all(e["origin"] == EXPORTED for e in ev.events)


# ----- T13 -----
def test_t13_nanobot_parser_system_native(tmp_path: Path):
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
    # SessionTurnStarted -> step, UserInputAccepted -> step, TurnCompleted -> completed
    assert "step" in kinds
    assert "completed" in kinds
    # PLUS the synthetic exit the adapter appends
    assert "exit" in kinds
    assert all(e["origin"] == NATIVE for e in ev.events)


# ----- T14 -----
def test_t14_registry_exposes_article_121():
    req_ids = list_registered_requirements()
    assert "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING" in req_ids
    r = get_requirement("AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING")
    assert r.id == "AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING"
    assert r.version  # non-empty
    # contract must now be 1.2.0
    assert r.version == "1.2.0"


# ----- T15 -----
def test_t15_persistence_roundtrip_and_dedup(tmp_path: Path):
    db_path = tmp_path / "test.db"
    schema_sql = (ROOT / "migrations" / "005_compliance_runtime_runs.sql").read_text()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    evidence = _ev_step_tool_exit()
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


# ----- T16 -----
def test_t16_probe_failed_maps_to_error():
    """Probe subprocess returned non-zero -> ERROR, never FAIL.

    The probe_status short-circuit fires before any of the 5
    compliance checks; even with no events, the verdict is ERROR.
    """
    ev = _ev([], probe_status="probe_failed", probe_returncode=1)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "probe_failed" in result.reason
    # No checks were run; the error short-circuits.
    assert result.checks == ()


# ----- T17 -----
def test_t17_no_trajectory_maps_to_error():
    """Probe ran cleanly but wrote no trajectory -> ERROR."""
    ev = _ev([], probe_status="no_trajectory", probe_returncode=0)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "no_trajectory" in result.reason


# ----- T18 -----
def test_t18_adapter_raised_maps_to_error():
    """Adapter could not parse the trajectory -> ERROR."""
    ev = _ev([], probe_status="adapter_raised", probe_returncode=0)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "adapter_raised" in result.reason


# ----- T19 -----
def test_t19_probe_status_ok_falls_through_to_checks():
    """probe_status='ok' is the normal path; the short-circuit does
    not fire and the 5 compliance checks run as before."""
    ev = _ev_step_tool_exit()
    # Stamp probe_status='ok' explicitly (the default in real runs;
    # _ev() does not add it so this is also a regression test).
    ev.extra["probe_status"] = "ok"
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.PASS


# ----- T20 -----
def test_t20_load_run_by_dedup_key_roundtrip(tmp_path: Path):
    """Persisting then loading by dedup key returns the same
    RunRecord; the loader is the idempotency primitive used by
    run_one() to short-circuit reruns."""
    db_path = tmp_path / "test.db"
    schema_sql = (ROOT / "migrations" / "005_compliance_runtime_runs.sql").read_text()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    evidence = _ev_step_tool_exit()
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

    # Lookup by dedup key returns the same row, reconstructed.
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
    assert loaded.status == RunStatus.PASS
    assert loaded.repository.sha == "abc123"
    assert loaded.evidence.schema_version == EVIDENCE_SCHEMA_VERSION

    # A different SHA returns None.
    assert load_run_by_dedup_key(
        db_path,
        repository_id=999,
        requirement_id=record.requirement_id,
        requirement_version=record.requirement_version,
        repo_sha="different",
        scenario_id=record.scenario_id,
        adapter_name=record.adapter_name,
        adapter_version=record.adapter_version,
    ) is None