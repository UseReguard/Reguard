"""DB access helpers for the Corpus Runner orchestration tables.

The four new tables (corpus_runs, corpus_run_repositories,
evaluation_jobs, evaluation_attempts) are pure orchestration
metadata. They never store framework-side evidence — that stays
in `compliance_runtime_runs`, which is the deterministic-result
record per the v1.4.0 frozen contract.

All functions are sqlite-only and synchronous. They are designed
for the v1 corpus runner's single-process usage. They do not
introduce a connection-pool abstraction (none exists today in
the existing pipeline layer).
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable

from compliance.corpus_runner.errors import TerminalizationConflict
from compliance.pipeline.persistence import default_db_path


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# corpus_runs
# ===========================================================================

@dataclass(frozen=True)
class CorpusRunRow:
    id: int
    status: str
    requirement_id: str
    requirement_version: str
    scenario_id: str
    executor: str
    runtime_version: str
    max_workers: int
    max_attempts: int
    selection_description: str
    requested_repo_count: int
    total_jobs: int
    completed_jobs: int
    pass_count: int
    fail_count: int
    unknown_count: int
    unsupported_count: int
    error_count: int
    skipped_count: int
    created_at: str
    started_at: str | None
    completed_at: str | None


def insert_corpus_run(
    *,
    requirement_id: str,
    requirement_version: str,
    scenario_id: str,
    executor: str,
    runtime_version: str,
    max_workers: int,
    max_attempts: int,
    selection_description: str,
    requested_repo_count: int,
    db_path: Path | None = None,
) -> int:
    """Insert a new corpus_run row in 'pending' state. Return new id."""
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT INTO corpus_runs (
                created_at, status, requirement_id, requirement_version,
                scenario_id, executor, runtime_version, max_workers,
                max_attempts, selection_description, requested_repo_count
            ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(), requirement_id, requirement_version, scenario_id,
                executor, runtime_version, max_workers, max_attempts,
                selection_description, requested_repo_count,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def load_corpus_run(corpus_run_id: int,
                    db_path: Path | None = None) -> CorpusRunRow | None:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM corpus_runs WHERE id = ?",
            (corpus_run_id,),
        ).fetchone()
        if row is None:
            return None
        return CorpusRunRow(
            id=row["id"], status=row["status"],
            requirement_id=row["requirement_id"],
            requirement_version=row["requirement_version"],
            scenario_id=row["scenario_id"],
            executor=row["executor"],
            runtime_version=row["runtime_version"],
            max_workers=row["max_workers"],
            max_attempts=row["max_attempts"],
            selection_description=row["selection_description"],
            requested_repo_count=row["requested_repo_count"],
            total_jobs=row["total_jobs"],
            completed_jobs=row["completed_jobs"],
            pass_count=row["pass_count"],
            fail_count=row["fail_count"],
            unknown_count=row["unknown_count"],
            unsupported_count=row["unsupported_count"],
            error_count=row["error_count"],
            skipped_count=row["skipped_count"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
    finally:
        conn.close()


def update_corpus_run_status(corpus_run_id: int, status: str,
                             *, started_at: str | None = None,
                             completed_at: str | None = None,
                             total_jobs: int | None = None,
                             db_path: Path | None = None) -> None:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        sets = ["status = ?"]
        params: list = [status]
        if started_at is not None:
            sets.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            sets.append("completed_at = ?")
            params.append(completed_at)
        if total_jobs is not None:
            sets.append("total_jobs = ?")
            params.append(total_jobs)
        params.append(corpus_run_id)
        conn.execute(
            f"UPDATE corpus_runs SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def increment_corpus_run_counters(
    corpus_run_id: int,
    *,
    completed_jobs_delta: int = 0,
    pass_delta: int = 0,
    fail_delta: int = 0,
    unknown_delta: int = 0,
    unsupported_delta: int = 0,
    error_delta: int = 0,
    skipped_delta: int = 0,
    db_path: Path | None = None,
) -> None:
    """Increment (or decrement) the run-level aggregate counters.

    Pass deltas may be negative (only used by tests).
    """
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            """
            UPDATE corpus_runs SET
                completed_jobs = completed_jobs + ?,
                pass_count      = pass_count + ?,
                fail_count      = fail_count + ?,
                unknown_count   = unknown_count + ?,
                unsupported_count = unsupported_count + ?,
                error_count     = error_count + ?,
                skipped_count   = skipped_count + ?
            WHERE id = ?
            """,
            (
                completed_jobs_delta, pass_delta, fail_delta,
                unknown_delta, unsupported_delta, error_delta,
                skipped_delta, corpus_run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# corpus_run_repositories
# ===========================================================================

def insert_corpus_run_repository(
    *,
    corpus_run_id: int,
    repository_id: int,
    full_name: str,
    clone_url: str,
    resolved_sha: str,
    position: int,
    sha_resolution_class: str | None = None,
    sha_resolution_message: str | None = None,
    db_path: Path | None = None,
) -> int:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT INTO corpus_run_repositories (
                corpus_run_id, repository_id, full_name, clone_url,
                resolved_sha, sha_resolution_class, sha_resolution_message,
                position, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corpus_run_id, repository_id, full_name, clone_url,
                resolved_sha, sha_resolution_class, sha_resolution_message,
                position, _now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_corpus_run_repositories(corpus_run_id: int,
                                 db_path: Path | None = None,
                                 ) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM corpus_run_repositories "
            "WHERE corpus_run_id = ? ORDER BY position ASC",
            (corpus_run_id,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()


# ===========================================================================
# evaluation_jobs
# ===========================================================================

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_SKIPPED_UNSUPPORTED_SCENARIO = "skipped_unsupported_scenario"

ADAPTER_MISSING_SENTINEL = "__MISSING__"


def insert_evaluation_job(
    *,
    corpus_run_id: int,
    repository_id: int,
    repo_sha: str,
    requirement_id: str,
    requirement_version: str,
    scenario_id: str,
    adapter_name: str | None = None,
    adapter_version: str | None = None,
    db_path: Path | None = None,
) -> int:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT INTO evaluation_jobs (
                corpus_run_id, repository_id, repo_sha,
                requirement_id, requirement_version, scenario_id,
                adapter_name, adapter_version, job_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                corpus_run_id, repository_id, repo_sha,
                requirement_id, requirement_version, scenario_id,
                adapter_name, adapter_version, _now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_jobs_for_run(corpus_run_id: int,
                      *, only_status: str | None = None,
                      db_path: Path | None = None,
                      ) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        if only_status is None:
            cur = conn.execute(
                "SELECT * FROM evaluation_jobs WHERE corpus_run_id = ? "
                "ORDER BY id ASC",
                (corpus_run_id,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM evaluation_jobs "
                "WHERE corpus_run_id = ? AND job_status = ? "
                "ORDER BY id ASC",
                (corpus_run_id, only_status),
            )
        return list(cur.fetchall())
    finally:
        conn.close()


def update_evaluation_job_running(job_id: int,
                                  db_path: Path | None = None) -> None:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            "UPDATE evaluation_jobs SET job_status='running', "
            "started_at = ?, attempt_count = attempt_count + 1 "
            "WHERE id = ?",
            (_now(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_evaluation_job_completed(
    job_id: int,
    *,
    compliance_status: str,
    compliance_runtime_run_id: int | None,
    db_path: Path | None = None,
) -> None:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            "UPDATE evaluation_jobs SET job_status='completed', "
            "completed_at = ?, compliance_status = ?, "
            "compliance_runtime_run_id = ? WHERE id = ?",
            (_now(), compliance_status, compliance_runtime_run_id, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_evaluation_job_skipped(
    job_id: int,
    *,
    reason: str,
    db_path: Path | None = None,
) -> None:
    """Mark a job as skipped because the scenario is not supported
    by the resolved adapter. Distinct from terminal compliance
    UNSUPPORTED (which is a real compliance outcome for a repo with
    no adapter at all)."""
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            "UPDATE evaluation_jobs SET job_status = "
            "'skipped_unsupported_scenario', completed_at = ?, "
            "error_class = 'SKIPPED_UNSUPPORTED_SCENARIO', "
            "error_message = ? WHERE id = ?",
            (_now(), reason, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_evaluation_job_error(
    job_id: int,
    *,
    error_class: str,
    error_message: str,
    db_path: Path | None = None,
) -> None:
    """Record the final classifier on the job (only after
    max_attempts has been reached and no retry will happen)."""
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            "UPDATE evaluation_jobs SET error_class = ?, "
            "error_message = ? WHERE id = ?",
            (error_class, error_message, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def find_unsupported_job_for_repo(corpus_run_id: int,
                                   repository_id: int,
                                   db_path: Path | None = None,
                                   ) -> sqlite3.Row | None:
    """Look up an existing job that already carries the
    ADAPTER_MISSING_SENTINEL adapter_name; used to fail fast
    on UNSUPPORTED before doing the costly clone/install."""
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM evaluation_jobs WHERE corpus_run_id = ? "
            "AND repository_id = ? AND adapter_name = ? LIMIT 1",
            (corpus_run_id, repository_id, ADAPTER_MISSING_SENTINEL),
        )
        return cur.fetchone()
    finally:
        conn.close()


def find_job_for_repo(
    *,
    corpus_run_id: int,
    repository_id: int,
    requirement_id: str,
    requirement_version: str,
    scenario_id: str,
    db_path: Path | None = None,
) -> sqlite3.Row | None:
    """Look up an existing job for the v1.1.1 dedup key. Used by
    `build_jobs_for_run` to make job creation idempotent: a second
    call for the same logical job returns the existing row instead
    of raising `sqlite3.IntegrityError` on the unique index."""
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """SELECT * FROM evaluation_jobs
                   WHERE corpus_run_id = ?
                     AND repository_id = ?
                     AND requirement_id = ?
                     AND requirement_version = ?
                     AND scenario_id = ?
                   LIMIT 1""",
            (
                corpus_run_id, repository_id, requirement_id,
                requirement_version, scenario_id,
            ),
        )
        return cur.fetchone()
    finally:
        conn.close()


# ===========================================================================
# evaluation_attempts
# ===========================================================================

def insert_evaluation_attempt(
    *,
    evaluation_job_id: int,
    attempt_number: int,
    worker_id: str | None,
    started_at: str | None = None,
    db_path: Path | None = None,
) -> int:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT INTO evaluation_attempts (
                evaluation_job_id, attempt_number, worker_id,
                started_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                evaluation_job_id, attempt_number, worker_id,
                started_at or _now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_evaluation_attempt_finished(
    attempt_id: int,
    *,
    result_status: str | None,
    error_class: str | None,
    error_message: str | None,
    db_path: Path | None = None,
) -> None:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            """
            UPDATE evaluation_attempts SET
                completed_at = ?,
                result_status = ?,
                error_class = ?,
                error_message = ?
            WHERE id = ?
            """,
            (_now(), result_status, error_class, error_message, attempt_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_attempts_for_job(evaluation_job_id: int,
                          db_path: Path | None = None,
                          ) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM evaluation_attempts "
            "WHERE evaluation_job_id = ? ORDER BY attempt_number ASC",
            (evaluation_job_id,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()


def latest_attempt_for_job(evaluation_job_id: int,
                           db_path: Path | None = None,
                           ) -> sqlite3.Row | None:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM evaluation_attempts "
            "WHERE evaluation_job_id = ? "
            "ORDER BY attempt_number DESC LIMIT 1",
            (evaluation_job_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


# ===========================================================================
# Agent repository selection (read-only)
# ===========================================================================

def list_eligible_repositories(
    *,
    limit: int,
    ordering: str = "stars_desc",
    include_full_names: tuple[str, ...] = (),
    db_path: Path | None = None,
) -> list[sqlite3.Row]:
    """Return up to `limit` rows from agent_repositories.

    The first `len(include_full_names)` rows are the explicit list
    (in the order given). Remaining rows follow `ordering` after
    excluding them. This guarantees the 20-repo gate keeps the five
    known-good repos at the front.
    """
    if limit <= 0:
        return []
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        out: list[sqlite3.Row] = []

        # 1. explicit names
        for fn in include_full_names:
            cur = conn.execute(
                "SELECT * FROM agent_repositories WHERE full_name = ? "
                "AND primary_language = 'Python' "
                "AND relevance_status = 'accepted' AND enabled = 1 "
                "AND archived = 0 AND fork = 0 LIMIT 1",
                (fn,),
            )
            row = cur.fetchone()
            if row is not None:
                out.append(row)
            if len(out) >= limit:
                return out

        remaining = limit - len(out)
        order_sql = {
            "stars_desc": "stars DESC, full_name ASC",
            "pushed_desc": "github_pushed_at DESC, full_name ASC",
            "name_asc":   "full_name ASC",
        }.get(ordering, "stars DESC, full_name ASC")

        if include_full_names:
            placeholders = ",".join("?" * len(include_full_names))
            cur = conn.execute(
                f"""
                SELECT * FROM agent_repositories
                WHERE primary_language = 'Python'
                  AND relevance_status = 'accepted'
                  AND enabled = 1
                  AND archived = 0 AND fork = 0
                  AND full_name NOT IN ({placeholders})
                ORDER BY {order_sql}
                LIMIT ?
                """,
                (*include_full_names, remaining),
            )
        else:
            cur = conn.execute(
                f"""
                SELECT * FROM agent_repositories
                WHERE primary_language = 'Python'
                  AND relevance_status = 'accepted'
                  AND enabled = 1
                  AND archived = 0 AND fork = 0
                ORDER BY {order_sql}
                LIMIT ?
                """,
                (remaining,),
            )
        out.extend(list(cur.fetchall()))
        return out
    finally:
        conn.close()


# ===========================================================================
# v1.1 — additive columns on evaluation_jobs
# ===========================================================================

def update_evaluation_job_recipe_and_missing(
    job_id: int,
    *,
    execution_recipe_id: str | None = None,
    execution_recipe_version: str | None = None,
    missing_capability: str | None = None,
    missing_facts: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Stamp v1.1 additive metadata on an evaluation_job row.

    Only the columns explicitly supplied are updated; the others retain
    their previous values (which may be NULL or a v1.1 default).
    """
    sets: list[str] = []
    params: list = []
    if execution_recipe_id is not None:
        sets.append("execution_recipe_id = ?")
        params.append(execution_recipe_id)
    if execution_recipe_version is not None:
        sets.append("execution_recipe_version = ?")
        params.append(execution_recipe_version)
    if missing_capability is not None:
        sets.append("missing_capability = ?")
        params.append(missing_capability)
    if missing_facts is not None:
        sets.append("missing_facts = ?")
        params.append(missing_facts)
    if not sets:
        return
    params.append(job_id)
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            f"UPDATE evaluation_jobs SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# v1.1 — requirement_evaluations
# ===========================================================================

