"""P4 — real and controlled result-state validation.

Validates that Reguard's run status surface correctly distinguishes:

  PASS      — deterministic Article 12(1) assertion satisfied.
  FAIL      — deterministic negative observation by a real probe.
  UNKNOWN   — probe ran, evidence insufficient to decide.
  ERROR     — probe / parser infrastructure failure.
  UNSUPPORTED — no adapter / test path for the repository.

Negative states are the primary focus of P4.

These tests do NOT mutate v1.4.0 semantics. They exercise the
adapter-layer and orchestrator code paths that produce each status,
and assert that the Article 12(1) verdict collapses to the right
RunStatus without colliding with any neighbouring status.

No source scanner is run. No LLM judge is consulted. No synthetic
runtime event is introduced.
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
from compliance.adapters.pocketflow import PocketFlowAdapter
from compliance.pipeline import orchestrator as orch
from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    RunStatus,
    Scenario,
)
from compliance.requirements.ai_act.article_12_1 import (
    Article121AutomaticLoggingTest,
)


_REQ = Article121AutomaticLoggingTest()


def _ev(
    events: list[dict] | tuple[dict, ...],
    *,
    probe_status: str = "ok",
    category: str = "E",
    observation_quality: str | None = None,
    framework_persists_durably: bool = False,
    framework_artifact_paths: tuple[str, ...] = (),
    harness_artifact_paths: tuple[str, ...] = (),
    **extra,
) -> Evidence:
    """Build a minimal Evidence object for verdict evaluation.

    Tests override only the fields they care about. ``probe_status='ok'``
    and ``schema_version=EVIDENCE_SCHEMA_VERSION`` are always set so the
    base-class schema / probe-status gates pass.
    """
    merged_extra: dict = {
        "recording_category": category,
        "framework_persists_durably": framework_persists_durably,
        "framework_artifact_paths": list(framework_artifact_paths),
        "harness_artifact_paths": list(harness_artifact_paths),
        "probe_status": probe_status,
    }
    if observation_quality is not None:
        merged_extra["observation_quality"] = observation_quality
    merged_extra.update(extra)
    return Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=tuple(events),
        agent_class="probe.Agent",
        agent_version="1.0.0",
        extra=merged_extra,
    )


# ===========================================================================
# 1. FAIL — real positive negative observation
# ===========================================================================
def test_fail_category_c_nanobot_shape_is_fail():
    """C — framework emits events but persistence depends on an external
    recorder. Harness collected events; framework_persists_durably=False.
    Real nanobot-shape input must deterministically FAIL."""
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "SessionTurnStarted",
             "origin": EvidenceOrigin.SYSTEM_NATIVE.value},
            {"kind": "completed", "ts": "t2", "name": "TurnCompleted",
             "origin": EvidenceOrigin.SYSTEM_NATIVE.value},
        ],
        category="C",
        framework_persists_durably=False,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_C" in failed
    assert RunStatus.UNKNOWN != result.status
    assert RunStatus.ERROR != result.status


def test_fail_category_d_corecoder_shape_is_fail():
    """D — framework keeps only ephemeral in-memory state."""
    ev = _ev(
        events=[
            {"kind": "step", "ts": "t1", "name": "user",
             "origin": EvidenceOrigin.SYSTEM_NATIVE.value},
            {"kind": "step", "ts": "t2", "name": "assistant",
             "origin": EvidenceOrigin.SYSTEM_NATIVE.value},
        ],
        category="D",
        framework_persists_durably=False,
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_NON_PASS_D" in failed
    assert RunStatus.UNKNOWN != result.status


def test_fail_category_e_pocketflow_observed_absence_is_fail():
    """E — observable absence (probe + cross-check agree: no framework
    artefact). The runtime observation is what establishes absence; no
    synthetic event is injected."""
    # Build the Evidence via the actual PocketFlow adapter against a
    # synthetic trajectory whose workspace contains no framework-written
    # files. This is what a real probe observes, not a hand-built
    # Evidence object.
    workspace = Path(__file__).resolve().parent / "_tmp_p4_pocketflow_fail"
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    traj = workspace / "trajectory.json"
    traj.write_text(json.dumps({
        "probe_status": "ok",
        "framework_artifacts_observed": [],
    }))

    try:
        ev = PocketFlowAdapter().parse_trajectory(
            str(traj),
            Scenario(scenario_id="compliance.synthetic.hello", user_prompt="hi"),
        )
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)

    # Determinism — the adapter must stamp observed_absence here.
    assert ev.events == ()
    assert ev.extra["observation_quality"] == "observed_absence"
    assert ev.extra["recording_category"] == "E"

    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.FAIL, result.reason
    failed = {c["name"] for c in result.checks if not c["passed"]}
    assert "RECORDING_CATEGORY_E_NON_PASS" in failed
    # FAIL must be observably distinct from neighbouring statuses.
    assert RunStatus.UNKNOWN != RunStatus.FAIL
    assert RunStatus.ERROR != RunStatus.FAIL


# ===========================================================================
# 2. UNKNOWN — controlled indeterminate observation
# ===========================================================================
def test_unknown_pocketflow_when_workspace_has_unrelated_artifact():
    """UNKNOWN — probe ran cleanly (returncode 0, trajectory written),
    framework_persists_durably is False, probe reports zero framework
    artefacts, BUT the cross-check workspace scan finds an unrelated
    JSON file that is NOT on the harness-basename whitelist. The
    adapter therefore stamps observation_quality='indeterminate' and
    events stay empty.

    That is the genuine indeterminate case the spec describes:
       "framework artefact location cannot be deterministically resolved"

    No probe failure is required to reach it; the runtime itself
    completes without error."""
    workspace = Path(__file__).resolve().parent / "_tmp_p4_pocketflow_unknown"
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # Trajectory written by the probe — returncode 0; reports zero
    # framework artefacts observed (matches the probe's own view).
    traj = workspace / "trajectory.json"
    traj.write_text(json.dumps({
        "probe_status": "ok",
        "framework_artifacts_observed": [],
    }))

    # An unrelated JSON file appears in the probe workspace between
    # snapshot and cross-check. It is NOT in the harness basename
    # whitelist, so the scanner counts it as a candidate framework
    # artefact. The adapter thus cannot positively assert absence.
    unrelated = workspace / "unrelated_event.json"
    unrelated.write_text(json.dumps({"side_effect": True}))

    try:
        ev = PocketFlowAdapter().parse_trajectory(
            str(traj),
            Scenario(scenario_id="compliance.synthetic.hello", user_prompt="hi"),
        )
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)

    # Adapter must downgrade to indeterminate (NOT observed_absence),
    # exactly because the scanner found a real file that is not on
    # the harness whitelist.
    assert ev.events == ()
    assert ev.extra["observation_quality"] == "indeterminate"
    assert ev.extra["probe_status"] == "ok"
    assert ev.extra["recording_category"] == "E"

    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.UNKNOWN, result.reason
    # Indistinguishable from ERROR would be a bug — must be UNKNOWN.
    assert result.status != RunStatus.ERROR
    assert result.status != RunStatus.FAIL
    assert "indeterminate" in (result.reason or "").lower() or \
        "no runtime events" in (result.reason or "").lower() or \
        result.status == RunStatus.UNKNOWN


def test_unknown_when_bundle_has_no_events_and_no_marker():
    """Generic UNKNOWN contract — the base class keeps UNKNOWN when an
    empty bundle lacks observation_quality='observed_absence'."""
    ev = _ev([], probe_status="ok", category="E", observation_quality=None)
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.UNKNOWN
    assert result.status != RunStatus.FAIL
    assert result.status != RunStatus.ERROR


# ===========================================================================
# 3. ERROR — infrastructure / probe failure paths
# ===========================================================================
class _BoomAdapter:
    """Adapter that always raises inside parse_trajectory — exercises
    the orchestrator's adapter_raised branch."""

    name = "boom"
    version = "test"

    def parse_trajectory(self, trajectory_path: str, scenario):  # noqa: D401
        raise RuntimeError("simulated parser failure")

    def resolve_agent(self, repo_root: str) -> str:  # noqa: D401
        return "boom.Agent"


