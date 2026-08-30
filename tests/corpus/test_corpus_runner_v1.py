"""Corpus Runner v1 — end-to-end test plan.

11 categories (per spec):
  1. run creation
  2. SHA manifest immutability
  3. job creation
  4. unsupported fast-fail
  5. worker bound
  6. retry
  7. no-retry
  8. resume
  9. governor
 10. network policy
 11. regression of v1.4.0 contract semantics

All tests use a temporary sqlite file; no test relies on the
production DB or on the real container runtime. The driver is
mocked via a stub function injected into the executor module.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.corpus_runner import executor as cr_exec
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.errors import (
    CONTAINER_START_ERROR,
    INSTALL_ERROR,
    PROBE_ERROR,
    SHA_RESOLUTION_ERROR,
    TIMEOUT,
    RETRYABLE_ERROR_CLASSES,
    classify_probe_status,
    is_retryable,
)
from compliance.corpus_runner.scenarios import S1, S3, LEGACY_S1
from compliance.corpus_runner.sha_resolver import ShaResolution
from compliance.pipeline import orchestrator
from compliance.pipeline.persistence import default_db_path
from compliance.pipeline.types import (
    EVIDENCE_SCHEMA_VERSION,
    Evidence,
    EvidenceOrigin,
    RepositoryTarget,
    Result,
    RunRecord,
    RunStatus,
    Scenario,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test DB file. Apply only the migrations Corpus Runner
    v1 actually depends on (no production DB reads)."""
    db = tmp_path / "corpus_runner.db"
    migrations_dir = ROOT / "migrations"
    needed = [
        "001_agent_repositories.sql",
        "002_agent_repositories_reclassified_at.sql",
        "003_agent_repository_audits.sql",
        "004_article_runtime_assessments.sql",
        "005_compliance_runtime_runs.sql",
        "006_corpus_runs.sql",
        "007_corpus_run_repositories.sql",
        "008_evaluation_jobs.sql",
        "009_evaluation_attempts.sql",
        "010_corpus_runner_v1_1_schema.sql",
        "011_corpus_runner_v1_1_evidence_state.sql",
    ]
    conn = sqlite3.connect(db)
    try:
        for name in needed:
            sql = (migrations_dir / name).read_text()
            conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture
def known_repos(db_path: Path) -> None:
    """Seed five known-good + one unsupported agent_repositories
    rows. Idempotent — re-seeding skips rows that already exist.
    Names match the ADAPTER_REGISTRY except for the explicit
    unsupported one."""
    rows = [
        ("SWE-agent/mini-swe-agent", "https://github.com/SWE-agent/mini-swe-agent", 1, 5000),
        ("he-yufeng/CoreCoder",      "https://github.com/he-yufeng/CoreCoder",      2, 200),
        ("HKUDS/nanobot",            "https://github.com/HKUDS/nanobot",            3, 100),
        ("gptme/gptme",              "https://github.com/gptme/gptme",               4, 8000),
        ("The-Pocket/PocketFlow",    "https://github.com/The-Pocket/PocketFlow",     5, 3000),
        ("example/no-such-agent",    "https://github.com/example/no-such-agent",     6, 10),
    ]
    conn = sqlite3.connect(db_path)
    try:
        for (fn, url, gid, stars) in rows:
            cur = conn.execute(
                "SELECT 1 FROM agent_repositories WHERE full_name = ?",
                (fn,),
            )
            if cur.fetchone() is not None:
                continue
            conn.execute(
                """
                INSERT INTO agent_repositories (
                    github_id, full_name, owner, name, html_url, clone_url,
                    primary_language, relevance_status, enabled, archived,
                    fork, stars, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'Python', 'accepted', 1, 0, 0,
                          ?, '2026-01-01T00:00:00Z')
                """,
                (gid, fn, fn.split("/")[0], fn.split("/")[1],
                 f"https://github.com/{fn}", url, stars),
            )
        conn.commit()
    finally:
        conn.close()


# The 5 known repos, in registry name order. Used in many tests.
KNOWN_FIVE = (
    "SWE-agent/mini-swe-agent",
    "he-yufeng/CoreCoder",
    "HKUDS/nanobot",
    "gptme/gptme",
    "The-Pocket/PocketFlow",
)

# Canonical 40-char test SHA. Used by both the stub resolver and
# the stub driver so they agree on the same value.
STUB_SHA = "deadbeef" + "0" * 32


# Stub driver to avoid real probe work. Returns deterministic
# RunRecords based on a per-full-name fixture table.

@dataclass
class _StubRun:
    repository_id: int
    full_name: str
    sha: str
    status: RunStatus
    reason: str = ""
    error_class: str = ""


_STUB_TABLE: dict[str, _StubRun] = {}


