-- 005_compliance_runtime_runs.sql
-- Persists results of deterministic agent-runtime compliance runs.
-- One row per (repository_id, requirement_id, repo_sha, attempt).
-- Schema version 1.

CREATE TABLE IF NOT EXISTS compliance_runtime_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id         INTEGER NOT NULL,
    repo_full_name        TEXT    NOT NULL,
    repo_sha              TEXT    NOT NULL,
    repo_branch           TEXT    NOT NULL DEFAULT 'main',
    requirement_id        TEXT    NOT NULL,
    requirement_version   TEXT    NOT NULL,
    runtime_version       TEXT    NOT NULL,
    adapter_name          TEXT    NOT NULL,
    adapter_version       TEXT    NOT NULL,
    status                TEXT    NOT NULL,           -- PASS | FAIL | UNKNOWN | UNSUPPORTED | ERROR
    reason                TEXT    NOT NULL DEFAULT '',
    result_json           TEXT    NOT NULL DEFAULT '{}',
    evidence_json         TEXT    NOT NULL DEFAULT '{}',
    scenario_id           TEXT    NOT NULL DEFAULT '',
    started_at            TEXT    NOT NULL,
    completed_at          TEXT    NOT NULL,
    duration_seconds      REAL    NOT NULL DEFAULT 0,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    schema_version        TEXT    NOT NULL DEFAULT '1',
    FOREIGN KEY (repository_id) REFERENCES agent_repositories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crr_repo
    ON compliance_runtime_runs (repository_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crr_requirement
    ON compliance_runtime_runs (requirement_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crr_status
    ON compliance_runtime_runs (status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_crr_dedup
    ON compliance_runtime_runs (
        repository_id,
        requirement_id,
        requirement_version,
        repo_sha,
        scenario_id,
        adapter_name,
        adapter_version
    );