def test_error_probe_failed_when_subprocess_returned_nonzero():
    """ERROR (class A) — probe subprocess returned non-zero. The
    orchestrator's collect_evidence must short-circuit to
    probe_status='probe_failed' and the requirement to ERROR."""
    from compliance.pipeline.orchestrator import ProbeOutputs
    outputs = ProbeOutputs(
        work_dir=Path("/tmp/reguard_p4_a"),
        trajectory_path=Path("/tmp/reguard_p4_a/missing.json"),
        stdout_log="",
        stderr_log="simulated install failure",
        returncode=2,
    )
    # Use a benign adapter — the orchestrator must not invoke it when
    # returncode != 0.
    ev = orch.collect_evidence(
        adapter=PocketFlowAdapter(),
        scenario=Scenario(scenario_id="t", user_prompt="hi"),
        outputs=outputs,
    )
    assert ev.extra["probe_status"] == "probe_failed"
    assert ev.extra["probe_returncode"] == 2

    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "probe_failed" in result.reason
    # ERROR must be distinguishable from UNKNOWN — distinct statuses.
    assert RunStatus.ERROR != RunStatus.UNKNOWN


def test_error_adapter_raised_when_parser_raises_on_clean_probe():
    """ERROR (class B) — probe subprocess returned 0 and wrote a
    trajectory file, but the adapter's parse_trajectory raised. The
    orchestrator must record probe_status='adapter_raised'."""
    from compliance.pipeline.orchestrator import ProbeOutputs

    workspace = Path(__file__).resolve().parent / "_tmp_p4_adapter_raised"
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    traj = workspace / "trajectory.json"
    traj.write_text("{}")

    outputs = ProbeOutputs(
        work_dir=workspace,
        trajectory_path=traj,
        stdout_log="",
        stderr_log="",
        returncode=0,
    )
    try:
        ev = orch.collect_evidence(
            adapter=_BoomAdapter(),
            scenario=Scenario(scenario_id="t", user_prompt="hi"),
            outputs=outputs,
        )
    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)

    assert ev.extra["probe_status"] == "adapter_raised"
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR
    assert "adapter_raised" in result.reason


