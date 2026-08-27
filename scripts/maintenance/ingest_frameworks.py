"""Ingest all compliance frameworks into the database.

For each framework in FRAMEWORK_CATALOG:
1. Load source file with framework_loader (auto-detects format)
2. Insert/update Framework record
3. Insert/update FrameworkItem records (with ON CONFLICT semantics)

Also ingests EU laws into the existing Law/LawArticle/LawRecital tables
(separate schema; preserves rich structure).

Usage:
    python3 scripts/ingest_frameworks.py
    python3 scripts/ingest_frameworks.py --only soc2 iso27001
    python3 scripts/ingest_frameworks.py --no-laws  # skip EU laws, just frameworks
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from compliance.db import init_db, session_scope  # noqa: E402
from compliance.legal.framework_loader import load_framework, ParsedFramework, FrameworkItem  # noqa: E402
from compliance.legal.framework_catalog import FRAMEWORK_CATALOG  # noqa: E402
from compliance.models import (  # noqa: E402
    Framework, FrameworkItem, FrameworkMapping,
    Law, LawArticle, LawRecital, LawAnnex, ReviewAction,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ingest_frameworks")


def ingest_framework(session, fw: ParsedFramework, catalog_entry: dict, replace: bool = True) -> dict:
    """Insert or update a Framework + its items."""
    framework_id = catalog_entry["id"]

    # Upsert framework
    existing = session.get(Framework, framework_id)
    if existing:
        if replace:
            # Delete old items to replace
            session.query(FrameworkItem).filter(
                FrameworkItem.framework_id == framework_id
            ).delete()
            log.info(f"  Replacing existing framework {framework_id}")
        else:
            log.info(f"  Skipping existing framework {framework_id}")
            return {"framework_id": framework_id, "items_added": 0, "skipped": True}
        fw_record = existing
    else:
        fw_record = Framework(id=framework_id)
        session.add(fw_record)

    # Update framework metadata
    fw_record.category = catalog_entry["category"]
    fw_record.name = catalog_entry["name"]
    fw_record.version = catalog_entry.get("version", "")
    fw_record.issuing_body = catalog_entry.get("issuing_body", "")
    fw_record.tier = catalog_entry.get("tier")
    fw_record.parent_id = catalog_entry.get("parent_id")
    fw_record.source_format = catalog_entry.get("source_format", "")
    fw_record.source_file = catalog_entry.get("source_file", "")
    fw_record.source_url = catalog_entry.get("source_url", "")
    fw_record.license = catalog_entry.get("license", "")
    fw_record.description = catalog_entry.get("description", "")
    fw_record.item_count = fw.count
    fw_record.framework_metadata = json.dumps(fw.metadata)

    # Insert items in bulk
    items_added = 0
    for i, item in enumerate(fw.items):
        # Determine parent_code if hierarchical
        parent_code = None
        if "." in item.code and item.code[0].isalpha():
            parts = item.code.rsplit(".", 1)
            if len(parts) == 2 and parts[1].isdigit():
                parent_code = parts[0]

        fw_item = FrameworkItem(
            framework_id=framework_id,
            code=item.code,
            title=item.title or "",
            content=item.content or "",
            item_type=item.metadata.get("kind", "control"),
            char_count=len(item.content or ""),
            parent_code=parent_code,
            source_path=fw.source_file,
            item_metadata=json.dumps(item.metadata) if item.metadata else None,
        )
        session.add(fw_item)
        items_added += 1

    # Log review action
    session.add(ReviewAction(
        celex=framework_id,
        action="ingested",
        tier=catalog_entry.get("tier"),
        short_name=catalog_entry["name"],
        reason=f"Imported {items_added} items from {fw.source_file}",
        actor="ingest_frameworks",
    ))

    return {"framework_id": framework_id, "items_added": items_added}


def ingest_eu_law(session, fw: ParsedFramework, replace: bool = True) -> dict:
    """Ingest an EU law into the existing Law/LawArticle/LawRecital/LawAnnex tables."""
    # The CELEX is the framework_id for EU laws
    celex = fw.metadata.get("framework_id", "")

    # Get law name from framework
    law = session.get(Law, celex)
    if law is None:
        law = Law(celex=celex)
        session.add(law)
    elif replace:
        # Clear existing children (FK cascade should handle this, but be explicit)
        for model in (LawArticle, LawRecital, LawAnnex):
            session.query(model).filter(model.celex == celex).delete()
        # Flush so the deletes are visible to subsequent queries
        session.flush()

    # Get title from items
    article_count = 0
    recital_count = 0
    annex_count = 0
    law_title = fw.name
    law_short_title = ""

    # Deduplicate within this law's parsed content
    seen_recital_nums = set()
    seen_article_paths = set()
    seen_annex_codes = set()

    for item in fw.items:
        kind = item.metadata.get("kind", "")
        if kind == "article":
            full_path = item.code
            if full_path in seen_article_paths:
                continue
            seen_article_paths.add(full_path)
            session.add(LawArticle(
                celex=celex,
                article_number=item.code.replace("Article ", ""),
                title=item.title or None,
                full_path=item.code,
                text=item.content,
            ))
            article_count += 1
        elif kind == "recital":
            try:
                num = int(item.code.replace("Recital ", ""))
            except (ValueError, AttributeError):
                continue
            if num in seen_recital_nums:
                continue
            # Skip OJ citations (recitals shouldn't be just an OJ reference)
            content = item.content or ""
            if len(content.strip()) < 50:
                continue
            # Skip duplicate recitals that are mostly OJ citations
            if "Official Journal" in content[:100] and len(content) < 200:
                continue
            seen_recital_nums.add(num)
            session.add(LawRecital(
                celex=celex,
                number=num,
                text=content,
            ))
            recital_count += 1
        elif kind == "annex":
            code = item.code.replace("Annex ", "")
            if code in seen_annex_codes:
                continue
            seen_annex_codes.add(code)
            session.add(LawAnnex(
                celex=celex,
                code=code,
                title=item.title or "",
                raw_text=item.content,
            ))
            annex_count += 1

    # Update law metadata
    law.short_name = law_short_title or law_title
    law.long_name = law_title
    law.in_scope = True
    if celex.endswith("P000"):  # Charter - tier 4
        law.tier = 4
    elif celex.startswith("32024") or celex.startswith("32025") or celex.startswith("32026"):
        law.tier = 1 if celex in {"32024R1689", "32024R2847", "32025R2392", "32026R0881", "32025R1535", "32016R0679"} else 2
    else:
        law.tier = 3

    return {
        "celex": celex,
        "articles": article_count,
        "recitals": recital_count,
        "annexes": annex_count,
    }


def run(only: list[str] = None, no_laws: bool = False, replace: bool = True) -> dict:
    """Run ingestion."""
    init_db()
    started = time.time()
    stats = {"laws": [], "frameworks": [], "skipped": []}

    raw_dir = ROOT / "data" / "raw"

    with session_scope() as session:
        for entry in FRAMEWORK_CATALOG:
            if only and entry["id"] not in only:
                continue

            fw_id = entry["id"]
            source_file = raw_dir / entry.get("source_file", "")
            if not source_file.exists():
                log.warning(f"  ✗ {fw_id}: source not found ({source_file})")
                stats["skipped"].append({"id": fw_id, "reason": "source not found"})
                continue

            log.info(f"Loading {fw_id} from {source_file.name}...")
            try:
                fw = load_framework(source_file)
            except Exception as e:
                log.error(f"  ✗ {fw_id}: load failed: {e}")
                stats["skipped"].append({"id": fw_id, "reason": str(e)})
                continue

            # EU laws go into the existing schema; everything else into the new schema
            is_eu_law = entry["category"] == "eu_law"
            if is_eu_law and not no_laws:
                try:
                    result = ingest_eu_law(session, fw, replace=replace)
                    log.info(
                        f"  ✓ {fw_id}: {result['articles']} articles, "
                        f"{result['recitals']} recitals, {result['annexes']} annexes"
                    )
                    stats["laws"].append(result)
                except Exception as e:
                    log.error(f"  ✗ {fw_id}: ingest failed: {e}")
                    stats["skipped"].append({"id": fw_id, "reason": str(e)})
            elif not is_eu_law:
                try:
                    result = ingest_framework(session, fw, entry, replace=replace)
                    log.info(f"  ✓ {fw_id}: {result['items_added']} items")
                    stats["frameworks"].append(result)
                except Exception as e:
                    log.error(f"  ✗ {fw_id}: ingest failed: {e}")
                    stats["skipped"].append({"id": fw_id, "reason": str(e)})

    elapsed = time.time() - started
    log.info(f"\n=== Done in {elapsed:.1f}s ===")
    log.info(f"  EU laws ingested: {len(stats['laws'])}")
    log.info(f"  Frameworks ingested: {len(stats['frameworks'])}")
    log.info(f"  Skipped: {len(stats['skipped'])}")

    return stats


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", nargs="+", help="Ingest only specific framework IDs")
    p.add_argument("--no-laws", action="store_true", help="Skip EU laws, just frameworks")
    p.add_argument("--no-replace", action="store_true", help="Don't replace existing data")
    args = p.parse_args()

    summary = run(only=args.only, no_laws=args.no_laws, replace=not args.no_replace)

    log_file = ROOT / "data" / "ingest_log.json"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(summary, indent=2, default=str))
    log.info(f"Log written to {log_file}")


if __name__ == "__main__":
    main()
