# Database Schema

The EU AI Compliance database stores EU law metadata + content, optimized
for RAG retrieval.

## Entity Relationship Diagram

```
┌─────────────────┐
│      laws       │  ← master table (one row per CELEX)
│                 │
│ celex (PK)      │
│ slug            │
│ tier (1/2/3/4)  │
│ short_name      │
│ long_name       │
│ document_date   │
│ in_force        │
│ source_url      │
│ raw_html_path   │
│ ...             │
└────────┬────────┘
         │ 1:N
         ├──→ law_recitals     (numbered (1), (2), ... before Article 1)
         ├──→ law_articles     (Article N with full text + sub-paragraph structure)
         ├──→ law_annexes      (ANNEX I, II, III ...)
         └──→ law_chunks       (RAG-ready segments — Article-paragraph level)
```

## Tables

### `laws` (master)
| Column | Type | Notes |
|---|---|---|
| `celex` | VARCHAR(20) PK | e.g. `32024R1689` |
| `slug` | VARCHAR(50) | friendly URL slug |
| `tier` | INTEGER | 1=core, 2=digital, 3=sectoral, 4=foundational |
| `short_name` | VARCHAR(200) | e.g. `EU AI Act` |
| `long_name` | TEXT | full official title |
| `document_date` | DATE | adoption date |
| `in_force` | BOOLEAN | currently binding |
| `work_uri` | VARCHAR(500) | CELLAR URI |
| `source_url` | VARCHAR(500) | EUR-Lex URL |
| `raw_html_path` | VARCHAR(500) | path in data/raw/ |
| `in_scope` | BOOLEAN | we cover it |
| `parent_celex` | VARCHAR(20) | for implementing acts (e.g., Digital Omnibus on AI → AI Act) |
| `added_at` | DATETIME | when added |
| `added_by` | VARCHAR(100) | who added |
| `notes` | TEXT | |

### `law_recitals`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) FK → laws | |
| `number` | INTEGER | 1, 2, 3, ... |
| `text` | TEXT | full text of recital |

UNIQUE(celex, number)

### `law_articles`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) FK → laws | |
| `article_number` | VARCHAR(20) | "5", "50bis" |
| `title` | VARCHAR(500) | e.g., "Subject matter" |
| `full_path` | VARCHAR(200) | e.g., "Article 5(1)(a)(ii)" |
| `text` | TEXT | full text |
| `parent_article_id` | INTEGER FK → law_articles | for nested sub-paragraphs |

UNIQUE(celex, full_path)

### `law_annexes`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) FK → laws | |
| `code` | VARCHAR(10) | "I", "II", "A", "B" |
| `title` | VARCHAR(1000) | |
| `raw_text` | TEXT | full annex content |

UNIQUE(celex, code)

### `law_chunks`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) FK → laws | |
| `idx` | INTEGER | ordering within a law |
| `chunk_kind` | VARCHAR(30) | 'recital', 'article_paragraph', 'annex' |
| `location` | VARCHAR(200) | "Art. 5(1)" or "Recital 3" or "Annex III" |
| `full_text` | TEXT | |
| `char_count` | INTEGER | |
| `embedding_model` | VARCHAR(50) | which embedding model generated this |
| `created_at` | DATETIME | |

UNIQUE(celex, idx)

The `embedding` column (vector(1536) in PostgreSQL) is added via migration. For SQLite, embeddings are computed and stored externally (JSON file).

### `discovery_candidates`
Audit trail of the discovery pipeline (RSS feeds + CELLAR relationships).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) | |
| `source` | VARCHAR(30) | 'RSS_161' / 'RSS_162' / 'RSS_222' / 'CELLAR_REL' / 'MANUAL' |
| `feed_id` | INTEGER | if RSS |
| `parent_celex` | VARCHAR(20) | if from CELLAR relationship |
| `title` | TEXT | |
| `pub_date` | VARCHAR(100) | |
| `creator` | VARCHAR(200) | issuing body |
| `keyword_match` | TEXT | JSON list of matched categories |
| `discovered_at` | DATETIME | |
| `cellar_verified` | BOOLEAN | verified against CELLAR |
| `cellar_title` | TEXT | |
| `cellar_date` | VARCHAR(20) | |
| `cellar_in_force` | VARCHAR(5) | '1', '0', or NULL |
| `llm_in_scope` | BOOLEAN NULL | validator result |
| `llm_tier` | INTEGER NULL | |
| `llm_confidence` | REAL NULL | |
| `llm_reason` | TEXT | |
| `llm_backend` | VARCHAR(50) | 'rules' / 'ollama:gemma3:12b' |
| `status` | VARCHAR(30) | 'pending' / 'auto_added' / 'auto_rejected' / 'ambiguous' / 'rejected' / 'in_canonical' |
| `reviewed_at` | DATETIME | |
| `review_note` | TEXT | |

