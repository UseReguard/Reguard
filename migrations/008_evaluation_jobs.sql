-- Migration 008: evaluation_jobs
--
-- A logical evaluation: one (corpus_run, repository, requirement,
-- version, scenario) triple. The scheduler state and the compliance
-- result are kept distinct:
--
--   job.status      : scheduler state — pending | running |
--                     completed | skipped_unsupported_scenario
--   compliance_status: the final five-valued RunStatus from
--                      compliance_runtime_runs (PASS / FAIL / UNKNOWN /
--                      ERROR / UNSUPPORTED). May be null until the job
--                      reaches its terminal state.
--
-- Existing compliance_runtime_runs remains the deterministic-result
-- record. evaluation_jobs references the latest terminal row by
-- `compliance_runtime_run_id`.
--
-- Article 12(1) v1.4.0 frozen contract is unaffected.
--
-- Apply via the corpus-runs migrate script.

CREATE TABLE IF NOT EXISTS evaluation_jobs (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    corpus_run_id            INTEGER     NOT NULL,
    repository_id            INTEGER     NOT NULL,
    repo_sha                 TEXT        NOT NULL,
    requirement_id           TEXT        NOT NULL,
    requirement_version      TEXT        NOT NULL,
    scenario_id              TEXT        NOT NULL,
    adapter_name             TEXT,
    adapter_version          TEXT,
    compliance_status        TEXT,
    compliance_runtime_run_id INTEGER,
    job_status               TEXT        NOT NULL DEFAULT 'pending',
    -- pending | running | completed | skipped_unsupported_scenario
    created_at               DATETIME    NOT NULL,
    started_at               DATETIME,
    completed_at             DATETIME,
    error_class              TEXT,
    error_message            TEXT,
    attempt_count            INTEGER     NOT NULL DEFAULT 0,
    FOREIGN KEY (corpus_run_id) REFERENCES corpus_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (repository_id) REFERENCES agent_repositories(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_ej_run
    ON evaluation_jobs (corpus_run_id, job_status, created_at);
CREATE INDEX IF NOT EXISTS idx_ej_repo
    ON evaluation_jobs (repository_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ej_unique_logical
    ON evaluation_jobs (
        corpus_run_id, repository_id, repo_sha,
        requirement_id, requirement_version, scenario_id
    );