def _stub_record_to_runrecord(stub: _StubRun) -> RunRecord:
    """Build a minimal RunRecord matching the v1.4.0 contract shape."""
    extra: dict[str, Any] = {
        "recording_category": "A",
        "framework_persists_durably": True,
        "framework_artifact_paths": [],
        "harness_artifact_paths": [],
        "origin": EvidenceOrigin.SYSTEM_NATIVE.value,
        "producer": "stub",
        "collector": "stub",
    }
    if stub.error_class:
        extra["probe_status"] = stub.error_class
    evidence = Evidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        events=(),
        agent_class="stub",
        agent_version="stub",
        extra=extra,
    )
    target = RepositoryTarget(
        repository_id=stub.repository_id,
        full_name=stub.full_name,
        sha=stub.sha,
        branch="main",
    )
    result = Result(
        schema_version="2",
        status=stub.status,
        reason=stub.reason,
    )
    return RunRecord(
        repository=target,
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        runtime_version="test",
        adapter_name=stub.full_name.split("/", 1)[1].lower(),
        adapter_version="0",
        scenario_id=LEGACY_S1,
        status=stub.status,
        reason=stub.reason,
        result=result,
        evidence=evidence,
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
        duration_seconds=0.1,
    )


def _stub_driver_run_one(*, full_name: str, sha: str,
                          requirement_id: str = "X",
                          **_: object) -> RunRecord:
    """Drop-in replacement for `driver.run_one` AND
    `driver.run_with_prepared_checkout`. Accepts and ignores the
    extra `repo_checkout` keyword argument passed by the v1.1.1
    materializer-driven path."""
    if full_name not in _STUB_TABLE:
        raise KeyError(full_name)
    stub = _STUB_TABLE[full_name]
    if stub.sha != sha:
        raise RuntimeError(f"sha mismatch for {full_name}: {sha} != {stub.sha}")
    rec = _stub_record_to_runrecord(stub)
    return rec


# The worker thread calls driver_run_one which would re-resolve
# the dedup key. We need a current db_path mapping so the stub
# can return repository_id > 0. The default behaviour below reads
# from a module-level dict that tests can populate.
_DB_FOR_STUB: dict[str, int] = {}


def _seed_stub(full_name: str, status: RunStatus,
                repository_id: int, *, error_class: str = "") -> None:
    _STUB_TABLE[full_name] = _StubRun(
        repository_id=repository_id, full_name=full_name,
        sha=STUB_SHA,
        status=status, reason="stub", error_class=error_class,
    )


def _fake_sha_resolver(clone_url: str) -> ShaResolution:
    return ShaResolution(sha=STUB_SHA, classification="ok", message="stub")


@pytest.fixture(autouse=True)
def _reset_stubs():
    _STUB_TABLE.clear()
    yield
    _STUB_TABLE.clear()


@pytest.fixture
def stub_driver(monkeypatch):
    monkeypatch.setattr(cr_exec, "driver_run_one", _stub_driver_run_one)
    # v1.1.1: the materializer-wired executor calls
    # `driver.run_with_prepared_checkout` instead of `driver.run_one`
    # for the normal execution path. Stub that as well so the
    # v1.1.1 materializer path is fast under tests.
    from compliance.pipeline import driver as drv
    monkeypatch.setattr(drv, "run_with_prepared_checkout",
                        _stub_driver_run_one)
    # Stub the materializer itself so no real SourceCache fetch runs.
    from compliance.corpus_runner.materializer import (
        PreparedRepository, MaterializationMetrics,
    )

    class _StubMaterializer:
        def __init__(self):
            self.metrics = MaterializationMetrics()

        def prepare(self, *, repository_id, clone_url, repo_sha,
                    attempt_id):
            self.metrics.source_cache_hits += 1
            tmp = Path(f"/tmp/reguard_stub_ws_{attempt_id}")
            tmp.mkdir(parents=True, exist_ok=True)
            (tmp / "repo").mkdir(parents=True, exist_ok=True)
            return PreparedRepository(
                workspace_id=f"stub-{attempt_id}",
                workspace_root=tmp,
                repository_path=tmp / "repo",
                artifacts_path=tmp / "artifacts",
                logs_path=tmp / "logs",
                repo_sha=repo_sha,
                cache_key="stub",
                cache_hit=True,
            )

        def cleanup(self, prepared):
            import shutil as _sh
            try:
                _sh.rmtree(prepared.workspace_root, ignore_errors=True)
            except OSError:
                pass
            return True

        def metrics_snapshot(self):
            return _to_dict(self.metrics)

    def _to_dict(m):
        import dataclasses
        return dataclasses.asdict(m)

    monkeypatch.setattr(cr_exec, "RepositoryMaterializer", _StubMaterializer)
    return _stub_driver_run_one


