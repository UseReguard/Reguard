"""Process manually-downloaded EUR-Lex HTML files.

Moves files from a source directory to data/raw/{celex}.html, renames them,
and verifies the parser can extract articles + recitals.

Usage:
    python3 scripts/process_manual_downloads.py <source_directory>
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("process_downloads")

RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def extract_celex(html_path: Path) -> str | None:
    """Extract CELEX number from HTML content (CELEX:XXXXXXXXXX format)."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"CELEX:([0-9A-Z]{10})", content)
        if m:
            return m.group(1)
    except Exception as e:
        log.warning(f"  Could not read {html_path}: {e}")
    return None


def process_files(source_dir: Path) -> dict:
    """Move HTML files to data/raw/{celex}.html, parse each."""
    results = []
    html_files = sorted(source_dir.glob("*.html"))
    log.info(f"Found {len(html_files)} HTML files in {source_dir}")

    for src in html_files:
        celex = extract_celex(src)
        if not celex:
            log.warning(f"  SKIP (no CELEX): {src.name}")
            results.append({"src": src.name, "celex": None, "ok": False, "error": "no CELEX"})
            continue

        dst = RAW_DIR / f"{celex}.html"
        if dst.exists():
            log.info(f"  EXISTS, overwriting: {dst.name}")
        shutil.copy2(src, dst)

        # Parse to verify
        try:
            sys.path.insert(0, str(ROOT))
            from compliance.legal.parser import parse_law  # type: ignore

            parsed = parse_law(dst.read_text(encoding="utf-8"))
            n_articles = len(parsed.articles)
            n_recitals = len(parsed.recitals)
            n_annexes = len(parsed.annexes)
            ok = n_articles > 0 or n_recitals > 0
            status = "OK" if ok else "EMPTY"
            log.info(
                f"  {status} {celex}: {n_articles} articles, "
                f"{n_recitals} recitals, {n_annexes} annexes"
            )
            results.append({
                "src": src.name,
                "celex": celex,
                "ok": ok,
                "articles": n_articles,
                "recitals": n_recitals,
                "annexes": n_annexes,
            })
        except Exception as e:
            log.warning(f"  PARSE ERROR {celex}: {e}")
            results.append({"src": src.name, "celex": celex, "ok": False, "error": str(e)})

    return {
        "source_dir": str(source_dir),
        "total": len(html_files),
        "results": results,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path, help="Directory with EUR-Lex HTML files")
    p.add_argument(
        "--out-meta",
        type=Path,
        default=ROOT / "data" / "manual_download_log.json",
    )
    args = p.parse_args()

    if not args.source.exists():
        log.error(f"Source directory does not exist: {args.source}")
        sys.exit(1)

    summary = process_files(args.source)

    args.out_meta.parent.mkdir(parents=True, exist_ok=True)
    args.out_meta.write_text(json.dumps(summary, indent=2))

    n_ok = sum(1 for r in summary["results"] if r["ok"])
    n_skip = sum(1 for r in summary["results"] if not r.get("celex"))
    n_err = sum(1 for r in summary["results"] if r.get("celex") and not r["ok"])
    log.info("")
    log.info("=" * 60)
    log.info(f"DONE: {n_ok} parsed OK, {n_err} errors, {n_skip} skipped (no CELEX)")
    log.info(f"Log: {args.out_meta}")


if __name__ == "__main__":
    main()
