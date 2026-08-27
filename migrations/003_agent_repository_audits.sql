-- Migration 003: agent_repository_audits + agent_repository_current_status
--
-- Separate the lifecycle of:
--   - agent_repositories.relevance_status   (mutable machine state)
--   - agent_repository_audits               (human / inspection history)
--
-- Audits accumulate per repository so we never lose prior verdicts.
-- A small view (agent_repository_current_status) keeps operational
-- queries ergonomic.
--
-- Apply with:
--     python3 scripts/migrate_add_agent_repository_audits.py

CREATE TABLE IF NOT EXISTS agent_repository_audits (
    id              INTEGER      PRIMARY KEY AUTOINCREMENT,
    repository_id   INTEGER      NOT NULL,
    verdict         VARCHAR(20)  NOT NULL,         -- gold / reject / borderline
    auditor_type    VARCHAR(30)  NOT NULL,         -- human / llm-judge / heuristic-review / deterministic-review
    auditor         VARCHAR(100),                  -- identifier: 'user:marcelo', 'claude-sonnet', 'audit_2026-08-28'
    reason          TEXT,
    audit_batch     VARCHAR(100),                  -- '2026-08-28-gold-bootstrap' etc.
    audited_at      DATETIME      NOT NULL,
    FOREIGN KEY (repository_id) REFERENCES agent_repositories(id)
);

CREATE INDEX IF NOT EXISTS ix_audits_repo    ON agent_repository_audits(repository_id);
CREATE INDEX IF NOT EXISTS ix_audits_batch   ON agent_repository_audits(audit_batch);
CREATE INDEX IF NOT EXISTS ix_audits_verdict ON agent_repository_audits(verdict);
CREATE INDEX IF NOT EXISTS ix_audits_time    ON agent_repository_audits(audited_at DESC);

-- Latest-audit-per-repository view. Operational queries use this for
-- "what's the latest verdict on this repo" without scanning the audit
-- history.
DROP VIEW IF EXISTS agent_repository_current_status;
CREATE VIEW agent_repository_current_status AS
SELECT
    r.id                AS repository_id,
    r.full_name,
    r.agent_category,
    r.relevance_status  AS classifier_status,
    a.verdict           AS latest_audit_verdict,
    a.auditor_type      AS latest_auditor_type,
    a.auditor           AS latest_auditor,
    a.audit_batch       AS latest_audit_batch,
    a.reason            AS latest_audit_reason,
    a.audited_at        AS latest_audited_at
FROM agent_repositories r
LEFT JOIN agent_repository_audits a
    ON a.id = (
        SELECT a2.id
        FROM agent_repository_audits a2
        WHERE a2.repository_id = r.id
        ORDER BY a2.audited_at DESC, a2.id DESC
        LIMIT 1
    );