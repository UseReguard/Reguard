-- Migration 007: corpus_run_repositories
--
-- Frozen run manifest: one row per (corpus_run_id, repository_id).
-- The resolved_sha is computed once at run-start; it is immutable
-- thereafter. The same repository may participate in different
-- CorpusRuns at different SHAs.
--
-- Article 12(1) v1.4.0 frozen contract is unaffected.
--
-- Apply with:
--     python3 scripts/migrate_add_corpus_runs.py (single apply
--     covers 006–009 with executescript).

CREATE TABLE IF NOT EXISTS corpus_run_repositories (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    corpus_run_id            INTEGER     NOT NULL,
    repository_id            INTEGER     NOT NULL,
    full_name                TEXT        NOT NULL,
    clone_url                TEXT        NOT NULL,
    resolved_sha             TEXT        NOT NULL,
    sha_resolution_class     TEXT,
    -- ok | sha_resolution_error | clone_error | checkout_error
    sha_resolution_message   TEXT,
    position                 INTEGER     NOT NULL DEFAULT 0,
    created_at               DATETIME    NOT NULL,
    FOREIGN KEY (corpus_run_id) REFERENCES corpus_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (repository_id) REFERENCES agent_repositories(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_crr_repo_run_id
    ON corpus_run_repositories (corpus_run_id, position);
CREATE UNIQUE INDEX IF NOT EXISTS idx_crr_run_repo_unique
    ON corpus_run_repositories (corpus_run_id, repository_id);
