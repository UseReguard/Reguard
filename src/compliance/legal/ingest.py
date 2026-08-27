"""Main ingestion pipeline.

Downloads EUR-Lex HTML for each canonical law, parses it, chunks it,
and stores in the database.

Usage:
    from compliance.legal.ingest import ingest_all, ingest_one
    ingest_all()
    ingest_one("32024R1689")
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from compliance.legal.catalog import CANONICAL_LAWS, by_celex
from compliance.legal.chunker import chunk_law
from compliance.config import EUR_LEX_HTML, RAW_DIR, CHUNKS_DIR
from compliance.db import session_scope, init_db
from compliance.models import Law, LawArticle, LawAnnex, LawChunk, LawRecital, ReviewAction
from compliance.legal.parser import parse_law

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def download_html(celex: str, force: bool = False) -> Path:
    """Download EUR-Lex HTML to data/raw/{celex}.html. Returns the path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{celex}.html"

    if out_path.exists() and not force:
        log.debug(f"  cached: {out_path}")
        return out_path

    url = EUR_LEX_HTML.format(celex=celex)
    log.info(f"  downloading {celex} from EUR-Lex...")
    r = httpx.get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    out_path.write_bytes(r.content)
    log.info(f"  saved: {out_path} ({len(r.content):,} bytes)")
    return out_path


def ingest_one(celex: str, force_download: bool = False) -> dict:
    """Ingest one law: download, parse, chunk, store."""
    catalog_entry = by_celex(celex)
    if not catalog_entry:
        raise ValueError(f"CELEX {celex} not in canonical catalog")

    log.info(f"\n=== Ingesting {celex} ({catalog_entry['short_name']}) ===")

    # 1. Download
    raw_path = download_html(celex, force=force_download)
    html = raw_path.read_text(encoding="utf-8")

    # 2. Parse
    parsed = parse_law(html)
    log.info(f"  parsed: {len(parsed.recitals)} recitals, {len(parsed.articles)} articles, {len(parsed.annexes)} annexes")

    # 3. Chunk
    chunks = chunk_law(parsed)
    log.info(f"  chunked: {len(chunks)} (recital={sum(1 for c in chunks if c.chunk_kind=='recital')}, article={sum(1 for c in chunks if c.chunk_kind=='article_paragraph')}, annex={sum(1 for c in chunks if c.chunk_kind=='annex')})")

    # 4. Save chunks as JSONL for debug
    chunks_jsonl_path = CHUNKS_DIR / f"{celex}.jsonl"
    chunks_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_jsonl_path, "w") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict()) + "\n")

    # 5. Store in DB
    with session_scope() as session:
        # Upsert law metadata
        law = session.get(Law, celex)
        if law is None:
            law = Law(celex=celex)
            session.add(law)
        law.slug = catalog_entry.get("slug")
        law.tier = catalog_entry.get("tier")
        law.short_name = catalog_entry["short_name"]
        law.long_name = catalog_entry["long_name"]
        law.in_scope = True
        law.source_url = EUR_LEX_HTML.format(celex=celex)
        law.raw_html_path = str(raw_path.relative_to(raw_path.parent.parent))
        law.parent_celex = catalog_entry.get("parent_celex")
        # Flush to populate relationships
        session.flush()

        # Replace articles, recitals, annexes, chunks
        session.query(LawArticle).filter(LawArticle.celex == celex).delete()
        session.query(LawRecital).filter(LawRecital.celex == celex).delete()
        session.query(LawAnnex).filter(LawAnnex.celex == celex).delete()
        session.query(LawChunk).filter(LawChunk.celex == celex).delete()

        # Insert recitals
        for r in parsed.recitals:
            if not r.text.strip():
                continue
            session.add(LawRecital(
                celex=celex, number=r.number, text=r.text.strip()
            ))

        # Insert articles (only the parent Article-level; sub-paragraphs go into chunks)
        for a in parsed.articles:
            if not a.text.strip():
                continue
            session.add(LawArticle(
                celex=celex,
                article_number=a.article_number,
                title=a.title,
                full_path=a.full_path,
                text=a.text.strip(),
            ))

        # Insert annexes
        for ax in parsed.annexes:
            session.add(LawAnnex(
                celex=celex, code=ax.code, title=ax.title, raw_text=ax.raw_text or ""
            ))

        # Insert chunks
        for c in chunks:
            session.add(LawChunk(
                celex=celex,
                idx=c.idx,
                chunk_kind=c.chunk_kind,
                location=c.location,
                full_text=c.full_text,
                char_count=c.char_count,
            ))

        # Log action
        session.add(ReviewAction(
            celex=celex,
            action="ingested",
            tier=catalog_entry.get("tier"),
            short_name=catalog_entry["short_name"],
            reason=f"Imported {len(chunks)} chunks from EUR-Lex XHTML",
            actor="import_pipeline",
        ))

    log.info(f"  stored: 1 law, {len(parsed.recitals)} recitals, "
             f"{len(parsed.articles)} articles, {len(parsed.annexes)} annexes, "
             f"{len(chunks)} chunks")
    return {
        "celex": celex,
        "recitals": len(parsed.recitals),
        "articles": len(parsed.articles),
        "annexes": len(parsed.annexes),
        "chunks": len(chunks),
    }


def ingest_all(force_download: bool = False, skip: list[str] | None = None) -> dict:
    """Ingest all canonical laws. Returns aggregate stats."""
    skip = skip or []
    init_db()
    started = time.time()
    stats: list[dict] = []
    for entry in CANONICAL_LAWS:
        celex = entry["celex"]
        if celex in skip:
            log.info(f"Skipping {celex}")
            continue
        try:
            stat = ingest_one(celex, force_download=force_download)
            stats.append(stat)
        except Exception as e:
            log.error(f"  ! error ingesting {celex}: {e}")
            stats.append({"celex": celex, "error": str(e)})

    elapsed = time.time() - started
    n_ok = sum(1 for s in stats if "error" not in s)
    n_err = len(stats) - n_ok
    total_chunks = sum(s.get("chunks", 0) for s in stats)

    log.info(f"\n=== Done. {n_ok}/{len(stats)} laws ingested in {elapsed:.1f}s. ===")
    log.info(f"    {total_chunks} total chunks stored.")

    return {
        "total": len(stats),
        "ok": n_ok,
        "errors": n_err,
        "total_chunks": total_chunks,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        ingest_all()
    elif len(sys.argv) > 1:
        ingest_one(sys.argv[1])
    else:
        print("Usage: python3 -m src.ingest all [force]")
        print("       python3 -m src.ingest <celex>")