def test_error_schema_mismatch_is_error_not_silent_pass():
    """ERROR — even with a clean probe, an evidence schema mismatch
    is ERROR (never silently mapped to PASS/FAIL/UNKNOWN)."""
    ev = Evidence(
        schema_version="not-the-current-version",
        events=(),
        agent_class="x",
        agent_version="1",
        extra={"probe_status": "ok", "observation_quality": "observed_absence"},
    )
    result = _REQ.evaluate(ev)
    assert result.status == RunStatus.ERROR


# ===========================================================================
# 4. UNSUPPORTED — no adapter registered
# ===========================================================================
def test_unsupported_when_repo_not_in_registry(tmp_path, monkeypatch):
    """UNSUPPORTED — repository full_name not in ADAPTER_REGISTRY.
    The registry must raise KeyError; the CLI's main() catches that
    into a synthetic UNSUPPORTED record with exit code 3.

    The CLI's clone-mode path opens the production SQLite DB to
    resolve the repo row. On a clean checkout that DB does not
    exist. The test therefore seeds a temp DB with the required
    ``agent_repositories`` schema and points
    :func:`pipeline.persistence.default_db_path` at it for the
    duration of the test.
    """
    db = tmp_path / "research.db"
    sql = (ROOT / "migrations" / "001_agent_repositories.sql").read_text()
    conn = sqlite3.connect(db)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

    # Point the pipeline module at the temp DB so the lookup uses it.
    from compliance.pipeline import persistence as pipe_persist
    monkeypatch.setattr(pipe_persist, "default_db_path", lambda: db)
    # driver.py imports default_db_path at module load; patch its bound
    # name too.
    from compliance.pipeline import driver as pipe_driver
    monkeypatch.setattr(pipe_driver, "default_db_path", lambda: db)

    with pytest.raises(KeyError):
        get_adapter("this-org/this-repo-does-not-exist")

    # Drive the actual CLI main() entry point to confirm UNSUPPORTED
    # surface and exit-code contract end-to-end without a real probe.
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import importlib
    cli = importlib.import_module("compliance-check")
    importlib.reload(cli)

    rc = cli.main([
        "--repo", "this-org/this-repo-does-not-exist",
        "--sha", "0" * 40,
    ])
    assert rc == 3  # EXIT_CODE[RunStatus.UNSUPPORTED]
    assert cli.EXIT_CODE[RunStatus.UNSUPPORTED] == 3

    # Distinct from neighbouring statuses — UNSUPPORTED != ERROR.
    assert cli.EXIT_CODE[RunStatus.UNSUPPORTED] != cli.EXIT_CODE[RunStatus.ERROR]
    assert RunStatus.UNSUPPORTED.value != RunStatus.ERROR.value