UNIQUE(celex, source)

### `agent_repositories`
Curated corpus of open-source Python AI-agent GitHub repositories. Stores
metadata + URLs only — never repository source code. The compliance scanner
worker is expected to clone `enabled = 1` rows one at a time, run analysis,
store the result, then delete the temporary clone.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `github_id` | INTEGER UNIQUE | GitHub's internal repo id |
| `full_name` | VARCHAR(255) UNIQUE | `owner/name` |
| `owner` | VARCHAR(255) | owner login |
| `name` | VARCHAR(255) | repo name |
| `html_url` | VARCHAR(500) UNIQUE | canonical web URL |
| `clone_url` | VARCHAR(500) | git clone URL |
| `description` | TEXT | |
| `primary_language` | VARCHAR(50) | must be `Python` for accepted rows |
| `topics_json` | TEXT | JSON list of GitHub topics |
| `license_spdx` | VARCHAR(100) | e.g. `MIT`, `Apache-2.0` |
| `stars` | INTEGER | snapshot of stargazers_count |
| `forks` | INTEGER | snapshot of forks_count |
| `github_created_at` | DATETIME | |
| `github_updated_at` | DATETIME | |
| `github_pushed_at` | DATETIME | |
| `archived` | BOOLEAN | mirrors GitHub's flag |
| `fork` | BOOLEAN | mirrors GitHub's flag |
| `agent_category` | VARCHAR(30) | `coding_agent` / `general_agent` / `agent_framework` / `multi_agent` / `browser_agent` / `computer_use_agent` / `workflow_agent` / `tool_using_agent` / `other_agent` / `not_agent` / `unknown` |
| `relevance_status` | VARCHAR(20) | `accepted` / `candidate` / `rejected` / `unknown` |
| `relevance_confidence` | REAL | 0.0–1.0 |
| `relevance_reason` | TEXT | human-readable classifier reasoning |
| `discovery_query` | VARCHAR(200) | first GitHub search that surfaced this repo |
| `discovered_at` | DATETIME | |
| `last_metadata_refresh` | DATETIME | updated by `python -m repo_corpus refresh` |
| `reclassified_at` | DATETIME | updated by `python -m repo_corpus reclassify` |
| `enabled` | BOOLEAN | whether the scanner worker is allowed to clone this repo |

Indexes: `ix_agent_repos_category`, `ix_agent_repos_status`,
`ix_agent_repos_stars`, `ix_agent_repos_pushed`, `ix_agent_repos_enabled`,
`ix_agent_repos_language`.

Populated by `python -m repo_corpus discover` (see `src/repo_corpus/`).
See `migrations/001_agent_repositories.sql` for the canonical DDL.

### `review_actions`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `celex` | VARCHAR(20) | |
| `action` | VARCHAR(30) | 'accept' / 'reject' / 'ingested' |
| `tier` | INTEGER | |
| `short_name` | VARCHAR(200) | |
| `reason` | TEXT | |
| `actor` | VARCHAR(100) | 'import_pipeline' / 'manual:username' |
| `timestamp` | DATETIME | |

## Indexes

All tables have primary key indexes. Foreign keys are auto-indexed by SQLAlchemy.

Additional indexes:
- `law_chunks`: ix on (celex, chunk_kind) — for fast kind-based filtering
- `discovery_candidates`: ix on status — for fast pending review queries
- `laws`: ix on tier, slug

## Migration to PostgreSQL

When you have access to a real PostgreSQL:

```bash
# 1. Install pgvector
apt install postgresql-18-pgvector

# 2. Set DATABASE_URL
export DATABASE_URL=postgresql://user:pass@host/eu_ai_compliance

# 3. Create database and user (in PostgreSQL)
createdb eu_ai_compliance

# 4. Run schema (creates tables in PostgreSQL)
python3 -c "from src.db import init_db; init_db()"

# 5. Migrate data (re-import from EUR-Lex or copy data dir)
./scripts/import_all_laws.sh

# 6. Add vector column + migrate embeddings
psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
python3 src/cli.py add-vector-column
python3 src/cli.py embed-and-store  # populate embeddings
```

The schema is identical between SQLite and PostgreSQL except:
- `embedding` column is added via migration on PostgreSQL
- `tsvector` columns for full-text search are added on PostgreSQL
- Trigram (`pg_trgm`) indexes added on PostgreSQL for fuzzy text search