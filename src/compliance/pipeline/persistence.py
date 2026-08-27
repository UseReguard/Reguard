"""Persist RunRecord into compliance_runtime_runs.

Schema version is pinned at 1. Re-running the same repo + requirement
+ sha + scenario + adapter is a no-op thanks to the unique dedup index.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .types import RunRecord


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