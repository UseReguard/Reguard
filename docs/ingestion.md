# Ingestion Pipeline

End-to-end: EUR-Lex XHTML → structured data → SQLite chunks.

## Flow

```
                    ┌──────────────────────────────────────────────┐
                    │ EUR-Lex CELLAR (public SPARQL endpoint)       │
                    └──────────────────────────────────────────────┘
                                      │
                                      │ get CELEX list + metadata
                                      ▼
                    ┌──────────────────────────────────────────────┐
                    │ catalog.py — 28 canonical laws (verified 2026-08-21) │
                    └──────────────────────────────────────────────┘
                                      │
                                      │ for each celex:
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  download_html(celex) → data/raw/{celex}.html                          │
   │  (EUR-Lex legal-content/EN/TXT/HTML/?uri=CELEX:{celex})                │
   └──────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  parser.py — parse_law(html) → ParsedLaw                              │
   │  Extracts: title, recitals, articles (with sub-paragraphs), annexes │
   └──────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  chunker.py — chunk_law(parsed) → list[Chunk]                         │
   │  Article-paragraph level granularity                                  │
   └──────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  data/chunks/{celex}.jsonl (debug output)                              │
   └──────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  SQLAlchemy ORM → SQLite database                                     │
   │  Tables: laws, law_articles, law_recitals, law_annexes, law_chunks    │
   └──────────────────────────────────────────────────────────────────────┘
```

## Running the pipeline

### One-time setup

```bash
./scripts/init_db.sh
```

### Import all 28 laws

```bash
./scripts/import_all_laws.sh
```

Takes ~2 minutes (28 laws × ~5s each for HTTP + parsing).

### Import one law (for testing)

```bash
python3 -c "from src.ingest import ingest_one; ingest_one('32024R1689')"
```

### Verify

```bash
python3 scripts/verify_import.py
```

## Known limitations

### EUR-Lex WAF / rate limiting

The document download endpoint (`eur-lex.europa.eu/legal-content/EN/TXT/HTML/`)
implements AWS WAF. After ~5-10 requests per session, subsequent calls return
HTTP 202 with a 2KB challenge page instead of the document.

**Workaround:** Wait 5-15 minutes for the WAF ban to expire, then re-run.
RSS feeds (`/EN/display-feed.rss?rssId=...`) are NOT rate-limited and work fine.

### Parser limitations

The current parser handles straightforward EU acts (AI Act, GDPR, CRA, etc.).
Edge cases that may need adjustment:

- Acts with extensive TOC at the start (parser may capture TOC as recitals)
- Acts where Article numbers contain letters (e.g., "Article 5bis")
- Acts with multiple levels of sub-paragraphs nested deep (4+ levels)
- Acts where annex titles are split across multiple HTML elements

Each law is parsed and stored — even with imperfect parsing, the chunks are
preserved and can be re-processed if the parser is improved.

## Storage footprint

Per law (estimates):
- Raw HTML: 0.5 - 1.5 MB (AI Act is the outlier at 1.26 MB)
- Plain text after strip: ~50% of HTML size
- Chunks (JSONL): ~150 KB
- DB row size: ~10-20 KB per row × ~300 chunks = 3-6 MB

Total for 28 laws:
- Raw HTML: ~30 MB
- Chunks JSONL: ~4 MB
- SQLite DB: ~10-20 MB

Easy to fit in any environment.

## What gets stored in each table per law

```
laws:           1 row
law_recitals:   ~80-180 rows (numbered (1) through (N))
law_articles:   ~30-110 rows (one per Article with full text)
law_annexes:    ~1-15 rows (one per Annex)
law_chunks:     ~150-400 rows (RAG-ready segments)
```

For AI Act specifically:
- 1 law row
- 180 recitals
- 113 articles (Articles 1-113, plus a few cross-references)
- 13 annexes
- ~400 chunks

## Future enhancements

1. **Embeddings**: Add `vector(1536)` column on PostgreSQL + embedding generation
2. **Full-text search**: Add `tsvector` columns + GIN index for keyword search
3. **Cross-references**: Extract "Article X references Article Y" relationships
4. **Multilingual**: Currently EN-only. Add other 23 EU languages
5. **Versioning**: When an act is amended, keep old + new versions with supersedes link