def insert_requirement_evaluation(
    *,
    evaluation_job_id: int,
    requirement_id: str,
    requirement_version: str,
    compliance_status: str,
    compliance_runtime_run_id: int | None,
    db_path: Path | None = None,
) -> int:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT OR REPLACE INTO requirement_evaluations (
                evaluation_job_id, requirement_id, requirement_version,
                compliance_status, compliance_runtime_run_id, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_job_id, requirement_id, requirement_version,
                compliance_status, compliance_runtime_run_id, _now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_requirement_evaluations_for_job(
    evaluation_job_id: int, db_path: Path | None = None,
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM requirement_evaluations "
            "WHERE evaluation_job_id = ? ORDER BY evaluated_at ASC",
            (evaluation_job_id,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()


# ===========================================================================
# v1.1 — execution_artifacts
# ===========================================================================

def insert_execution_artifact(
    *,
    evaluation_job_id: int,
    artifact_logical_name: str,
    producer: str,
    origin: str,
    size_bytes: int,
    sha256: str,
    mime_or_ext: str | None = None,
    created_during_execution: bool = True,
    framework_created: bool = False,
    truncated: bool = False,
    bytes_available: bool = True,
    host_path: str | None = None,
    db_path: Path | None = None,
) -> int:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            INSERT OR REPLACE INTO execution_artifacts (
                evaluation_job_id, artifact_logical_name, producer, origin,
                size_bytes, sha256, mime_or_ext, created_during_execution,
                framework_created, truncated, bytes_available, host_path,
                captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_job_id, artifact_logical_name, producer, origin,
                size_bytes, sha256, mime_or_ext,
                int(bool(created_during_execution)),
                int(bool(framework_created)),
                int(bool(truncated)),
                int(bool(bytes_available)),
                host_path,
                _now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_execution_artifacts_for_job(
    evaluation_job_id: int, db_path: Path | None = None,
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM execution_artifacts "
            "WHERE evaluation_job_id = ? ORDER BY id ASC",
            (evaluation_job_id,),
        )
        return list(cur.fetchall())
    finally:
        conn.close()


# ===========================================================================
# v1.1 — source_cache_entries
# ===========================================================================

def upsert_source_cache_entry(
    *,
    cache_key: str,
    clone_url: str,
    cache_path: str,
    last_fetch_at: str | None = None,
    last_used_at: str | None = None,
    size_bytes: int = 0,
    state: str = "ok",
    error: str | None = None,
    db_path: Path | None = None,
) -> None:
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        conn.execute(
            """
            INSERT INTO source_cache_entries (
                cache_key, clone_url, cache_path, last_fetch_at,
                last_used_at, size_bytes, state, error, refcount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(cache_key) DO UPDATE SET
                clone_url = excluded.clone_url,
                cache_path = excluded.cache_path,
                last_fetch_at = COALESCE(excluded.last_fetch_at,
                                         source_cache_entries.last_fetch_at),
                last_used_at = COALESCE(excluded.last_used_at,
                                        source_cache_entries.last_used_at),
                size_bytes = excluded.size_bytes,
                state = excluded.state,
                error = excluded.error
            """,
            (
                cache_key, clone_url, cache_path, last_fetch_at,
                last_used_at, size_bytes, state, error,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_source_cache_entries(
    db_path: Path | None = None,
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM source_cache_entries ORDER BY size_bytes DESC"
        )
        return list(cur.fetchall())
    finally:
        conn.close()


# ===========================================================================
# v1.1.2 — atomic terminalization (single-transaction + busy retry)
# ===========================================================================
#
# CR-3 persistence hardening (run 11 / 2026-08-29):
#
# The previous terminalization path persisted terminal state in three
# separate sqlite3 connections per job. A transient
# `sqlite3.OperationalError: database is locked` from concurrent
# connections could skip the v1.1 stamping step
# (`update_evaluation_job_recipe_and_missing`) without raising,
# leaving the row in a hybrid state. The row for
# `ZhuLinsen/daily_stock_analysis` in corpus_run_id=11 is the
# documented example.
#
# `terminalize_job` runs the three terminal-state writes inside ONE
# BEGIN ... COMMIT block on a SINGLE connection, with bounded
# retry-on-busy. The idempotence guard ensures re-issuing the same
# payload is a no-op. Re-issuing a *different* payload raises
# `TerminalizationConflict` so the executor surfaces a deterministic
# INTERNAL_SCHEDULER_ERROR attempt error rather than silently
# overwriting one verdict with another.
#
# RC2 reliability hardening: the connection now applies a
# `busy_timeout` PRAGMA so SQLite itself blocks each write for up
# to ``_TERMINALIZE_BUSY_TIMEOUT_MS`` ms waiting for the lock to
# clear, instead of returning ``database is locked`` immediately
# with timeout=0. The application-level outer retry loop is
# retained as a backstop for genuinely contended paths (e.g. a
# long-held OS-level lock beyond SQLite's own mutex) but it no
# longer does the heavy lifting for ordinary contention — SQLite's
# built-in busy handler does.


_BUSY_MSG_RE = re.compile(
    r"(database is locked|database table is locked|locked|busy)",
    re.IGNORECASE,
)


# Busy-handler timeout applied to every connection opened by
# terminalize_job. SQLite blocks the calling thread for up to this
# many ms before raising ``database is locked``. 5 s is sufficient
# for the test regime (4 worker threads, 500 jobs, single SQLite
# file) because the lock turnover per write is sub-millisecond on
# a clean local filesystem; the wait is rarely invoked and almost
# always resolved before the timeout expires.
_TERMINALIZE_BUSY_TIMEOUT_MS = 5000

# Outer retry budget for terminalize_job. With
# ``busy_timeout=5000`` the inner writes normally succeed without
# raising; this loop is a backstop for genuinely contended paths.
# 10 attempts × exponential backoff capped at 5 s ≈ 25 s worst
# case — enough to absorb contention that exceeds the per-connection
# busy timeout but bounded so a real persistence failure surfaces
# promptly.
_TERMINALIZE_OUTER_ATTEMPTS = 10
_TERMINALIZE_BACKOFF_BASE_S = 0.05
_TERMINALIZE_BACKOFF_CAP_S = 5.0


def _execute_with_busy_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
    *,
    attempts: int = 5,
    base_sleep_s: float = 0.02,
) -> None:
    """Execute `conn.execute(sql, params)` with bounded retry on
    busy/locked `OperationalError`.

    Only retries the explicit "busy / locked" family of
    `OperationalError`. Any other `OperationalError` (disk I/O,
    schema mismatch, corrupt DB) propagates immediately. The caller
    is responsible for transaction boundaries (`BEGIN` / `COMMIT` /
    `ROLLBACK`); this helper does not start or end a transaction.

    Note: terminalize_job does NOT use this helper. It relies on
    the connection's ``busy_timeout`` PRAGMA for lock wait, and
    the outer loop in terminalize_job for the rare genuinely-
    contended case. This helper is retained for the other
    code paths that open ``timeout=0`` connections.
    """
    last_exc: sqlite3.OperationalError | None = None
    for i in range(attempts):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as exc:
            if not _BUSY_MSG_RE.search(str(exc)):
                raise
            last_exc = exc
            time.sleep(base_sleep_s * (2 ** i))
    # Exhausted: surface the last busy/locked OperationalError.
    assert last_exc is not None  # for type-checkers
    raise last_exc


@dataclass(frozen=True)
class TerminalPayload:
    """All structured fields persisted by a single
    `terminalize_job` call.

    A frozen payload is the v1.1.2 narrowing of the executor's
    terminal-state writes: every terminal-state column is now
    written in one transaction, so there is no longer a hybrid
    pre-terminal / terminal state to reason about. This dataclass
    is intentionally frozen; callers must construct a new payload
    for any retry-with-different-fields (which will raise
    TerminalizationConflict on the second terminalize_job call).
    """
    job_id: int
    compliance_status: str       # PASS / FAIL / UNKNOWN / ERROR / UNSUPPORTED
    compliance_runtime_run_id: int | None
    missing_capability: str | None  # 'compatible_execution_recipe' |
                                     # 'tool_failure_scenario' | None
    execution_recipe_id: str         # 'legacy-adapter-direct'
    execution_recipe_version: str    # 'v1.1'
    error_class: str                # '' for non-ERROR
    error_message: str              # '' or full message
    completed_at: str               # UTC ISO-8601 with 'Z'
    requirement_id: str             # for requirement_evaluations dedup
    requirement_version: str        # for requirement_evaluations dedup


def terminalize_job(payload: TerminalPayload, *,
                    db_path: Path | None = None) -> None:
    """Single-transaction terminalization.

    All three writes happen in ONE BEGIN ... COMMIT block:

      1. UPDATE evaluation_jobs SET job_status='completed',
         compliance_status=?, compliance_runtime_run_id=?,
         error_class=?, error_message=?, completed_at=?
         WHERE id=?
         AND (job_status<>'completed'
              OR compliance_status IS NULL
              OR compliance_status = ?)   -- idempotence guard

      2. INSERT OR REPLACE INTO requirement_evaluations (...)
         (dedup key on (evaluation_job_id, requirement_id,
         requirement_version); INSERT OR REPLACE preserves the
         current behaviour).

      3. UPDATE evaluation_jobs SET missing_capability=?,
         execution_recipe_id=?, execution_recipe_version=?
         WHERE id=?

    If step 1's WHERE clause matches 0 rows AND the existing row's
    `compliance_status` differs from the payload, raise
    `TerminalizationConflict` (no silent overwrite).

    All three statements run in a single transaction. The
    connection applies a ``busy_timeout`` PRAGMA so SQLite itself
    blocks the calling thread for up to
    ``_TERMINALIZE_BUSY_TIMEOUT_MS`` ms waiting for the lock to
    clear. The outer retry loop is a backstop for paths that
    exceed the busy timeout (e.g. a long-held OS-level lock);
    its envelope is bounded (``_TERMINALIZE_OUTER_ATTEMPTS``
    iterations of capped exponential backoff).
    """
    completed_at = payload.completed_at or _now()

    # Outer retry loop: a backstop for genuinely contended paths
    # that exceed the per-connection busy_timeout. The
    # busy_timeout on the connection itself does the heavy lifting
    # under ordinary contention.
    for attempt in range(_TERMINALIZE_OUTER_ATTEMPTS):
        # Open a fresh connection per attempt so each retry runs
        # on a clean connection with the busy_timeout re-applied.
        # ``timeout`` (in seconds) is the upper bound on the wait
        # for the lock — match the PRAGMA below for consistency.
        conn = sqlite3.connect(
            db_path or default_db_path(),
            timeout=_TERMINALIZE_BUSY_TIMEOUT_MS / 1000,
        )
        conn.row_factory = sqlite3.Row
        # Apply busy_timeout explicitly. The ``timeout`` arg above
        # sets the same value but is documented as a synonym;
        # applying the PRAGMA makes the contract explicit and
        # protects against any future Python/CPython change that
        # decouples the two. SQLite's ``PRAGMA`` does not accept
        # bound parameters; the value must be interpolated as a
        # literal in the SQL text. The constant is module-private
        # so this is safe from injection.
        conn.execute(
            f"PRAGMA busy_timeout = {_TERMINALIZE_BUSY_TIMEOUT_MS}"
        )
        try:
            # Step 1: idempotence-guarded UPDATE.
            cur = conn.execute(
                """
                UPDATE evaluation_jobs SET
                    job_status = 'completed',
                    compliance_status = ?,
                    compliance_runtime_run_id = ?,
                    error_class = ?,
                    error_message = ?,
                    completed_at = ?
                WHERE id = ?
                  AND (job_status <> 'completed'
                       OR compliance_status IS NULL
                       OR compliance_status = ?)
                """,
                (
                    payload.compliance_status,
                    payload.compliance_runtime_run_id,
                    payload.error_class,
                    payload.error_message,
                    completed_at,
                    payload.job_id,
                    payload.compliance_status,
                ),
            )
            updated = cur.rowcount

            if updated == 0:
                # Either the row doesn't exist (impossible — job_id
                # came from a real `evaluation_jobs` row) OR the
                # row is already terminalised with a different
                # payload. Inspect the existing row to distinguish.
                existing = conn.execute(
                    "SELECT compliance_status FROM evaluation_jobs "
                    "WHERE id = ?",
                    (payload.job_id,),
                ).fetchone()
                if existing is None:
                    raise TerminalizationConflict(
                        f"evaluation_job id={payload.job_id} does not "
                        f"exist; cannot terminalise"
                    )
                if existing["compliance_status"] != payload.compliance_status:
                    raise TerminalizationConflict(
                        f"evaluation_job id={payload.job_id} already "
                        f"terminalised with compliance_status="
                        f"{existing['compliance_status']!r}; refusing "
                        f"to overwrite with "
                        f"{payload.compliance_status!r}"
                    )
                # Same payload: idempotent no-op. Fall through to
                # ensure requirement_evaluations + recipe stamps are
                # consistent.
                pass

            # Step 2: requirement_evaluations row (INSERT OR REPLACE).
            # No nested busy-retry helper here — the connection's
            # busy_timeout handles contention, and the outer loop
            # handles anything that escapes.
            conn.execute(
                """
                INSERT OR REPLACE INTO requirement_evaluations (
                    evaluation_job_id, requirement_id, requirement_version,
                    compliance_status, compliance_runtime_run_id, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.job_id,
                    payload.requirement_id,
                    payload.requirement_version,
                    payload.compliance_status,
                    payload.compliance_runtime_run_id,
                    _now(),
                ),
            )

            # Step 3: recipe / missing-capability stamp.
            conn.execute(
                """
                UPDATE evaluation_jobs SET
                    missing_capability = ?,
                    execution_recipe_id = ?,
                    execution_recipe_version = ?
                WHERE id = ?
                """,
                (
                    payload.missing_capability,
                    payload.execution_recipe_id,
                    payload.execution_recipe_version,
                    payload.job_id,
                ),
            )

            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if not _BUSY_MSG_RE.search(str(exc)):
                raise
            # Busy / locked: roll back the in-flight transaction.
            try:
                conn.rollback()
            except sqlite3.OperationalError:
                pass
            # If we have attempts left, back off deterministically
            # before the next try. Cap the wait so the loop has a
            # hard upper bound.
            if attempt + 1 < _TERMINALIZE_OUTER_ATTEMPTS:
                backoff_s = min(
                    _TERMINALIZE_BACKOFF_BASE_S * (2 ** attempt),
                    _TERMINALIZE_BACKOFF_CAP_S,
                )
                time.sleep(backoff_s)
            # else: fall through to the exhausted-retry raise.
        finally:
            conn.close()
    # Exhausted retries. Surface a deterministic OperationalError so
    # the executor can convert it to an INTERNAL_SCHEDULER_ERROR
    # attempt error.
    raise sqlite3.OperationalError(
        "terminalize_job: exhausted busy/locked retries"
    )


def set_corpus_run_counters_from_jobs(
    corpus_run_id: int,
    *,
    db_path: Path | None = None,
) -> None:
    """Recompute the corpus_runs aggregate counters from the
    evaluation_jobs rows for the run and write them in ONE
    transaction.

    Replaces the per-job `increment_corpus_run_counters` hot path
    used by the executor's terminalization. The caller (the run-end
    hook of `run_corpus_run`) calls this exactly once, after every
    job has terminalised, just before the `corpus_runs.status =
    'completed'` update.

    Counts the five compliance buckets
    (`pass_count`, `fail_count`, `unknown_count`,
    `unsupported_count`, `error_count`) directly from
    `compliance_status`, matching the legacy semantics of
    `increment_corpus_run_counters` (ERROR compliance_status
    contributes to error_count; UNSUPPORTED contributes to
    unsupported_count; etc).

    `error_count` therefore reflects ALL terminal ERROR-class
    outcomes: both compliance_status='ERROR' from the executor
    path AND pre-execution Option-B terminalisations (e.g.
    SHA_RESOLUTION_ERROR rows terminalised at `build_jobs_for_run`
    time, which carry `error_class` but NULL `compliance_status`).
    `skipped_count` is recomputed from
    `job_status='skipped_unsupported_scenario'` rows.
    `completed_jobs` is set to the number of rows whose
    `job_status IN ('completed', 'skipped_unsupported_scenario')`.

    The function is safe to call more than once (idempotent; the
    final state is deterministic given the rows).
    """
    conn = sqlite3.connect(db_path or default_db_path())
    try:
        cur = conn.execute(
            """
            SELECT
                SUM(CASE WHEN compliance_status = 'PASS'
                         THEN 1 ELSE 0 END) AS pass_count,
                SUM(CASE WHEN compliance_status = 'FAIL'
                         THEN 1 ELSE 0 END) AS fail_count,
                SUM(CASE WHEN compliance_status = 'UNKNOWN'
                         THEN 1 ELSE 0 END) AS unknown_count,
                SUM(CASE WHEN compliance_status = 'UNSUPPORTED'
                         THEN 1 ELSE 0 END) AS unsupported_count,
                SUM(CASE WHEN compliance_status = 'ERROR'
                              OR (compliance_status IS NULL
                                  AND job_status = 'completed')
                         THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN job_status = 'skipped_unsupported_scenario'
                         THEN 1 ELSE 0 END) AS skipped_count,
                SUM(CASE WHEN job_status IN
                              ('completed', 'skipped_unsupported_scenario')
                         THEN 1 ELSE 0 END) AS completed_jobs
            FROM evaluation_jobs
            WHERE corpus_run_id = ?
            """,
            (corpus_run_id,),
        )
        row = cur.fetchone()
        conn.execute(
            """
            UPDATE corpus_runs SET
                pass_count = ?,
                fail_count = ?,
                unknown_count = ?,
                unsupported_count = ?,
                error_count = ?,
                skipped_count = ?,
                completed_jobs = ?
            WHERE id = ?
            """,
            (
                int(row[0] or 0),
                int(row[1] or 0),
                int(row[2] or 0),
                int(row[3] or 0),
                int(row[4] or 0),
                int(row[5] or 0),
                int(row[6] or 0),
                corpus_run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# v1.1.2 — structured terminal-state validator
# ===========================================================================


@dataclass(frozen=True)
class ValidationIssue:
    """One detected structural defect in a terminalised
    `evaluation_jobs` row."""
    job_id: int
    full_name: str
    issue_class: str
    detail: str


# Stable issue-class tokens for the validator. These are the same
# tokens used by downstream audits (reconciliation reports,
# inventory scripts) so consumers can grep / aggregate by class.
MALFORMED_UNSUPPORTED_REASON = "MALFORMED_UNSUPPORTED_REASON"
MISSING_REQUIREMENT_EVALUATION = "MISSING_REQUIREMENT_EVALUATION"
CONFLICTING_REQUIREMENT_EVALUATION = "CONFLICTING_REQUIREMENT_EVALUATION"
MALFORMED_SKIPPED_SCENARIO = "MALFORMED_SKIPPED_SCENARIO"


def validate_terminal_state(
    corpus_run_id: int,
    *,
    db_path: Path | None = None,
) -> list[ValidationIssue]:
    """Walk every terminal evaluation_job for the run and emit
    `ValidationIssue` rows for malformed terminal states.

    Pure read function; does NOT mutate the DB. Designed to run
    after a `corpus_run` completes, against either the live
    production DB (via `default_db_path`) or any test-fixture DB.

    Issue classes:

      - `MALFORMED_UNSUPPORTED_REASON`:
          `compliance_status='UNSUPPORTED'` but `missing_capability IS NULL`.
          The CR-3 anomaly row for `ZhuLinsen/daily_stock_analysis`
          (job_id=93 in corpus_run_id=11) is the canonical example.
      - `MISSING_REQUIREMENT_EVALUATION`:
          terminal job (job_status='completed' or
          'skipped_unsupported_scenario') has no
          `requirement_evaluations` row.
      - `CONFLICTING_REQUIREMENT_EVALUATION`:
          terminal job's `requirement_evaluations.compliance_status`
          differs from its `evaluation_jobs.compliance_status`.
      - `MALFORMED_SKIPPED_SCENARIO`:
          `job_status='skipped_unsupported_scenario'` but
          `missing_capability <> 'tool_failure_scenario'`.

    Returns the list of issues sorted by `(issue_class, job_id)`
    for stable reporting.
    """
    conn = sqlite3.connect(db_path or default_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT j.id AS job_id,
                   crr.full_name AS full_name,
                   j.compliance_status AS compliance_status,
                   j.job_status AS job_status,
                   j.missing_capability AS missing_capability,
                   (SELECT COUNT(*) FROM requirement_evaluations re
                     WHERE re.evaluation_job_id = j.id) AS re_count,
                   (SELECT re.compliance_status
                       FROM requirement_evaluations re
                      WHERE re.evaluation_job_id = j.id
                      ORDER BY re.evaluated_at DESC LIMIT 1) AS re_status
            FROM evaluation_jobs j
            JOIN corpus_run_repositories crr
              ON crr.corpus_run_id = j.corpus_run_id
             AND crr.repository_id = j.repository_id
            WHERE j.corpus_run_id = ?
              AND j.job_status IN ('completed',
                                   'skipped_unsupported_scenario')
            """,
            (corpus_run_id,),
        ).fetchall()
    finally:
        conn.close()

    issues: list[ValidationIssue] = []
    for r in rows:
        job_id = int(r["job_id"])
        full_name = str(r["full_name"])
        compliance_status = r["compliance_status"]
        job_status = r["job_status"]
        missing_capability = r["missing_capability"]
        re_count = int(r["re_count"])
        re_status = r["re_status"]

        # 1. UNSUPPORTED with NULL missing_capability is the
        # CR-3 anomaly shape.
        if compliance_status == "UNSUPPORTED" and missing_capability is None:
            issues.append(ValidationIssue(
                job_id=job_id, full_name=full_name,
                issue_class=MALFORMED_UNSUPPORTED_REASON,
                detail=(
                    f"compliance_status='UNSUPPORTED' but "
                    f"missing_capability IS NULL"
                ),
            ))

        # 2. Terminal jobs must have a requirement_evaluations row.
        if re_count == 0:
            issues.append(ValidationIssue(
                job_id=job_id, full_name=full_name,
                issue_class=MISSING_REQUIREMENT_EVALUATION,
                detail=(
                    f"job_status='{job_status}' has no "
                    f"requirement_evaluations row"
                ),
            ))
        # 3. requirement_evaluations.compliance_status must agree
        # with evaluation_jobs.compliance_status.
        elif (compliance_status is not None
              and re_status is not None
              and compliance_status != re_status):
            issues.append(ValidationIssue(
                job_id=job_id, full_name=full_name,
                issue_class=CONFLICTING_REQUIREMENT_EVALUATION,
                detail=(
                    f"evaluation_jobs.compliance_status="
                    f"{compliance_status!r} but "
                    f"requirement_evaluations.compliance_status="
                    f"{re_status!r}"
                ),
            ))

        # 4. skipped_unsupported_scenario requires the structured
        # missing_capability token.
        if (job_status == "skipped_unsupported_scenario"
                and missing_capability != "tool_failure_scenario"):
            issues.append(ValidationIssue(
                job_id=job_id, full_name=full_name,
                issue_class=MALFORMED_SKIPPED_SCENARIO,
                detail=(
                    f"job_status='skipped_unsupported_scenario' but "
                    f"missing_capability={missing_capability!r} "
                    f"(expected 'tool_failure_scenario')"
                ),
            ))

    issues.sort(key=lambda i: (i.issue_class, i.job_id))
    return issues

