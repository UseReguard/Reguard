-- Migration 010: Corpus Runner v1.1 schema additions
--
-- Adds additive columns and tables for execution/evaluation separation
-- and missing-fact bookkeeping. Does NOT modify Article 12(1) v1.4.0
-- semantics. Frozen contract is unaffected.

-- ---------------------------------------------------------------------------
-- Additive columns on existing tables
-- ---------------------------------------------------------------------------

ALTER TABLE evaluation_jobs
    ADD COLUMN execution_recipe_id TEXT NOT NULL DEFAULT 'legacy-adapter-direct';

ALTER TABLE evaluation_jobs
    ADD COLUMN execution_recipe_version TEXT NOT NULL DEFAULT 'v0';

-- Stable-token missing_capability. NULL for PASS/FAIL/UNKNOWN that have
-- no missing capability. For ADAPTER_ERROR: 'compatible_execution_recipe'.
-- For SKIPPED_UNSUPPORTED_SCENARIO: 'tool_failure_scenario'.
ALTER TABLE evaluation_jobs
    ADD COLUMN missing_capability TEXT;

-- JSON list of deterministic fact keys that were missing. NULL when
-- compliance verdict was PASS/FAIL or when missing-facts is not yet
-- surfaced (current Article 12(1) v1.4.0).
ALTER TABLE evaluation_jobs
    ADD COLUMN missing_facts TEXT;

ALTER TABLE compliance_runtime_runs
    ADD COLUMN execution_recipe_id TEXT NOT NULL DEFAULT 'legacy-adapter-direct';

ALTER TABLE compliance_runtime_runs
    ADD COLUMN execution_recipe_version TEXT NOT NULL DEFAULT 'v0';

-- ---------------------------------------------------------------------------
-- New table: requirement_evaluations
--
-- Links one evaluation_job to one (requirement_id, requirement_version)
-- evaluation. v1.1 inserts exactly one row per job (the requirement under
-- evaluation). Future requirements can join to the same evaluation_job_id
-- and reuse the underlying compliance_runtime_runs evidence.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS requirement_evaluations (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    evaluation_job_id        INTEGER     NOT NULL,
    requirement_id           TEXT        NOT NULL,
    requirement_version      TEXT        NOT NULL,
    compliance_status        TEXT        NOT NULL,
    compliance_runtime_run_id INTEGER,
    evaluated_at             DATETIME    NOT NULL,
    FOREIGN KEY (evaluation_job_id) REFERENCES evaluation_jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (compliance_runtime_run_id) REFERENCES compliance_runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_re_job
    ON requirement_evaluations (evaluation_job_id);
CREATE INDEX IF NOT EXISTS idx_re_requirement
    ON requirement_evaluations (requirement_id, requirement_version, evaluated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_re_unique
    ON requirement_evaluations (evaluation_job_id, requirement_id, requirement_version);

-- ---------------------------------------------------------------------------
-- New table: execution_artifacts
--
-- Metadata for selected persisted bytes produced during execution. Bytes
-- may be evicted by cache policy; the DB row remains and the
-- `bytes_available` flag flips to false.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS execution_artifacts (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    evaluation_job_id        INTEGER     NOT NULL,
    artifact_logical_name    TEXT        NOT NULL,
    producer                 TEXT        NOT NULL,
    origin                   TEXT        NOT NULL,
    size_bytes               INTEGER     NOT NULL,
    sha256                   TEXT        NOT NULL,
    mime_or_ext              TEXT,
    created_during_execution INTEGER     NOT NULL DEFAULT 1,
    framework_created        INTEGER     NOT NULL DEFAULT 0,
    truncated                INTEGER     NOT NULL DEFAULT 0,
    bytes_available          INTEGER     NOT NULL DEFAULT 1,
    host_path                TEXT,
    captured_at              DATETIME    NOT NULL,
    FOREIGN KEY (evaluation_job_id) REFERENCES evaluation_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ea_job
    ON execution_artifacts (evaluation_job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ea_unique
    ON execution_artifacts (evaluation_job_id, artifact_logical_name);
CREATE INDEX IF NOT EXISTS idx_ea_sha
    ON execution_artifacts (sha256);