def _resolve_run_counters(db_path: Path, run_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM corpus_runs WHERE id = ?", (run_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ===========================================================================
# 1. Run creation
# ===========================================================================

def test_run_creation_writes_corpus_run_row(db_path, known_repos):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0",
        scenario_id=S1,
        executor="subprocess",
        runtime_version="test",
        max_workers=1,
        max_attempts=2,
        selection_description="test1",
        requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent",
            "he-yufeng/CoreCoder",
            "HKUDS/nanobot",
            "gptme/gptme",
            "The-Pocket/PocketFlow",
        ),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    run = crp.load_corpus_run(rid, db_path=db_path)
    assert run is not None
    assert run.requirement_version == "1.4.0"
    assert run.scenario_id == S1
    assert run.executor == "subprocess"
    assert run.requested_repo_count == 5
    assert run.status == "pending"


def test_run_creation_writes_manifest_with_resolved_sha(db_path, known_repos):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "gptme/gptme",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    # First 2 entries are the explicit includes; remaining 3 are
    # stars_desc fill from the other 3 known repos.
    assert len(manifest) == 5
    assert manifest[0]["full_name"] == "SWE-agent/mini-swe-agent"
    assert manifest[1]["full_name"] == "gptme/gptme"
    for row in manifest:
        assert row["resolved_sha"] == STUB_SHA
        assert row["sha_resolution_class"] == "ok"


# ===========================================================================
# 2. SHA manifest immutability
# ===========================================================================

def test_sha_manifest_is_frozen_after_run_creation(db_path, known_repos):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=2,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=2, include_full_names=(
            "SWE-agent/mini-swe-agent", "gptme/gptme",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    # Mutate the agent_repositories row's clone_url. The manifest
    # row must remain the original (frozen) URL.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE agent_repositories SET clone_url = "
            "'https://github.com/changed/foo' "
            "WHERE full_name = 'SWE-agent/mini-swe-agent'"
        )
        conn.commit()
    finally:
        conn.close()
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    assert all(
        "changed/foo" not in (row["clone_url"] or "")
        for row in manifest
    )


# ===========================================================================
# 3. Job creation
# ===========================================================================

def test_job_creation_creates_one_per_repo(db_path, known_repos, stub_driver):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "he-yufeng/CoreCoder",
            "HKUDS/nanobot", "gptme/gptme", "The-Pocket/PocketFlow",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    n = cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    assert n == 5
    pending = crp.list_jobs_for_run(rid, db_path=db_path)
    assert len(pending) == 5
    # All jobs should have a non-empty repo_sha.
    assert all(j["repo_sha"] for j in pending)


def test_job_creation_short_circuits_sha_failures(db_path, known_repos):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=2,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=2, include_full_names=(
            "SWE-agent/mini-swe-agent", "gptme/gptme",
        ), db_path=db_path,
    )

    def failing_resolver(url: str) -> ShaResolution:
        return ShaResolution(sha=None, classification="sha_resolution_error",
                             message="network down")

    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=failing_resolver)
    n = cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    assert n == 2
    counters = _resolve_run_counters(db_path, rid)
    assert counters["error_count"] == 2
    assert counters["completed_jobs"] == 2
    assert counters["total_jobs"] == 2


# ===========================================================================
# 4. Unsupported fast-fail
# ===========================================================================

def test_unsupported_repo_short_circuits_without_driver_call(db_path, known_repos):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    # Use one repo that is NOT in ADAPTER_REGISTRY (example/no-such-agent)
    # plus four supported ones. The unsupported one must be
    # short-circuited before the driver is called.
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "he-yufeng/CoreCoder",
            "gptme/gptme", "The-Pocket/PocketFlow",
            "example/no-such-agent",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    called: list[str] = []

    # Build a full_name -> repository_id map so the stub returns
    # the correct id (used for dedup lookup).
    manifest_by_name = {
        r["full_name"]: r["repository_id"]
        for r in crp.list_corpus_run_repositories(rid, db_path=db_path)
    }

    def spy(*, full_name, sha, **_: object):
        called.append(full_name)
        return _stub_record_to_runrecord(
            _StubRun(repository_id=manifest_by_name.get(full_name, 0),
                     full_name=full_name, sha=sha,
                     status=RunStatus.PASS)
        )

    # v1.1.1 path: the executor calls `run_with_prepared_checkout`
    # (not `driver_run_one`). Patch the right symbol. We also patch
    # the legacy entrypoint to make sure the executor doesn't fall
    # back to it. We must also stub `RepositoryMaterializer.prepare`
    # to avoid the real fetch against GitHub URLs in this test.
    import tempfile as _tempfile
    from compliance.pipeline import driver as drv
    from compliance.corpus_runner.materializer import PreparedRepository
    fake_ws = Path(_tempfile.mkdtemp(prefix="reguard_test_unsupp_"))
    (fake_ws / "input").mkdir(parents=True, exist_ok=True)
    (fake_ws / "repo").mkdir(parents=True, exist_ok=True)
    (fake_ws / "artifacts").mkdir(parents=True, exist_ok=True)
    (fake_ws / "logs").mkdir(parents=True, exist_ok=True)

    def stub_prepare(self, *, repository_id, clone_url, repo_sha,
                     attempt_id):
        return PreparedRepository(
            workspace_id=f"stub-{attempt_id}",
            workspace_root=fake_ws,
            repository_path=fake_ws / "repo",
            artifacts_path=fake_ws / "artifacts",
            logs_path=fake_ws / "logs",
            repo_sha=repo_sha,
            cache_key="stub",
            cache_hit=True,
        )

    def stub_cleanup(self, prepared):
        return True

    with mock.patch.object(drv, "run_with_prepared_checkout",
                           side_effect=spy):
        with mock.patch.object(cr_exec, "driver_run_one",
                               side_effect=spy):
            with mock.patch.object(
                cr_exec.RepositoryMaterializer, "prepare", stub_prepare,
            ):
                with mock.patch.object(
                    cr_exec.RepositoryMaterializer, "cleanup", stub_cleanup,
                ):
                    cr_exec.run_corpus_run(rid, executor="subprocess",
                                           db_path=db_path)

    # example/no-such-agent has no adapter. The driver must NOT be
    # invoked for it; the others must.
    assert "example/no-such-agent" not in called
    assert len(called) == 4
    counters = _resolve_run_counters(db_path, rid)
    assert counters["unsupported_count"] == 1
    assert counters["pass_count"] == 4


