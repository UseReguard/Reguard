# compliance-tool

EU AI compliance assessment — law corpus + GitHub repository scanning pipeline.

## Overview

- **Law corpus** (legal domain): EUR-Lex XHTML → structured law + chunked text
- **Repository corpus** (corpus domain): curated Python AI-agent GitHub repos
- **Compliance pipeline** (pipeline domain): clone → SHA → runtime → deterministic result
- **Adapters** (adapters domain): per-repo adapters (mini-swe-agent, nanobot, …)
- **Requirements** (requirements domain): AI Act Article 12(1) and future articles
- **Storage**: SQLite (`data/eu_ai_compliance.db`) — PostgreSQL-compatible via SQLAlchemy

## Folder layout

```
compliance-tool/
├── pyproject.toml                  # project metadata + dependencies
├── pytest.ini                      # pytest config
├── conftest.py                     # adds src/ to sys.path for tests
├── README.md
├── .github/workflows/
├── src/
│   └── compliance/
│       ├── __init__.py
│       ├── config.py               # env vars, DB URL
│       ├── db.py                   # SQLAlchemy engine + session
│       ├── models.py               # ORM models (laws, chunks, agent_repositories, …)
│       ├── legal/                  # laws, parsing, ingestion
│       │   ├── catalog.py          # the 28 canonical EU laws (source of truth)
│       │   ├── framework_catalog.py
│       │   ├── parser.py           # EUR-Lex XHTML → structured data
│       │   ├── chunker.py          # chunk structured data for RAG
│       │   ├── framework_loader.py # multi-format framework loader
│       │   └── ingest.py           # main ingestion pipeline
│       ├── corpus/                 # GitHub repo discovery + gold sets
│       │   ├── __main__.py         # CLI: `python -m compliance.corpus …`
│       │   ├── github_client.py
│       │   ├── classifier.py       # relevance + agent_category heuristic
│       │   ├── pipeline.py         # discover / refresh / list / reclassify
│       │   ├── queries.py
│       │   └── stats.py
│       ├── requirements/           # AI_ACT_12_1, AI_ACT_14_4_e, …
│       │   ├── legal_text_parser.py # EU article text → atomic obligations
│       │   └── article_classifier.py # runtime-testability heuristic
│       ├── pipeline/               # clone → SHA → runtime → result (stub)
│       └── adapters/               # mini-swe-agent, nanobot, … (stub)
├── runtime/                        # frozen generic Docker execution runtime
│   ├── Dockerfile
│   ├── detect.py
│   ├── entrypoint.py
│   └── commands/
├── data/
│   ├── eu_ai_compliance.db         # SQLite database
│   ├── raw/                        # downloaded XHTML files
│   └── chunks/                     # generated chunks (JSONL, debug)
├── migrations/                     # schema migrations (numbered .sql)
├── scripts/                        # thin entrypoints only
│   └── run_repo_corpus.sh
├── scripts/maintenance/            # all maintenance scripts (audits, migrations, ingest, sync)
├── tests/
│   ├── legal/                      # ingest pipeline tests
│   ├── corpus/                     # (empty for now)
│   ├── pipeline/                   # (empty for now)
│   ├── requirements/               # legal text parser tests
│   └── runtime/                    # runtime unit tests + fixtures
├── audit/                          # current audit artifacts (old ones archived)
└── docs/
```

## Quick start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Initialize the database
./scripts/maintenance/init_db.sh

# 3. Import all 28 canonical laws
./scripts/maintenance/import_all_laws.sh

# 4. Verify
python3 scripts/maintenance/verify_import.py

# 5. Run the corpus CLI
./scripts/run_repo_corpus.sh stats
```

## Pipeline flow

```
LEGAL SOURCES  →  requirements/   AI Act → atomic obligations
CORPUS         →  adapters/       per-repo agent drivers
RUNTIME        →  (Docker)        frozen execution sandbox
PIPELINE       →  clone → SHA → runtime → deterministic result
```

Each row in `agent_repositories` (corpus) maps to one or more AI Act
requirements (requirements), which are evaluated by a per-repo adapter
inside the runtime.

## Database schema (high level)

```
laws (master table)
  ↓ 1:N
law_articles (Articles × sub-paragraphs)
law_recitals
law_annexes

laws → law_chunks (1:N, for RAG)
laws → law_candidates (1:N, from discovery pipeline)

agent_repositories (curated GitHub corpus)
  ↓ 1:N
agent_repository_audits (human + LLM judgments)

article_runtime_assessments (Article 12(1) etc.)
```

## Migration to PostgreSQL

The schema is PostgreSQL-compatible. When ready:

1. `pip install -e ".[pgvector]"`
2. Set `DATABASE_URL=postgresql://user:pass@host/db`
3. Re-run `scripts/maintenance/init_db.sh` — SQLAlchemy handles the rest
4. Install pgvector: `apt install postgresql-18-pgvector`

## License

Internal project. Source code: AGPL-3.0 (or proprietary — TBD).