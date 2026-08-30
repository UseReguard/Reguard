-- Migration 009: evaluation_attempts
--
-- Every execution attempt of an EvaluationJob. Preserves the original
-- ERROR even when a later retry succeeds. attempt_number is 1-based.
--
-- Article 12(1) v1.4.0 frozen contract is unaffected.
--
-- Apply via the corpus-runs migrate script.

CREATE TABLE IF NOT EXISTS evaluation_attempts (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    evaluation_job_id        INTEGER     NOT NULL,
    attempt_number           INTEGER     NOT NULL,
    worker_id                TEXT,
    started_at               DATETIME    NOT NULL,
    completed_at             DATETIME,
    result_status            TEXT,
    error_class              TEXT,
    error_message            TEXT,
    FOREIGN KEY (evaluation_job_id) REFERENCES evaluation_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ea_job
    ON evaluation_attempts (evaluation_job_id, attempt_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ea_unique_attempt
    ON evaluation_attempts (evaluation_job_id, attempt_number);