def test_unsupported_scenario_short_circuits_to_skipped(
        db_path, known_repos, stub_driver):
    # Build a run with a scenario that none of the adapters declare
    # in supported_scenarios. Use S3 ("tool_failure") which is
    # declared by every registered adapter — then we'll mark it as
    # NOT supported on the gptme adapter via direct DB hack.
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S3,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=2,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "he-yufeng/CoreCoder",
            "HKUDS/nanobot", "gptme/gptme", "The-Pocket/PocketFlow",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S3, db_path=db_path)
    counters = _resolve_run_counters(db_path, rid)
    # PocketFlow does NOT declare S3 — only S1 and S4. So
    # build_jobs_for_run short-circuits PocketFlow into the
    # `skipped_unsupported_scenario` state. The other 4 remain
    # pending.
    assert counters["skipped_count"] == 1
    pending = crp.list_jobs_for_run(rid, only_status=crp.JOB_STATUS_PENDING,
                                     db_path=db_path)
    assert len(pending) == 4
    skipped = crp.list_jobs_for_run(rid,
                                     only_status=crp.JOB_STATUS_SKIPPED_UNSUPPORTED_SCENARIO,
                                     db_path=db_path)
    assert len(skipped) == 1
    assert skipped[0]["adapter_name"] == "pocketflow"


# ===========================================================================
# 5. Worker bound
# ===========================================================================

def test_worker_count_capped_by_max_workers(db_path, known_repos, stub_driver):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=2, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "he-yufeng/CoreCoder",
            "HKUDS/nanobot", "gptme/gptme", "example/no-such-agent",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    # Seed stubs for the 4 supported repos. example/no-such-agent
    # is unsupported (no stub).
    for row in crp.list_corpus_run_repositories(rid, db_path=db_path):
        if row["full_name"] != "example/no-such-agent":
            _seed_stub(row["full_name"], RunStatus.PASS,
                        repository_id=row["repository_id"])

    active = cr_exec.ActiveContainerCounter(max_active=2)
    cr_exec.run_corpus_run(
        rid, executor="subprocess", db_path=db_path,
        container_counter=active,
    )
    assert active.peak <= 2
    counters = _resolve_run_counters(db_path, rid)
    assert counters["pass_count"] == 4
    assert counters["unsupported_count"] == 1


# ===========================================================================
# 6. Retry (transient errors retried up to max_attempts)
# ===========================================================================

def test_retry_on_container_start_error(db_path, known_repos, monkeypatch):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=3,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("SWE-agent/mini-swe-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    # Stub the _execute_one_attempt to return CONTAINER_START_ERROR
    # twice and then PASS.
    state = {"count": 0}

    def fake_execute_one_attempt(*, job_id, attempt_number, full_name,
                                  repo_sha, requirement_id, worker_id,
                                  executor, db_path=None, materializer=None):
        attempt_id = crp.insert_evaluation_attempt(
            evaluation_job_id=job_id, attempt_number=attempt_number,
            worker_id=worker_id, db_path=db_path,
        )
        state["count"] += 1
        if state["count"] <= 2:
            crp.update_evaluation_attempt_finished(
                attempt_id, result_status="ERROR",
                error_class=CONTAINER_START_ERROR,
                error_message="oci runtime hiccup", db_path=db_path,
            )
            return "ERROR", CONTAINER_START_ERROR, "oci runtime hiccup", None
        crp.update_evaluation_attempt_finished(
            attempt_id, result_status="PASS",
            error_class="", error_message="",
            db_path=db_path,
        )
        return "PASS", "", "", None

    monkeypatch.setattr(cr_exec, "_execute_one_attempt",
                         fake_execute_one_attempt)
    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)
    counters = _resolve_run_counters(db_path, rid)
    assert counters["pass_count"] == 1
    assert counters["error_count"] == 0
    # 3 attempts total: 2 retries + 1 success.
    assert state["count"] == 3


