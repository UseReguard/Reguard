-- PostgreSQL schema for EU AI repos corpus
-- Used to test our compliance scanner rules against real codebases

CREATE TABLE IF NOT EXISTS eu_ai_repos (
    id SERIAL PRIMARY KEY,
    github_id BIGINT UNIQUE,             -- GitHub's internal repo ID
    full_name TEXT NOT NULL UNIQUE,      -- 'owner/repo'
    owner_login TEXT NOT NULL,
    owner_location TEXT,                 -- owner's profile location (free text)
    owner_country TEXT,                  -- normalized EU country code (FR, DE, etc.) or NULL
    name TEXT NOT NULL,
    description TEXT,
    primary_language TEXT,
    languages JSONB,                     -- all languages with byte counts
    topics JSONB,                        -- GitHub topics
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    size_kb INTEGER,                     -- repo size in KB
    is_ai_product BOOLEAN DEFAULT FALSE, -- verified AI nature
    app_category TEXT,                   -- 'fullstack', 'backend', 'ai_product', 'ml_framework', 'data'
    created_at TIMESTAMP,
    pushed_at TIMESTAMP,
    default_branch TEXT,
    html_url TEXT,
    clone_url TEXT,
    verified_at TIMESTAMP DEFAULT NOW(),
    verification_notes TEXT,             -- how we confirmed EU + AI
    collection_method TEXT               -- 'github_search', 'curated_list', 'awesome_*'
);

CREATE INDEX IF NOT EXISTS ix_repos_stars ON eu_ai_repos(stars DESC);
CREATE INDEX IF NOT EXISTS ix_repos_category ON eu_ai_repos(app_category);
CREATE INDEX IF NOT EXISTS ix_repos_country ON eu_ai_repos(owner_country);
CREATE INDEX IF NOT EXISTS ix_repos_ai ON eu_ai_repos(is_ai_product);
CREATE INDEX IF NOT EXISTS ix_repos_language ON eu_ai_repos(primary_language);
