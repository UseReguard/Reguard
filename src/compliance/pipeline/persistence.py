"""Persist RunRecord into compliance_runtime_runs.

Schema version is pinned at 1. Re-running the same repo + requirement
+ sha + scenario + adapter is a no-op thanks to the unique dedup index;
the loader returns the previously persisted row rather than letting
the insert fire.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .types import Evidence, RepositoryTarget, Result, RunRecord, RunStatus


def default_db_path() -> Path:
    """Locate the repo's data/eu_ai_compliance.db.

    The pipeline package lives under src/compliance/pipeline; the
    data dir is at the repo root, three levels up from this file.
    """
    return Path(__file__).resolve().parents[3] / "data" / "eu_ai_compliance.db"


def insert_run(db_path: Path, record: RunRecord) -> int:
    """Insert a new compliance runtime run. Returns the new row id.

    Raises sqlite3.IntegrityError if the dedup unique index fires
    (same repo + requirement + sha + scenario + adapter triple).
    Callers that want idempotent behaviour should check
    `load_run_by_dedup_key` first; that avoids the IntegrityError
    path entirely.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT OR ABORT INTO compliance_runtime_runs (
                repository_id, repo_full_name, repo_sha, repo_branch,
                requirement_id, requirement_version, runtime_version,
                adapter_name, adapter_version,
                status, reason, result_json, evidence_json, scenario_id,
                started_at, completed_at, duration_seconds, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.repository.repository_id,
                record.repository.full_name,
                record.repository.sha,
                record.repository.branch,
                record.requirement_id,
                record.requirement_version,
                record.runtime_version,
                record.adapter_name,
                record.adapter_version,
                record.status.value,
                record.reason,
                record.result_json(),
                record.evidence_json(),
                record.scenario_id,
                record.started_at,
                record.completed_at,
                record.duration_seconds,
                "1",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    """Reconstruct a RunRecord from a sqlite3.Row.

    The two JSON columns are deserialised into their dataclass types
    using ``__init__``. Everything else is taken verbatim from the
    row columns.
    """
    evidence = Evidence(**json.loads(row["evidence_json"]))
    result = Result(**json.loads(row["result_json"]))
    return RunRecord(
        repository=RepositoryTarget(
            repository_id=row["repository_id"],
            full_name=row["repo_full_name"],
            sha=row["repo_sha"],
            branch=row["repo_branch"],
        ),
        requirement_id=row["requirement_id"],
        requirement_version=row["requirement_version"],
        runtime_version=row["runtime_version"],
        adapter_name=row["adapter_name"],
        adapter_version=row["adapter_version"],
        scenario_id=row["scenario_id"],
        status=RunStatus(row["status"]),
        reason=row["reason"],
        result=result,
        evidence=evidence,
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        duration_seconds=row["duration_seconds"],
    )


def load_run_by_dedup_key(
    db_path: Path,
    *,
    repository_id: int,
    requirement_id: str,
    requirement_version: str,
    repo_sha: str,
    scenario_id: str,
    adapter_name: str,
    adapter_version: str,
) -> RunRecord | None:
    """Return the previously persisted RunRecord for this dedup key.

    The dedup key mirrors the unique index in
    migrations/005_compliance_runtime_runs.sql: every column that
    identifies "the same run" is included.

    Returns None if no row exists. Used by `run_one` to short-circuit
    re-runs: if a row is already there, the previously persisted
    result is returned without re-running the probe or re-inserting.
    The unique index then never fires for legitimate reruns.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT * FROM compliance_runtime_runs
            WHERE repository_id = ?
              AND requirement_id = ?
              AND requirement_version = ?
              AND repo_sha = ?
              AND scenario_id = ?
              AND adapter_name = ?
              AND adapter_version = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                repository_id,
                requirement_id,
                requirement_version,
                repo_sha,
                scenario_id,
                adapter_name,
                adapter_version,
            ),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_record(row)
    finally:
        conn.close()


def recent_runs(
    db_path: Path,
    *,
    limit: int = 20,
    requirement_id: str | None = None,
) -> Iterable[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if requirement_id:
            cur = conn.execute(
                """
                SELECT * FROM compliance_runtime_runs
                WHERE requirement_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (requirement_id, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM compliance_runtime_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return list(cur.fetchall())
    finally:
        conn.close()