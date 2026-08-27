-- Migration 004: article_runtime_assessments
--
-- One row per ATOMIC obligation extracted from a law article. The legal
-- corpus stores whole articles as single text blobs in law_articles; this
-- table stores the per-obligation classification produced by the
-- runtime-testability pipeline.
--
-- Two-tier design (mirrors agent_repositories / agent_repository_audits):
--   * `status` (proposed / confirmed / rejected / needs_review) — the
--     mutable review state of an individual assessment.
--   * `classifier` + `reviewer` — provenance of the verdict.
--
-- The pipeline that fills this table does NOT build compliance tests. It
-- only decides whether each obligation is, in principle, deterministically
-- testable against an AI-agent system running under controlled conditions.
-- Actual compliance tests are a downstream concern.
--
-- Atomic decomposition rule:
--   paragraph (required, 1..N)
--   point     (optional, letter or roman)
--   sub_point (optional, roman)
--
-- atomic_id encodes the path within the article (e.g. "12", "12.2",
-- "12.2.b", "12.3.d") and is unique per (celex, article_number).
--
-- Apply with:
--     python3 scripts/migrate_add_article_runtime_assessments.py

CREATE TABLE IF NOT EXISTS article_runtime_assessments (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    celex                    VARCHAR(20) NOT NULL,
    article_number           VARCHAR(20) NOT NULL,
    atomic_id                VARCHAR(50) NOT NULL,
    paragraph                INTEGER,
    point                    VARCHAR(10),
    sub_point                VARCHAR(10),
    text_excerpt             TEXT        NOT NULL,
    full_text_hash           VARCHAR(64),
    classification           VARCHAR(40) NOT NULL,
    agent_system_relevant    BOOLEAN     NOT NULL DEFAULT 1,
    applicability_note       TEXT,
    testability_rule_json    TEXT,
    notes                    TEXT,
    status                   VARCHAR(20) NOT NULL DEFAULT 'proposed',
    classifier               VARCHAR(100) NOT NULL,
    reviewer                 VARCHAR(100),
    created_at               DATETIME    NOT NULL,
    updated_at               DATETIME    NOT NULL,
    FOREIGN KEY (celex) REFERENCES laws (celex),
    UNIQUE (celex, article_number, atomic_id)
);

CREATE INDEX IF NOT EXISTS ix_ara_celex       ON article_runtime_assessments (celex);
CREATE INDEX IF NOT EXISTS ix_ara_article     ON article_runtime_assessments (celex, article_number);
CREATE INDEX IF NOT EXISTS ix_ara_class       ON article_runtime_assessments (classification);
CREATE INDEX IF NOT EXISTS ix_ara_status      ON article_runtime_assessments (status);
CREATE INDEX IF NOT EXISTS ix_ara_atomic      ON article_runtime_assessments (celex, article_number, atomic_id);