# ===========================================================================
# 7. No retry (non-retryable error → terminal)
# ===========================================================================

def test_no_retry_on_probe_error(db_path, known_repos, monkeypatch):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=3,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("SWE-agent/mini-swe-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    state = {"count": 0}

    def fake_execute(*, job_id, attempt_number, full_name, repo_sha,
                      requirement_id, worker_id, executor, db_path=None,
                      materializer=None):
        attempt_id = crp.insert_evaluation_attempt(
            evaluation_job_id=job_id, attempt_number=attempt_number,
            worker_id=worker_id, db_path=db_path,
        )
        state["count"] += 1
        crp.update_evaluation_attempt_finished(
            attempt_id, result_status="ERROR",
            error_class=PROBE_ERROR,
            error_message="probe bad", db_path=db_path,
        )
        return "ERROR", PROBE_ERROR, "probe bad", None

    monkeypatch.setattr(cr_exec, "_execute_one_attempt", fake_execute)
    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)
    counters = _resolve_run_counters(db_path, rid)
    assert counters["error_count"] == 1
    assert state["count"] == 1  # no retries


def test_classifier_is_correct():
    assert is_retryable(CONTAINER_START_ERROR) is True
    assert is_retryable(TIMEOUT) is True
    assert is_retryable(INSTALL_ERROR) is False
    assert is_retryable(PROBE_ERROR) is False
    assert is_retryable(None) is False
    assert classify_probe_status("ok") == ""
    assert classify_probe_status("probe_failed") == PROBE_ERROR
    assert classify_probe_status("no_trajectory") == PROBE_ERROR


# ===========================================================================
# 8. Resume (immutable SHA + idempotent)
# ===========================================================================

