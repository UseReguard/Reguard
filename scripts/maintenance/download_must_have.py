"""Download the 4 must-have EU law HTML files via Wayback Machine.

The 3 laws every AI software repo needs to comply with:
- AI Act (32024R1689) — already have HTML, skip
- CRA (32024R2847)
- GDPR (32016R0679)

Plus 2 strongly recommended for most B2B SaaS:
- NIS2 (32022L2555)
- Product Liability Directive (32024L2853)

EUR-Lex direct is WAF-blocked, so we use web.archive.org.
Wayback rate-limits aggressively — we send ONE request per law with delays.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("must_have_download")

RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# The 4 we need (AI Act already downloaded)
MUST_HAVE: list[tuple[str, str]] = [
    ("32024R2847", "CRA"),
    ("32016R0679", "GDPR"),
    ("32022L2555", "NIS2"),
    ("32024L2853", "Product Liability Directive"),
]


def find_snapshot(celex: str) -> str | None:
    """Find most recent Wayback snapshot for this EUR-Lex URL."""
    cdx_url = "https://web.archive.org/cdx/search/cdx"
    target = f"eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
    params = {
        "url": target,
        "output": "json",
        "limit": "5",
        "filter": "statuscode:200",
        "from": "20240101",
    }
    try:
        r = httpx.get(cdx_url, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()
        if len(rows) < 2:
            return None
        return rows[1][1]  # most recent 200 snapshot timestamp
    except Exception as e:
        log.warning(f"  CDX failed for {celex}: {e}")
    return None


def looks_like_law(content: bytes) -> bool:
    """Quick sanity check."""
    if len(content) < 100_000:
        return False
    head = content[:5000].decode("utf-8", errors="ignore").lower()
    return (
        ("eur-lex" in head or "regulation" in head or "directive" in head)
        and ("oj-normal" in head or "oj-ti-art" in head)
    )


def download_one(celex: str, name: str) -> dict:
    """Download one law HTML. ONE request only."""
    out_path = RAW_DIR / f"{celex}.html"

    if out_path.exists() and looks_like_law(out_path.read_bytes()[:5000]):
        size = out_path.stat().st_size
        log.info(f"{celex} ({name}): already cached ({size:,} bytes)")
        return {"celex": celex, "name": name, "ok": True, "cached": True, "bytes": size}

    log.info(f"{celex} ({name}): finding Wayback snapshot...")
    ts = find_snapshot(celex)
    if not ts:
        log.warning(f"  no snapshot found")
        return {"celex": celex, "name": name, "ok": False, "error": "no snapshot"}

    target_url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
    archive_url = f"https://web.archive.org/web/{ts}id_/{target_url}"
    log.info(f"  snapshot: {ts}")
    log.info(f"  GET (one request)...")

    try:
        # ONE request. No retries. No streaming. Direct.
        r = httpx.get(archive_url, timeout=180, follow_redirects=True)
        r.raise_for_status()
        content = r.content
        out_path.write_bytes(content)
        log.info(f"  OK: {len(content):,} bytes written to {out_path.name}")
        return {
            "celex": celex,
            "name": name,
            "ok": True,
            "cached": False,
            "bytes": len(content),
            "snapshot": ts,
        }
    except Exception as e:
        log.warning(f"  FAILED: {e}")
        return {"celex": celex, "name": name, "ok": False, "error": str(e)}


def main():
    log.info("=" * 60)
    log.info("Downloading must-have EU laws (one request per law)")
    log.info("=" * 60)
    log.info("")

    results = []
    for celex, name in MUST_HAVE:
        log.info(f"[{MUST_HAVE.index((celex, name))+1}/{len(MUST_HAVE)}] {celex} — {name}")
        result = download_one(celex, name)
        results.append(result)
        log.info("")
        # Be polite: 6 second delay between Wayback requests
        if (celex, name) != MUST_HAVE[-1]:
            log.info("  waiting 6s...")
            time.sleep(6)

    # Summary
    log.info("=" * 60)
    n_ok = sum(1 for r in results if r["ok"])
    total = sum(r.get("bytes", 0) for r in results)
    log.info(f"DONE: {n_ok}/{len(results)} OK ({total:,} bytes)")
    for r in results:
        status = "✓" if r["ok"] else "✗"
        info = f"{r.get('bytes', 0):,} bytes" if r["ok"] else r.get("error", "?")
        log.info(f"  {status} {r['celex']} ({r['name']}): {info}")

    log_file = ROOT / "data" / "must_have_download.json"
    log_file.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