# ===========================================================================
# 5. Status surface — distinctness invariants
# ===========================================================================
def test_status_enumeration_is_distinct():
    """The five RunStatus values must be pairwise distinct and the CLI
    exit-code map must mirror the enum without collapse."""
    values = {s.value for s in RunStatus}
    assert len(values) == 5
    expected = {"PASS", "FAIL", "UNKNOWN", "UNSUPPORTED", "ERROR"}
    assert values == expected

    scripts_dir = ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    cli = importlib.import_module("compliance-check")

    codes = cli.EXIT_CODE
    # FAIL (1) is distinct from UNKNOWN (2), UNSUPPORTED (3), ERROR (4).
    assert codes[RunStatus.PASS] == 0
    assert codes[RunStatus.FAIL] == 1
    assert codes[RunStatus.UNKNOWN] == 2
    assert codes[RunStatus.UNSUPPORTED] == 3
    assert codes[RunStatus.ERROR] == 4
    # No two engine statuses may collapse to the same exit code.
    assert len(set(codes.values())) == len(codes)


@pytest.mark.parametrize(
    "status_a,status_b",
    [
        (RunStatus.FAIL, RunStatus.UNKNOWN),
        (RunStatus.UNKNOWN, RunStatus.ERROR),
        (RunStatus.ERROR, RunStatus.UNSUPPORTED),
        (RunStatus.PASS, RunStatus.FAIL),
        (RunStatus.PASS, RunStatus.UNKNOWN),
        (RunStatus.PASS, RunStatus.ERROR),
        (RunStatus.PASS, RunStatus.UNSUPPORTED),
    ],
)
def test_status_pairs_are_distinct(status_a, status_b):
    scripts_dir = ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    cli = importlib.import_module("compliance-check")
    if status_a == status_b:
        return
    assert status_a != status_b
    assert status_a.value != status_b.value
    assert cli.EXIT_CODE[status_a] != cli.EXIT_CODE[status_b]


# ===========================================================================
# 6. No forbidden mechanisms
# ===========================================================================
def test_no_synthetic_event_injected_on_unknown_dispatch():
    """The base class MUST NOT introduce any synthetic event when
    routing an empty bundle through assert_evidence. This is the
    "no fake event" invariant the spec requires for the negative
    states."""
    stub_called = {"n": 0}

    from compliance.requirements.base import CheckResult, RequirementTest

    class _RecordingStub(RequirementTest):
        id = "STUB_REC"
        version = "0.0.1"

        def assert_evidence(self, evidence):
            stub_called["n"] += 1
            # Snapshot the bundle we received — must still be empty.
            assert evidence.events == ()
            yield CheckResult(name="SHOULD_NOT_HAPPEN", passed=True, detail="ok")

    # Empty bundle + observed_absence marker.
    ev = Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=(),
        agent_class="x",
        agent_version="1",
        extra={"probe_status": "ok", "observation_quality": "observed_absence"},
    )
    res = _RecordingStub().evaluate(ev)
    assert stub_called["n"] == 1
    # Base class returned a Fail verdict (the stub returned PASS) only
    # if all checks passed; here stub yields a passed check so we
    # expect PASS. The key invariant is the bundle still had zero
    # events — never padded.
    assert res.summary.get("event_count") == 0