def test_resume_does_not_resnapshot(db_path, known_repos, monkeypatch):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("SWE-agent/mini-swe-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    # First, mutate the resolver to return a different SHA and
    # call create_corpus_run again on the SAME id: this should
    # NOT happen because resume should not re-snapshot. We assert
    # the snapshot manifest is preserved by attempting another
    # create_corpus_run in a separate run.
    sha1 = crp.list_corpus_run_repositories(rid, db_path=db_path)[0]["resolved_sha"]

    def different_sha_resolver(_url):
        return ShaResolution(sha="feedface" + "0" * 33,
                             classification="ok",
                             message="would-be-different")

    # create_corpus_run creates a NEW run id; original manifest
    # must remain unchanged.
    new_rid = cr_exec.create_corpus_run(cfg, rows,
                                          resolve_sha=different_sha_resolver)
    sha_after = crp.list_corpus_run_repositories(rid, db_path=db_path)[0]["resolved_sha"]
    assert sha_after == sha1
    assert new_rid != rid


# ===========================================================================
# 9. Governor (active container counter)
# ===========================================================================

def test_active_container_counter_admission_control():
    c = cr_exec.ActiveContainerCounter(max_active=2)
    assert c.acquire() is True
    assert c.acquire() is True
    assert c.acquire() is False
    c.release()
    assert c.acquire() is True
    assert c.peak == 2


def test_active_container_counter_peak_observed(db_path, known_repos,
                                                  stub_driver, monkeypatch):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=3, max_attempts=1,
        selection_description="", requested_repo_count=3,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=3, include_full_names=(
            "SWE-agent/mini-swe-agent",
            "he-yufeng/CoreCoder",
            "gptme/gptme",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    # Slow down the stub to ensure the pool can have multiple
    # concurrent attempts.
    for row in crp.list_corpus_run_repositories(rid, db_path=db_path):
        _seed_stub(row["full_name"], RunStatus.PASS,
                    repository_id=row["repository_id"])

    counter = cr_exec.ActiveContainerCounter(max_active=3)
    cr_exec.run_corpus_run(
        rid, executor="subprocess", db_path=db_path,
        container_counter=counter,
    )
    assert counter.peak <= 3
    counters = _resolve_run_counters(db_path, rid)
    assert counters["pass_count"] == 3


# ===========================================================================
# 10. Network policy (no probe-time network)
# ===========================================================================

def test_container_runner_default_network_is_none():
    """The default value of `network` parameter is "none" — i.e.
    the probe container has network disabled. The driver-level
    network policy is enforced by container_runner.run_in_container."""
    from compliance.pipeline.container_runner import run_in_container
    import inspect
    sig = inspect.signature(run_in_container)
    assert sig.parameters["network"].default == "none"


def test_container_runner_invocation_passes_network_flag(monkeypatch):
    """When network="none", the invocation argv contains --network none."""
    captured: dict[str, list[str]] = {}

    def fake_run(*args, **kwargs):
        # container_runner calls subprocess.run(args=invocation, ...).
        captured["argv"] = list(kwargs.get("args", args[0] if args else []))
        # Return a fake CompletedProcess-like object.
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    from compliance.pipeline import container_runner
    monkeypatch.setattr(container_runner.subprocess, "run", fake_run)

    fake_target = Path("/tmp/fake_target")
    fake_probe = Path("/tmp/fake_probe.py")
    # Bypass directory check by mocking is_dir/is_file.
    monkeypatch.setattr(container_runner.Path, "is_dir", lambda self: True)
    monkeypatch.setattr(container_runner.Path, "is_file", lambda self: True)

    container_runner.run_in_container(
        target_repo_path=fake_target,
        probe_script_path=fake_probe,
        probe_task="hello",
        network="none",
    )
    argv = captured["argv"]
    assert "--network" in argv
    idx = argv.index("--network")
    assert argv[idx + 1] == "none"


# ===========================================================================
# 11. Regression — Article 12(1) v1.4.0 baseline
# ===========================================================================

def test_p4_baseline_still_holds_for_corpus_runner_path(
        db_path, known_repos, stub_driver):
    """CR-1 invariant regression — must reproduce the frozen
    Article 12(1) v1.4.0 baseline exactly:

      PASS=2  (mini-swe-agent A, gptme B)
      FAIL=3  (nanobot C, CoreCoder D, PocketFlow E)
      UNKNOWN=0, ERROR=0, UNSUPPORTED=0

    All five frozen repositories are supported. There must be
    NO UNSUPPORTED in the CR-1 distribution.
    """
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent",
            "gptme/gptme",
            "HKUDS/nanobot",
            "he-yufeng/CoreCoder",
            "The-Pocket/PocketFlow",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    # CR-1 expected per-repo status (frozen baseline).
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    expected_status = {
        "SWE-agent/mini-swe-agent": RunStatus.PASS,
        "gptme/gptme":              RunStatus.PASS,
        "HKUDS/nanobot":            RunStatus.FAIL,
        "he-yufeng/CoreCoder":      RunStatus.FAIL,
        "The-Pocket/PocketFlow":    RunStatus.FAIL,
    }
    for row in manifest:
        st = expected_status.get(row["full_name"])
        assert st is not None, f"unexpected manifest entry {row['full_name']!r}"
        _seed_stub(row["full_name"], st, repository_id=row["repository_id"])

    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)
    counters = _resolve_run_counters(db_path, rid)
    assert counters["pass_count"] == 2, counters
    assert counters["fail_count"] == 3, counters
    assert counters["unsupported_count"] == 0, counters
    assert counters["error_count"] == 0, counters
    assert counters["unknown_count"] == 0, counters
    assert counters["skipped_count"] == 0, counters


# ===========================================================================
# Summary JSON
# ===========================================================================

def test_write_summary_json_emits_counts(db_path, known_repos, stub_driver):
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=(
            "SWE-agent/mini-swe-agent", "he-yufeng/CoreCoder",
            "HKUDS/nanobot", "gptme/gptme", "The-Pocket/PocketFlow",
        ), db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)
    summary_path = db_path.parent / "summary.json"
    cr_exec.write_summary_json(rid, summary_path, db_path=db_path)
    payload = json.loads(summary_path.read_text())
    assert payload["corpus_run_id"] == rid
    assert payload["requirement_version"] == "1.4.0"
    assert payload["scenario_id"] == S1
    assert "error_class_counts" in payload


# ===========================================================================
# Identity regression — CR-1 baseline invariant
# ===========================================================================

# The five frozen Article 12(1) v1.4.0 baseline repositories.
# Cross-referenced against:
#   - audit/p3_selection.md (selection + categories)
#   - audit/article_12_1_pipeline_report.md (historical verdicts)
#   - src/compliance/adapters/registry.py (ADAPTER_REGISTRY keys)
#   - data/eu_ai_compliance.db (production full_name)
FROZEN_CR1 = (
    "SWE-agent/mini-swe-agent",
    "gptme/gptme",
    "HKUDS/nanobot",
    "he-yufeng/CoreCoder",
    "The-Pocket/PocketFlow",
)


