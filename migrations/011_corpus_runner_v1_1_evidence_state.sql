-- Migration 011: source_cache_entries (deferred but created for v1.1)
--
-- Mirror of cache_meta.json sidecars for SQL-only operator queries.
-- The cache itself is class B; this table is class A (durable).

CREATE TABLE IF NOT EXISTS source_cache_entries (
    id                       INTEGER     PRIMARY KEY AUTOINCREMENT,
    cache_key                TEXT        NOT NULL UNIQUE,
    clone_url                TEXT        NOT NULL,
    cache_path               TEXT        NOT NULL,
    last_fetch_at            DATETIME,
    last_used_at             DATETIME,
    size_bytes               INTEGER     NOT NULL DEFAULT 0,
    state                    TEXT        NOT NULL DEFAULT 'ok',
    error                    TEXT,
    refcount                 INTEGER     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sce_state_size
    ON source_cache_entries (state, size_bytes DESC);
