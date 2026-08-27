-- Migration 001: agent_repositories
--
-- Curated corpus of open-source Python AI-agent GitHub repositories.
-- Stores metadata + URLs only — never repository source code.
--
-- This migration only creates the new table and its indexes. It does not
-- touch any existing table in the database.
--
-- Apply with:
--     python3 scripts/migrate_add_agent_repositories.py

CREATE TABLE IF NOT EXISTS agent_repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- GitHub identity (uniqueness is on GitHub's id; full_name and
    -- html_url are also unique as belt-and-braces against id collisions
    -- in old re-imported data).
    github_id            INTEGER      NOT NULL UNIQUE,
    full_name            VARCHAR(255) NOT NULL UNIQUE,   -- "owner/name"
    owner                VARCHAR(255) NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    html_url             VARCHAR(500) NOT NULL UNIQUE,
    clone_url            VARCHAR(500),

    -- Metadata snapshot from GitHub
    description          TEXT,
    primary_language     VARCHAR(50),
    topics_json          TEXT,                          -- JSON list
    license_spdx         VARCHAR(100),
    stars                INTEGER       NOT NULL DEFAULT 0,
    forks                INTEGER       NOT NULL DEFAULT 0,

    -- GitHub timestamps
    github_created_at    DATETIME,
    github_updated_at    DATETIME,
    github_pushed_at     DATETIME,

    -- Repo status (mirrors GitHub's flags)
    archived             BOOLEAN       NOT NULL DEFAULT 0,
    fork                 BOOLEAN       NOT NULL DEFAULT 0,

    -- Corpus organisation (NOT a compliance classification).
    --   agent_category:   coding_agent | general_agent | agent_framework
    --                     | multi_agent | browser_agent | computer_use_agent
    --                     | workflow_agent | tool_using_agent | other_agent
    --                     | not_agent | unknown
    --   relevance_status: accepted | candidate | rejected | unknown
    agent_category       VARCHAR(30),
    relevance_status     VARCHAR(20)  NOT NULL DEFAULT 'unknown',
    relevance_confidence REAL,
    relevance_reason     TEXT,

    -- Provenance
    discovery_query      VARCHAR(200),
    discovered_at        DATETIME      NOT NULL,
    last_metadata_refresh DATETIME,

    -- Pipeline control: whether the ingest worker is allowed to clone this repo.
    enabled              BOOLEAN       NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_agent_repos_category   ON agent_repositories(agent_category);
CREATE INDEX IF NOT EXISTS ix_agent_repos_status     ON agent_repositories(relevance_status);
CREATE INDEX IF NOT EXISTS ix_agent_repos_stars      ON agent_repositories(stars);
CREATE INDEX IF NOT EXISTS ix_agent_repos_pushed     ON agent_repositories(github_pushed_at);
CREATE INDEX IF NOT EXISTS ix_agent_repos_enabled    ON agent_repositories(enabled);
CREATE INDEX IF NOT EXISTS ix_agent_repos_language   ON agent_repositories(primary_language);