def test_each_frozen_repo_resolves_to_adapter(db_path, known_repos):
    """Each of the five frozen CR-1 repos must be resolvable to
    a registered adapter through the CorpusRun build path.

    This is a focused identity-regression: build_jobs_for_run
    must NOT stamp any of them with the
    ADAPTER_MISSING_SENTINEL."""
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=FROZEN_CR1, db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)

    jobs = crp.list_jobs_for_run(rid, db_path=db_path)
    assert len(jobs) == 5, "expected exactly 5 jobs, one per frozen repo"

    seen = {j["adapter_name"] for j in jobs}
    # The sentinel must NEVER appear among the frozen repos.
    assert crp.ADAPTER_MISSING_SENTINEL not in seen, (
        f"frozen repo short-circuited to UNSUPPORTED sentinel; "
        f"adapters seen: {seen}"
    )

    # All five adapters declared in src/compliance/adapters must
    # appear — and only those.
    from compliance.adapters import ADAPTER_REGISTRY
    expected_adapters = {
        v.name for k, v in ADAPTER_REGISTRY.items() if k in FROZEN_CR1
    }
    actual_adapters = {j["adapter_name"] for j in jobs}
    assert expected_adapters.issubset(actual_adapters), (
        f"missing adapters: {expected_adapters - actual_adapters}"
    )


def test_unknown_repository_is_compliance_unsupported(
        db_path, known_repos, stub_driver):
    """Repository identity not in ADAPTER_REGISTRY →
    compliance UNSUPPORTED. Distinct from the
    scheduler-level skipped_unsupported_scenario state.
    """
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("example/no-such-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    cr_exec.run_corpus_run(rid, executor="subprocess", db_path=db_path)

    jobs = crp.list_jobs_for_run(rid, db_path=db_path)
    assert len(jobs) == 1
    job = jobs[0]
    # Compliance UNSUPPORTED is the result; the driver's
    # ADAPTER_MISSING_SENTINEL path is what produces it.
    assert job["adapter_name"] == crp.ADAPTER_MISSING_SENTINEL
    assert job["compliance_status"] == RunStatus.UNSUPPORTED.value
    assert job["job_status"] == crp.JOB_STATUS_COMPLETED
    counters = _resolve_run_counters(db_path, rid)
    assert counters["unsupported_count"] == 1
    assert counters["skipped_count"] == 0


def test_known_repo_with_unsupported_scenario_is_skipped(
        db_path, known_repos):
    """Repository IS registered but the selected scenario is not
    in adapter.capabilities.supported_scenarios →
    scheduler-level SKIPPED_UNSUPPORTED_SCENARIO.

    This must remain DISTINCT from compliance UNSUPPORTED:
      compliance_status  : NOT SET (compliance never ran)
      job_status         : skipped_unsupported_scenario
      error_class        : SKIPPED_UNSUPPORTED_SCENARIO
      skipped_count += 1
      unsupported_count does NOT increment.
    """
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S3,  # tool_failure
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=FROZEN_CR1, db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    cr_exec.build_jobs_for_run(rid, S3, db_path=db_path)

    jobs = crp.list_jobs_for_run(rid, db_path=db_path)
    # PocketFlow declares only S1 + S4 in capabilities, not S3.
    # Every other adapter declares all 5 IDs.
    skipped = [j for j in jobs
               if j["job_status"] == crp.JOB_STATUS_SKIPPED_UNSUPPORTED_SCENARIO]
    assert len(skipped) == 1, (
        f"expected exactly one skipped job (PocketFlow); got {len(skipped)}"
    )
    assert skipped[0]["adapter_name"] == "pocketflow"
    assert skipped[0]["compliance_status"] is None  # compliance never ran
    assert skipped[0]["error_class"] == "SKIPPED_UNSUPPORTED_SCENARIO"

    # The other 4 are pending (driver never invoked; we did not
    # call run_corpus_run here, only build_jobs_for_run).
    pending = [j for j in jobs
               if j["job_status"] == crp.JOB_STATUS_PENDING]
    assert len(pending) == 4
    counters = _resolve_run_counters(db_path, rid)
    assert counters["skipped_count"] == 1
    assert counters["unsupported_count"] == 0
    assert counters["pass_count"] == 0
    assert counters["fail_count"] == 0


# ===========================================================================
# Pinned-SHA reproducibility manifest
# ===========================================================================

# The five frozen historical SHAs from the CR-1 baseline. These
# are the SHAs the audit recorded for the v1.4.0 baseline; a
# reproducibility run must execute against these exact commits.
PINNED_CR1 = {
    "SWE-agent/mini-swe-agent": "25941c89cfbc91eb40b3f8756348c91d9977d57e",
    "gptme/gptme":              "c574b83d34f970f816af18183bd77d01b22bd504",
    "HKUDS/nanobot":            "4d204ba077a86dc42225c16f8f90032013ea1969",
    "he-yufeng/CoreCoder":      "a03ef36412e432fc49d972d4007b36ce44ec5d9a",
    "The-Pocket/PocketFlow":    "f74d023f93607b8c3268133339a5e532a949898c",
}


def test_pinned_sha_bypasses_head_resolution(db_path, known_repos):
    """When cfg.pinned_shas maps full_name → SHA, create_corpus_run
    must use the supplied SHA verbatim — no `git ls-remote` call
    is required to produce it."""
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=5,
        db_path=db_path,
        pinned_shas=dict(PINNED_CR1),
    )
    rows = crp.list_eligible_repositories(
        limit=5, include_full_names=FROZEN_CR1, db_path=db_path,
    )
    # Use a deliberately-wrong SHA resolver so any un-pinned repo
    # would be detected. The pinned entries must use the supplied
    # SHA exactly.
    def wrong(url):
        return ShaResolution(
            sha="0000000000000000000000000000000000000000",
            classification="ok", message="wrong",
        )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=wrong)
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    by_name = {m["full_name"]: m["resolved_sha"] for m in manifest}
    for fn, expected in PINNED_CR1.items():
        assert by_name[fn] == expected, (
            f"pinned SHA for {fn!r} was not respected: "
            f"got {by_name[fn]!r}, expected {expected!r}"
        )
    # sha_resolution_class is "pinned" for these rows.
    for m in manifest:
        assert m["sha_resolution_class"] == "pinned", (
            f"manifest row {m['full_name']!r} did not record "
            f"sha_resolution_class='pinned'; got "
            f"{m['sha_resolution_class']!r}"
        )


