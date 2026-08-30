"""Bounded in-process worker pool + resource governor for Corpus Runner v1.

This is intentionally a single-process executor. It enforces:

  * `--max-workers N` (default 1) — pool size,
  * `--max-active-containers M` (default same as N) — bounded
    admission control on the simulator/hardware side; counts an
    "active container" as one in-flight probe execution,
  * retry of transient ERROR classes only.

It does NOT use an external queue, a separate worker process, a
DB-backed job table, or any multi-host primitive. The Corpus Runner
v1 stop conditions explicitly forbid those.

Each worker thread takes one EvaluationJob at a time, drives the
deterministic pipeline, persists a single compliance_runtime_runs
row, and writes the aggregate counters. The existing
`compliance-check.py`-equivalent flow lives in
`compliance.pipeline.driver.run_one`; the executor invokes it
synchronously per attempt.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Callable

from compliance.adapters import get_adapter
from compliance.adapters.base import AdapterCapabilities
from compliance.corpus_runner import persistence as crp
from compliance.corpus_runner.cache.source_cache import SourceCache
from compliance.corpus_runner.errors import (
    ADAPTER_ERROR,
    CHECKOUT_ERROR,
    CLONE_ERROR,
    CONTAINER_START_ERROR,
    INTERNAL_SCHEDULER_ERROR,
    INSTALL_ERROR,
    PROBE_ERROR,
    SHA_RESOLUTION_ERROR,
    TIMEOUT,
    classify_probe_status,
    is_retryable,
)
from compliance.corpus_runner.materializer import (
    MaterializationMetrics,
    RepositoryMaterializer,
)
from compliance.corpus_runner.scenarios import (
    LEGACY_S1,
    S1,
    is_supported_by_capability,
)
from compliance.corpus_runner.workspace.manager import (
    WorkspaceManager,
    truncate_log,
)

from compliance.pipeline.driver import run_one as driver_run_one
from compliance.pipeline.types import RunStatus

log = logging.getLogger(__name__)


# ===========================================================================
# Configuration / result objects
# ===========================================================================

@dataclass(frozen=True)
class CorpusRunConfig:
    requirement_id: str
    requirement_version: str
    scenario_id: str
    executor: str             # 'subprocess' | 'container'
    runtime_version: str
    max_workers: int
    max_attempts: int
    selection_description: str
    requested_repo_count: int
    db_path: Path | None = None
    pinned_shas: dict[str, str] | None = None
    """Optional reproducibility map: full_name → 40-hex SHA.

    When provided, every full_name in this map bypasses the
    `git ls-remote HEAD` resolver and uses the supplied SHA
    instead. The supplied SHA is validated as 40 lowercase
    hex characters. Names not present in the map fall back
    to the live resolver. The manifest is then frozen with
    these SHAs and behaves identically to a live-resolved
    run thereafter.
    """


@dataclass
class CorpusRunProgress:
    corpus_run_id: int
    total_jobs: int = 0
    completed_jobs: int = 0
    pass_count: int = 0
    fail_count: int = 0
    unknown_count: int = 0
    unsupported_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    per_status: dict[str, int] = field(default_factory=dict)
    error_class_counts: dict[str, int] = field(default_factory=dict)
    active_containers_peak: int = 0
    materialization_metrics: dict = field(default_factory=dict)

    def snapshot_line(self) -> str:
        return (
            f"completed {self.completed_jobs} / {self.total_jobs} ; "
            f"PASS={self.pass_count} FAIL={self.fail_count} "
            f"UNKNOWN={self.unknown_count} UNSUPPORTED={self.unsupported_count} "
            f"ERROR={self.error_count} SKIPPED={self.skipped_count} "
            f"peak_active_containers={self.active_containers_peak}"
        )


# ===========================================================================
# Phase 0 — create the run + SHA snapshot manifest
# ===========================================================================

def create_corpus_run(
    cfg: CorpusRunConfig,
    eligible_rows: list[sqlite3.Row],
    resolve_sha: Callable[[str], "object"] | None = None,
) -> int:
    """Insert a corpus_run row plus a frozen manifest.

    `resolve_sha(clone_url)` returns a `ShaResolution` (or None to
    use the default `git ls-remote HEAD` resolution). It is
    parameterised so tests can inject deterministic stubs.

    If `cfg.pinned_shas` is set, each full_name present in the
    map bypasses the resolver and uses the supplied SHA. SHAs
    are validated as 40 lowercase hex; an invalid SHA causes
    `ShaResolutionError` and the manifest row is stamped with
    that classification.

    Returns the corpus_run_id."""
    crp.insert_corpus_run(
        requirement_id=cfg.requirement_id,
        requirement_version=cfg.requirement_version,
        scenario_id=cfg.scenario_id,
        executor=cfg.executor,
        runtime_version=cfg.runtime_version,
        max_workers=cfg.max_workers,
        max_attempts=cfg.max_attempts,
        selection_description=cfg.selection_description,
        requested_repo_count=cfg.requested_repo_count,
        db_path=cfg.db_path,
    )
    # Last-inserted ID
    conn = sqlite3.connect(cfg.db_path or crp.default_db_path())
    try:
        rid = conn.execute(
            "SELECT id FROM corpus_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()

    # Resolve SHAs and insert manifest rows.
    # Imported lazily to avoid a cycle.
    from compliance.corpus_runner.sha_resolver import (
        ShaResolution,
        _SHA_RE,
        resolve_remote_sha,
    )

    pinned = cfg.pinned_shas or {}
    for position, row in enumerate(eligible_rows):
        clone_url = row["clone_url"]
        full_name = row["full_name"]
        if full_name in pinned:
            sha = pinned[full_name]
            if _SHA_RE.match(sha):
                res = ShaResolution(
                    sha=sha,
                    classification="pinned",
                    message="supplied via cfg.pinned_shas",
                )
            else:
                res = ShaResolution(
                    sha=None,
                    classification="sha_resolution_error",
                    message=(
                        f"pinned SHA for {full_name!r} is not 40-char "
                        f"lowercase hex: {sha!r}"
                    ),
                )
        elif resolve_sha is None:
            res = resolve_remote_sha(clone_url)
        else:
            res = resolve_sha(clone_url)
        crp.insert_corpus_run_repository(
            corpus_run_id=rid,
            repository_id=row["id"],
            full_name=full_name,
            clone_url=clone_url,
            resolved_sha=res.sha or "",
            position=position,
            sha_resolution_class=res.classification,
            sha_resolution_message=res.message,
            db_path=cfg.db_path,
        )

    crp.update_corpus_run_status(rid, "pending", total_jobs=0,
                                  db_path=cfg.db_path)
    return rid


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# Job construction
# ===========================================================================

def build_jobs_for_run(
    corpus_run_id: int,
    scenario_id: str,
    db_path: Path | None = None,
) -> int:
    """For each resolved repository in the run, create one
    EvaluationJob. If an adapter exists and supports the scenario,
    the job carries the adapter_name. If no adapter exists the job
    is created with `adapter_name = '__MISSING__'`; it will be
    short-circuited to UNSUPPORTED before any clone/probe work.

    IDEMPOTENT (v1.1.1): calling `build_jobs_for_run` more than once
    on the same `corpus_run_id` is safe. Already-existing jobs are
    detected via the existing
    `idx_ej_unique_logical (corpus_run_id, repository_id, repo_sha,
    requirement_id, requirement_version, scenario_id)` index; the
    function returns the count of already-existing jobs plus any
    newly-created ones, and never raises `sqlite3.IntegrityError` on
    a duplicate. Re-running the function never mutates prior job rows
    and never double-counts in `corpus_runs` aggregate counters.

    Returns the number of jobs the run now has (existing + newly
    created).
    """
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        # Pull run requirements.
        run_row = conn.execute(
            "SELECT requirement_id, requirement_version FROM corpus_runs WHERE id = ?",
            (corpus_run_id,),
        ).fetchone()
        requirement_id = run_row[0]
        requirement_version = run_row[1]

        manifest = conn.execute(
            "SELECT repository_id, full_name, resolved_sha, "
            "sha_resolution_class FROM corpus_run_repositories "
            "WHERE corpus_run_id = ? ORDER BY position ASC",
            (corpus_run_id,),
        ).fetchall()
    finally:
        conn.close()

    created = 0
    for rid, full_name, resolved_sha, sha_class in manifest:
        # Skip SHA resolution failures at job-creation: the job
        # is created with empty sha and an error class stamped
        # immediately, so it surfaces in counts. Pinned SHAs from
        # the `--manifest` flag use sha_class="pinned" which is
        # equivalent to "ok" for the purposes of job creation —
        # the SHA was supplied verbatim by the host and is
        # accepted at face value.
        adapter_name: str | None
        adapter_version: str | None
        if not resolved_sha or sha_class not in ("ok", "pinned"):
            adapter_name = crp.ADAPTER_MISSING_SENTINEL
            adapter_version = ""
            # v1.1.1 idempotence: detect existing short-circuit row.
            existing = crp.find_job_for_repo(
                corpus_run_id=corpus_run_id,
                repository_id=rid,
                requirement_id=requirement_id,
                requirement_version=requirement_version,
                scenario_id=scenario_id,
                db_path=db_path,
            )
            if existing is not None:
                created += 1
                continue
            conn = sqlite3.connect(db_path or crp.default_db_path())
            try:
                conn.execute(
                    """
                    INSERT INTO evaluation_jobs (
                        corpus_run_id, repository_id, repo_sha,
                        requirement_id, requirement_version, scenario_id,
                        adapter_name, adapter_version, job_status,
                        compliance_status, error_class, error_message,
                        started_at, completed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        corpus_run_id, rid, resolved_sha,
                        requirement_id, requirement_version, scenario_id,
                        adapter_name, adapter_version,
                        crp.JOB_STATUS_COMPLETED,
                        SHA_RESOLUTION_ERROR,
                        "sha resolution failed at snapshot time",
                        _now(), _now(), _now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            crp.increment_corpus_run_counters(
                corpus_run_id,
                completed_jobs_delta=1, error_delta=1,
                db_path=db_path,
            )
            created += 1
            continue

        # Adapter resolution.
        try:
            ad = get_adapter(full_name)
            capability: AdapterCapabilities = ad.capabilities
            adapter_name = ad.name
            adapter_version = ad.version
            scenario_supported = is_supported_by_capability(
                scenario_id, capability_set=capability.supported_scenarios)
        except KeyError:
            adapter_name = crp.ADAPTER_MISSING_SENTINEL
            adapter_version = ""
            scenario_supported = True  # never reached; sentinel short-circuits

        # v1.1.1 idempotence: detect existing job for the dedup key
        # before inserting. If present, do not insert again and do
        # not increment counters.
        existing = crp.find_job_for_repo(
            corpus_run_id=corpus_run_id,
            repository_id=rid,
            requirement_id=requirement_id,
            requirement_version=requirement_version,
            scenario_id=scenario_id,
            db_path=db_path,
        )
        if existing is not None:
            created += 1
            continue

        job_id = crp.insert_evaluation_job(
            corpus_run_id=corpus_run_id,
            repository_id=rid,
            repo_sha=resolved_sha,
            requirement_id=requirement_id,
            requirement_version=requirement_version,
            scenario_id=scenario_id,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            db_path=db_path,
        )
        if not scenario_supported:
            crp.update_evaluation_job_skipped(
                job_id,
                reason=(
                    f"scenario {scenario_id!r} not in adapter "
                    f"{adapter_name!r} capability.supported_scenarios"
                ),
                db_path=db_path,
            )
            crp.increment_corpus_run_counters(
                corpus_run_id,
                completed_jobs_delta=1, skipped_delta=1,
                db_path=db_path,
            )
        created += 1

    crp.update_corpus_run_status(
        corpus_run_id, "pending", started_at=_now(),
        total_jobs=created, db_path=db_path,
    )
    return created


# ===========================================================================
# Worker pool
# ===========================================================================

class ActiveContainerCounter:
    """Tracks the number of in-flight probe executions.

    The counter is *not* a perfect host-level measurement; for v1 it
    exists to enforce admission control at the runner level. A real
    cgroup / OCI-runtime query is out of scope.
    """

    def __init__(self, max_active: int) -> None:
        self.max_active = max_active
        self._value = 0
        self._peak = 0
        self._lock_path: Path | None = None
        self._slots = _SemaphoreLike(max_active)

    def acquire(self) -> bool:
        if not self._slots.acquire():
            return False
        self._value += 1
        if self._value > self._peak:
            self._peak = self._value
        return True

    def release(self) -> None:
        self._value = max(0, self._value - 1)
        self._slots.release()

    @property
    def peak(self) -> int:
        return self._peak


class _SemaphoreLike:
    """Tiny semaphore; stdlib's threading.Semaphore is fine but
    keeping the dependency surface tight helps test determinism."""

    def __init__(self, n: int) -> None:
        self._n = n

    def acquire(self) -> bool:
        if self._n <= 0:
            return False
        self._n -= 1
        return True

    def release(self) -> None:
        self._n += 1


# ===========================================================================
# Job execution (one attempt)
# ===========================================================================

def _execute_one_attempt(
    *,
    job_id: int,
    attempt_number: int,
    full_name: str,
    repo_sha: str,
    requirement_id: str,
    worker_id: str,
    executor: str,
    db_path: Path | None = None,
    materializer: "RepositoryMaterializer | None" = None,
) -> tuple[str | None, str | None, str | None, int | None]:
    """Execute one attempt of one job. Returns
    (compliance_status, error_class, error_message,
    compliance_runtime_run_id).

    Compliance statuses:
      PASS / FAIL / UNKNOWN / ERROR / UNSUPPORTED
    plus the synthetic ADAPTER_MISSING_SENTINEL → UNSUPPORTED
    short-circuit applied via `compliance_status = UNSUPPORTED`.

    Returns (None, INTERNAL_SCHEDULER_ERROR, "...", None) on
    unexpected exceptions so the runner can classify.

    v1.1.1 wiring: when a `materializer` is supplied, the attempt is
    executed against a per-attempt workspace prepared by the
    `RepositoryMaterializer` (SourceCache + WorkspaceManager). The
    workspace is destroyed before this function returns; cache state
    is not part of the compliance verdict.
    """
    attempt_id = crp.insert_evaluation_attempt(
        evaluation_job_id=job_id,
        attempt_number=attempt_number,
        worker_id=worker_id,
        db_path=db_path,
    )

    prepared = None
    try:
        # Check the sentinel for fast UNSUPPORTED.
        conn = sqlite3.connect(db_path or crp.default_db_path())
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT adapter_name FROM evaluation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            adapter_name = row["adapter_name"]
        finally:
            conn.close()

        if adapter_name == crp.ADAPTER_MISSING_SENTINEL:
            crp.update_evaluation_attempt_finished(
                attempt_id,
                result_status=RunStatus.UNSUPPORTED.value,
                error_class="",
                error_message="adapter not registered",
                db_path=db_path,
            )
            return RunStatus.UNSUPPORTED.value, "", \
                "adapter not registered", None

        # Resolve the manifest entry to learn the clone_url + repo_id
        # so the materializer can prepare a workspace.
        conn = sqlite3.connect(db_path or crp.default_db_path())
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT crr.repository_id, crr.clone_url, crr.full_name
                       FROM corpus_run_repositories crr
                       JOIN evaluation_jobs ej
                         ON ej.corpus_run_id = crr.corpus_run_id
                        AND ej.repository_id = crr.repository_id
                       WHERE ej.id = ? LIMIT 1""",
                (job_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            crp.update_evaluation_attempt_finished(
                attempt_id,
                result_status=RunStatus.ERROR.value,
                error_class=INTERNAL_SCHEDULER_ERROR,
                error_message="manifest row missing for job",
                db_path=db_path,
            )
            return RunStatus.ERROR.value, INTERNAL_SCHEDULER_ERROR, \
                "manifest row missing", None
        clone_url = str(row["clone_url"])
        repository_id = int(row["repository_id"])

        # v1.1.1 path: prepare a workspace via the materializer, then
        # run the pipeline against the prepared snapshot. Falls back
        # to the legacy `driver.run_one` clone path only when no
        # materializer is supplied (e.g. unit tests that exercise the
        # pipeline in isolation).
        from compliance.pipeline.driver import (
            run_one as _legacy_run_one,
            run_with_prepared_checkout,
        )

        if materializer is not None:
            prepared = materializer.prepare(
                repository_id=repository_id,
                clone_url=clone_url,
                repo_sha=repo_sha,
                attempt_id=attempt_id,
            )
            try:
                record = run_with_prepared_checkout(
                    full_name=full_name,
                    sha=repo_sha,
                    repo_checkout=prepared.repository_path,
                    requirement_id=requirement_id,
                    executor=executor,
                )
            finally:
                materializer.cleanup(prepared)
                prepared = None
        else:
            record = _legacy_run_one(
                full_name=full_name,
                sha=repo_sha,
                requirement_id=requirement_id,
            )

        # The driver may have re-resolved an existing RunRecord from
        # a prior run. Extract compliance status; map error class
        # from probe_status if present.
        compliance_status = record.status.value
        err_class = ""
        if compliance_status == RunStatus.ERROR.value:
            err_class = classify_probe_status(
                record.evidence.extra.get("probe_status")
            ) or PROBE_ERROR
        return compliance_status, err_class, record.reason, \
            _find_compliance_runtime_run_id(record)

    except Exception as exc:  # noqa: BLE001
        msg = repr(exc)[:4000]
        crp.update_evaluation_attempt_finished(
            attempt_id,
            result_status=RunStatus.ERROR.value,
            error_class=INTERNAL_SCHEDULER_ERROR,
            error_message=msg,
            db_path=db_path,
        )
        return RunStatus.ERROR.value, INTERNAL_SCHEDULER_ERROR, msg, None
    finally:
        if prepared is not None and materializer is not None:
            try:
                materializer.cleanup(prepared)
            except Exception:  # noqa: BLE001
                log.exception("workspace cleanup failed")


def _find_compliance_runtime_run_id(record) -> int | None:
    """Find the row id of the persisted RunRecord in
    compliance_runtime_runs. The RunRecord does not carry its row
    id, so we look it up by the dedup key."""
    conn = sqlite3.connect(crp.default_db_path())
    try:
        row = conn.execute(
            """
            SELECT id FROM compliance_runtime_runs
            WHERE repo_full_name = ? AND requirement_id = ?
              AND requirement_version = ? AND repo_sha = ?
              AND scenario_id = ? ORDER BY id DESC LIMIT 1
            """,
            (
                record.repository.full_name,
                record.requirement_id,
                record.requirement_version,
                record.repository.sha,
                record.scenario_id,
            ),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


# ===========================================================================
# Top-level runner
# ===========================================================================

@dataclass(frozen=True)
class RunnerResult:
    corpus_run_id: int
    progress: CorpusRunProgress


def run_corpus_run(corpus_run_id: int, *,
                   executor: str = "subprocess",
                   db_path: Path | None = None,
                   on_progress: Callable[[CorpusRunProgress], None] | None = None,
                   container_counter: ActiveContainerCounter | None = None,
                   materializer: RepositoryMaterializer | None = None,
                   ) -> RunnerResult:
    """Drive one CorpusRun end-to-end.

    - Iterates EvaluationJobs ordered by id ASC.
    - Respects max_active_containers via ActiveContainerCounter.
    - Retries ONLY transient-infrastructure errors up to max_attempts.
    - Persists every attempt; never overwrites the first ERROR.
    - Final run-end counter increment + status update.
    """
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        run_row = conn.execute(
            "SELECT max_workers, max_attempts, status FROM corpus_runs "
            "WHERE id = ?", (corpus_run_id,),
        ).fetchone()
        max_workers = int(run_row[0])
        max_attempts = int(run_row[1])
    finally:
        conn.close()

    crp.update_corpus_run_status(
        corpus_run_id, "running", db_path=db_path,
    )

    counter = container_counter or ActiveContainerCounter(max_workers)
    mat = materializer or RepositoryMaterializer()

    progress = CorpusRunProgress(corpus_run_id=corpus_run_id)
    _emit_progress(progress, on_progress)

    # Build list of pending jobs.
    pending = crp.list_jobs_for_run(
        corpus_run_id, only_status=crp.JOB_STATUS_PENDING,
        db_path=db_path,
    )
    progress.total_jobs = len(pending)

    # Use a ThreadPoolExecutor for concurrency; each thread
    # acquires a container slot before running.
    with ThreadPoolExecutor(max_workers=max_workers,
                            thread_name_prefix="corpus") as pool:
        futures = []
        for job in pending:
            futures.append(pool.submit(
                _process_one_job_thread,
                job_id=int(job["id"]),
                full_name=str(job["adapter_name"]),
                attempt_limit=max_attempts,
                executor=executor,
                db_path=db_path,
                counter=counter,
                materializer=mat,
            ))
        # Wait for every job to finish, surfacing exceptions.
        for fut in as_completed(futures):
            fut.result()

    # All threads have completed. v1.1.2 batched recompute of the
    # corpus_runs aggregate counters from the evaluation_jobs rows,
    # done once at run-end (replacing the per-job
    # increment_corpus_run_counters hot path that was the source
    # of the CR-3 persistence defect).
    crp.set_corpus_run_counters_from_jobs(corpus_run_id, db_path=db_path)

    final = crp.load_corpus_run(corpus_run_id, db_path=db_path)
    assert final is not None
    progress.completed_jobs = final.completed_jobs
    progress.pass_count = final.pass_count
    progress.fail_count = final.fail_count
    progress.unknown_count = final.unknown_count
    progress.unsupported_count = final.unsupported_count
    progress.error_count = final.error_count
    progress.skipped_count = final.skipped_count
    progress.active_containers_peak = counter.peak
    progress.error_class_counts = _error_class_counts(
        corpus_run_id, db_path=db_path)

    crp.update_corpus_run_status(
        corpus_run_id, "completed",
        completed_at=_now(), db_path=db_path,
    )
    _emit_progress(progress, on_progress)
    # Stash the materialization metrics on the progress object so the
    # caller / summary writer can persist them alongside the run.
    progress.materialization_metrics = mat.metrics_snapshot()
    return RunnerResult(corpus_run_id=corpus_run_id, progress=progress)


def _emit_progress(progress: CorpusRunProgress,
                   on_progress: Callable[[CorpusRunProgress], None] | None,
                   ) -> None:
    if on_progress is not None:
        try:
            on_progress(progress)
        except Exception:  # noqa: BLE001
            log.exception("progress callback failed")
    else:
        log.info(progress.snapshot_line())


def _error_class_counts(corpus_run_id: int,
                        *, db_path: Path | None) -> dict[str, int]:
    """Aggregate error_class counts across all evaluation_attempts."""
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        rows = conn.execute(
            """
            SELECT a.error_class AS ec, COUNT(*) AS n
            FROM evaluation_attempts a
            JOIN evaluation_jobs j ON j.id = a.evaluation_job_id
            WHERE j.corpus_run_id = ?
              AND a.error_class IS NOT NULL AND a.error_class <> ''
            GROUP BY a.error_class
            """,
            (corpus_run_id,),
        ).fetchall()
        return {r[0]: int(r[1]) for r in rows}
    finally:
        conn.close()


def _process_one_job_thread(*, job_id: int, full_name: str,
                             attempt_limit: int,
                             executor: str, db_path: Path | None,
                             counter: ActiveContainerCounter,
                             materializer: RepositoryMaterializer | None = None) -> None:
    """Worker thread body. Drives one job through attempts with
    retry semantics. Each attempt acquires/releases a container
    slot. Container admission is bounded by the runner's
    ActiveContainerCounter."""
    conn = sqlite3.connect(db_path or crp.default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        job = conn.execute(
            "SELECT * FROM evaluation_jobs WHERE id = ?", (job_id,),
        ).fetchone()
        if job is None:
            return
        repo_id = int(job["repository_id"])
        repo_sha = str(job["repo_sha"])
        requirement_id = str(job["requirement_id"])
        scenario_id = str(job["scenario_id"])
    finally:
        conn.close()

    # Resolve full_name from run manifest so we use the
    # immutable identity.
    corpus_run_id = _run_id_for_job(job_id, db_path=db_path)
    manifest_entry = _lookup_full_name(corpus_run_id, repo_id, db_path=db_path)
    full_name = manifest_entry or full_name

    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

    attempt = 0
    last_status: str | None = None
    last_err_class = ""
    last_err_msg = ""
    last_run_id: int | None = None

    while attempt < attempt_limit:
        attempt += 1
        if not counter.acquire():
            # Should never happen if max_active==max_workers,
            # but defensive.
            crp.insert_evaluation_attempt(
                evaluation_job_id=job_id,
                attempt_number=attempt,
                worker_id=worker_id,
                db_path=db_path,
            )
            # Classify as container admission failure.
            last_status = RunStatus.ERROR.value
            last_err_class = CONTAINER_START_ERROR
            last_err_msg = "admission control refused the slot"
            crp.update_evaluation_attempt_finished(
                crp_latest_attempt_id(job_id, db_path=db_path),
                result_status=last_status,
                error_class=last_err_class,
                error_message=last_err_msg,
                db_path=db_path,
            )
            counter.release()
            break

        crp.update_evaluation_job_running(job_id, db_path=db_path)
        try:
            last_status, last_err_class, last_err_msg, last_run_id = \
                _execute_one_attempt(
                    job_id=job_id,
                    attempt_number=attempt,
                    full_name=full_name,
                    repo_sha=repo_sha,
                    requirement_id=requirement_id,
                    worker_id=worker_id,
                    executor=executor,
                    db_path=db_path,
                    materializer=materializer,
                )
        finally:
            counter.release()

        # Terminal handling.
        if last_status in ("PASS", "FAIL", "UNKNOWN", "UNSUPPORTED"):
            break
        # ERROR -> retry only if is_retryable(error_class).
        if last_status == "ERROR" and is_retryable(last_err_class) and attempt < attempt_limit:
            continue
        # Otherwise terminal (ERROR with non-retryable class).
        break

    # Persist final outcome (v1.1.2 atomic terminalization).
    if last_status is None:
        last_status = RunStatus.ERROR.value
        last_err_class = last_err_class or INTERNAL_SCHEDULER_ERROR
        last_err_msg = last_err_msg or "no attempt produced a status"

    requirement_version = str(job["requirement_version"]) if "requirement_version" in job.keys() else ""

    missing_capability: str | None = None
    if last_status == RunStatus.UNSUPPORTED.value:
        # The adapter-missing sentinel is the v1 short-circuit. v1.1
        # surfaces it as a structured missing_capability token.
        missing_capability = "compatible_execution_recipe"
    elif last_status == "skipped_unsupported_scenario":
        missing_capability = "tool_failure_scenario"

    try:
        crp.terminalize_job(crp.TerminalPayload(
            job_id=job_id,
            compliance_status=last_status,
            compliance_runtime_run_id=last_run_id,
            missing_capability=missing_capability,
            execution_recipe_id="legacy-adapter-direct",
            execution_recipe_version="v1.1",
            error_class=(last_err_class or PROBE_ERROR)
                       if last_status == RunStatus.ERROR.value else "",
            error_message=last_err_msg if last_status == RunStatus.ERROR.value else "",
            completed_at=_now(),
            requirement_id=str(requirement_id),
            requirement_version=requirement_version,
        ), db_path=db_path)
    except crp.TerminalizationConflict as exc:
        # Two different terminalization calls disagreed on the
        # verdict. The legacy per-call path would have silently
        # overwritten one with the other (PASS vs FAIL corruption).
        # The new path surfaces a deterministic
        # INTERNAL_SCHEDULER_ERROR so the audit trail records the
        # conflict instead.
        log.error(
            "terminalization conflict on job_id=%d: %s",
            job_id, exc,
        )
        # Re-attempt to persist the conflict as an ERROR verdict so
        # the row is still terminalised (otherwise the run can never
        # complete).
        try:
            crp.terminalize_job(crp.TerminalPayload(
                job_id=job_id,
                compliance_status=RunStatus.ERROR.value,
                compliance_runtime_run_id=last_run_id,
                missing_capability=None,
                execution_recipe_id="legacy-adapter-direct",
                execution_recipe_version="v1.1",
                error_class=INTERNAL_SCHEDULER_ERROR,
                error_message=f"terminalization conflict: {exc}",
                completed_at=_now(),
                requirement_id=str(requirement_id),
                requirement_version=requirement_version,
            ), db_path=db_path)
        except sqlite3.OperationalError:
            # If even the conflict-stamp can't land, log and move on;
            # the run-end sweep will pick this up via set_corpus_run_counters_from_jobs
            # which inspects every terminal row.
            log.exception("could not stamp terminalization conflict")
    except sqlite3.OperationalError as exc:
        # Busy / locked retries exhausted inside terminalize_job.
        # Surface this as an attempt-level error and let the
        # run-end sweep clean up. Re-raise so the executor's
        # pool reports the exception.
        log.error(
            "terminalize_job exhausted busy retries on job_id=%d: %s",
            job_id, exc,
        )
        raise
    # Per-job counter bump is no longer done here; the run-end
    # hook of `run_corpus_run` calls
    # `crp.set_corpus_run_counters_from_jobs` ONCE after every
    # job has terminalised.


def _counter_delta_for(status: str) -> dict:
    return {
        "pass_delta": int(status == "PASS"),
        "fail_delta": int(status == "FAIL"),
        "unknown_delta": int(status == "UNKNOWN"),
        "unsupported_delta": int(status == "UNSUPPORTED"),
        "error_delta": int(status == "ERROR"),
        "skipped_delta": 0,
    }


def _lookup_full_name(corpus_run_id: int, repository_id: int,
                      *, db_path: Path | None) -> str | None:
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        row = conn.execute(
            "SELECT full_name FROM corpus_run_repositories "
            "WHERE corpus_run_id = ? AND repository_id = ? LIMIT 1",
            (corpus_run_id, repository_id),
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def _run_id_for_job(job_id: int, *, db_path: Path | None) -> int:
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        row = conn.execute(
            "SELECT corpus_run_id FROM evaluation_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def crp_latest_attempt_id(job_id: int, *,
                          db_path: Path | None) -> int:
    conn = sqlite3.connect(db_path or crp.default_db_path())
    try:
        row = conn.execute(
            """
            SELECT id FROM evaluation_attempts
            WHERE evaluation_job_id = ?
            ORDER BY attempt_number DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ===========================================================================
# JSON progress summary
# ===========================================================================

def write_summary_json(corpus_run_id: int, path: Path,
                       *, db_path: Path | None = None) -> None:
    run = crp.load_corpus_run(corpus_run_id, db_path=db_path)
    if run is None:
        raise KeyError(f"unknown corpus_run_id {corpus_run_id}")
    err_class_counts = _error_class_counts(corpus_run_id, db_path=db_path)
    payload = {
        "schema_version": "1",
        "corpus_run_id": corpus_run_id,
        "status": run.status,
        "requirement_id": run.requirement_id,
        "requirement_version": run.requirement_version,
        "scenario_id": run.scenario_id,
        "executor": run.executor,
        "runtime_version": run.runtime_version,
        "max_workers": run.max_workers,
        "max_attempts": run.max_attempts,
        "requested_repo_count": run.requested_repo_count,
        "total_jobs": run.total_jobs,
        "completed_jobs": run.completed_jobs,
        "pass_count": run.pass_count,
        "fail_count": run.fail_count,
        "unknown_count": run.unknown_count,
        "unsupported_count": run.unsupported_count,
        "error_count": run.error_count,
        "skipped_count": run.skipped_count,
        "error_class_counts": err_class_counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True),
                     encoding="utf-8")
