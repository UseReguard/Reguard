-- Migration 006: corpus_runs
--
-- One row per CorpusRun — a bounded batch evaluation request over
-- a frozen repository selection, requirement version, scenario, and
-- runtime configuration. Article 12(1) v1.4.0 frozen contract is
-- unaffected; this table is orchestration metadata only.
--
-- Apply with:
--     python3 scripts/migrate_add_corpus_runs.py

CREATE TABLE IF NOT EXISTS corpus_runs (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,

    -- Lifecycle
    created_at               DATETIME    NOT NULL,
    started_at               DATETIME,
    completed_at             DATETIME,
    status                   VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | running | completed | failed | cancelled

    -- Compliance identity (frozen for this run)
    requirement_id           TEXT        NOT NULL,
    requirement_version      TEXT        NOT NULL,
    scenario_id              TEXT        NOT NULL,

    -- Execution configuration (frozen for this run)
    executor                 VARCHAR(20) NOT NULL,
    runtime_version          TEXT        NOT NULL,
    max_workers              INTEGER     NOT NULL DEFAULT 1,
    max_attempts             INTEGER     NOT NULL DEFAULT 2,

    -- Selection description (free-form; includes seed, ordering, filters)
    selection_description    TEXT        NOT NULL DEFAULT '',
    requested_repo_count     INTEGER     NOT NULL DEFAULT 0,

    -- Counters maintained at run-end
    total_jobs               INTEGER     NOT NULL DEFAULT 0,
    completed_jobs           INTEGER     NOT NULL DEFAULT 0,
    pass_count               INTEGER     NOT NULL DEFAULT 0,
    fail_count               INTEGER     NOT NULL DEFAULT 0,
    unknown_count            INTEGER     NOT NULL DEFAULT 0,
    unsupported_count        INTEGER     NOT NULL DEFAULT 0,
    error_count              INTEGER     NOT NULL DEFAULT 0,
    skipped_count            INTEGER     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_corpus_runs_status
    ON corpus_runs (status, created_at DESC);