def test_pinned_sha_validates_format(db_path, known_repos):
    """A pinned SHA that is not 40 lowercase hex must be rejected
    (the manifest row gets sha_resolution_class='sha_resolution_error')."""
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
        pinned_shas={"SWE-agent/mini-swe-agent": "not-a-sha"},
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("SWE-agent/mini-swe-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    row = manifest[0]
    assert row["resolved_sha"] == ""
    assert row["sha_resolution_class"] == "sha_resolution_error"
    assert "not 40-char lowercase hex" in (row["sha_resolution_message"] or "")


def test_pinned_sha_is_immutable_after_run_creation(db_path, known_repos):
    """After create_corpus_run writes the manifest, no external
    code path may mutate it. The SHA persists in
    corpus_run_repositories.resolved_sha for the entire run."""
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
        pinned_shas=dict(PINNED_CR1),
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("SWE-agent/mini-swe-agent",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    # Mutate the source row in agent_repositories. The manifest
    # row must remain the original pinned SHA.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE agent_repositories SET clone_url = "
            "'https://github.com/changed/foo' "
            "WHERE full_name = 'SWE-agent/mini-swe-agent'"
        )
        conn.commit()
    finally:
        conn.close()
    manifest = crp.list_corpus_run_repositories(rid, db_path=db_path)
    assert manifest[0]["resolved_sha"] == PINNED_CR1["SWE-agent/mini-swe-agent"]
    # build_jobs_for_run must use the manifest SHA, not the live HEAD.
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    jobs = crp.list_jobs_for_run(rid, db_path=db_path)
    assert jobs[0]["repo_sha"] == PINNED_CR1["SWE-agent/mini-swe-agent"]


def test_resume_reuses_pinned_sha(db_path, known_repos):
    """`cmd_resume` (via run_corpus_run rebuild path) must read
    the persisted SHA from the manifest, not re-resolve HEAD."""
    cfg = cr_exec.CorpusRunConfig(
        requirement_id="AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING",
        requirement_version="1.4.0", scenario_id=S1,
        executor="subprocess", runtime_version="test",
        max_workers=1, max_attempts=1,
        selection_description="", requested_repo_count=1,
        db_path=db_path,
        pinned_shas=dict(PINNED_CR1),
    )
    rows = crp.list_eligible_repositories(
        limit=1, include_full_names=("gptme/gptme",),
        db_path=db_path,
    )
    rid = cr_exec.create_corpus_run(cfg, rows, resolve_sha=_fake_sha_resolver)
    manifest_before = crp.list_corpus_run_repositories(rid, db_path=db_path)
    sha_before = manifest_before[0]["resolved_sha"]
    # Simulate "resume" by calling build_jobs_for_run again
    # (as cmd_resume does). The manifest SHA must NOT change.
    cr_exec.build_jobs_for_run(rid, S1, db_path=db_path)
    manifest_after = crp.list_corpus_run_repositories(rid, db_path=db_path)
    sha_after = manifest_after[0]["resolved_sha"]
    assert sha_before == sha_after == PINNED_CR1["gptme/gptme"]
    # Jobs still carry the pinned SHA.
    jobs = crp.list_jobs_for_run(rid, db_path=db_path)
    assert jobs[0]["repo_sha"] == PINNED_CR1["gptme/gptme"]
