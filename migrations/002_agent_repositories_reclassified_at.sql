-- Migration 002: add reclassified_at to agent_repositories
--
-- Stamps the last time a row's relevance_status / agent_category /
-- relevance_reason were (re)computed by the reclassify command.
-- Distinct from last_metadata_refresh (which tracks the GitHub
-- metadata refresh).
--
-- Apply with:
--     python3 scripts/migrate_add_reclassified_at.py

ALTER TABLE agent_repositories ADD COLUMN reclassified_at DATETIME;
CREATE INDEX IF NOT EXISTS ix_agent_repos_reclassified ON agent_repositories(reclassified_at);
