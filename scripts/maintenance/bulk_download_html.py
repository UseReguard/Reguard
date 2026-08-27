"""Bulk download EU law HTML via Web Archive (bypasses EUR-Lex WAF).

EUR-Lex HTML endpoint is WAF-blocked (HTTP 202 + JS challenge).
web.archive.org has snapshots of the same URLs — works without blocking.

For each CELEX, we:
1. Try the latest Wayback snapshot for the EUR-Lex HTML URL
2. If none, try multiple known snapshot dates
3. Save as data/raw/{celex}.html

Usage:
    python3 scripts/bulk_download_html.py
    python3 scripts/bulk_download_html.py --only 32024R1689
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from compliance.legal.catalog import CANONICAL_LAWS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("wayback_download")


RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# Same subset as bulk_download.py — laws relevant to code compliance
CODE_COMPLIANCE_LAWS: list[str] = [
    "32024R1689",  # EU AI Act
    "32016R0679",  # GDPR
    "32024R2847",  # Cyber Resilience Act
    "32025R0454",  # AI Act Scientific Panel Reg
    "32026R1755",  # AI Act Commission Proceedings Reg
    "32026R1744",  # Digital Omnibus on AI
    "32022L2555",  # NIS2
    "32023R2854",  # Data Act
    "32024L2853",  # Product Liability Directive
    "32022R0868",  # Data Governance Act
]


# Wayback Machine pattern: {prefix}/{timestamp}/{original_url}
# Use the prefix to get the raw archived content without Wayback chrome.
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"


def looks_like_real_html(content: bytes) -> bool:
    """Sanity check: does this look like a real EUR-Lex law document?"""
    if len(content) < 100_000:
        return False
    head = content[:5000].decode("utf-8", errors="ignore").lower()
    return (
        "eur-lex" in head
        and ("oj-normal" in head or "oj-ti-art" in head)
        and ("regulation" in head or "directive" in head)
    )


def find_wayback_snapshot(celex: str) -> str | None:
    """Use Wayback CDX API to find the best snapshot URL.

    Returns the timestamp string (e.g. '20240716050300') or None.
    """
    cdx_url = "https://web.archive.org/cdx/search/cdx"
    target = f"eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
    params = {
        "url": target,
        "output": "json",
        "limit": "10",  # check most recent
        "filter": "statuscode:200",
        "from": "20240101",  # after AI Act was published
        "to": "20260831",
    }
    try:
        r = httpx.get(cdx_url, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()
        if len(rows) < 2:
            return None
        # First row is header: ["urlkey", "timestamp", "original", ...]
        # Pick the most recent (rows are already sorted by timestamp desc)
        for row in rows[1:]:
            ts = row[1]
            return ts  # most recent 200 snapshot
    except Exception as e:
        log.warning(f"  CDX lookup failed: {e}")
    return None


def download_via_wayback(celex: str, out_path: Path, max_attempts: int = 3) -> dict:
    """Download EUR-Lex HTML via Wayback Machine."""
    target_url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"

    for attempt in range(1, max_attempts + 1):
        log.info(f"  attempt {attempt}/{max_attempts}: find snapshot")
        ts = find_wayback_snapshot(celex)
        if not ts:
            log.warning(f"  no Wayback snapshot found for {celex}")
            if attempt < max_attempts:
                time.sleep(3)
            continue

        # Use the 'id_' prefix to get raw archived content without Wayback chrome
        url = WAYBACK_RAW.format(ts=ts, url=target_url)
        log.info(f"  GET {url[:120]}...")
        try:
            with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
                if r.status_code == 429:
                    log.warning(f"  Wayback rate-limited (429). Sleeping 30s...")
                    time.sleep(30)
                    continue
                r.raise_for_status()
                sha = hashlib.sha256()
                size = 0
                with open(out_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=64 * 1024):
                        f.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
                sha_hex = sha.hexdigest()

            if not looks_like_real_html(out_path.read_bytes()[:5000]):
                log.warning(f"  downloaded content doesn't look like real law HTML (size={size})")
                if attempt < max_attempts:
                    time.sleep(5)
                continue

            log.info(f"  OK: {out_path.name} ({size:,} bytes, snapshot={ts})")
            return {
                "ok": True,
                "path": str(out_path),
                "bytes": size,
                "snapshot": ts,
                "sha256": sha_hex,
            }
        except httpx.HTTPError as e:
            log.warning(f"  HTTP error: {e}")
            if attempt < max_attempts:
                time.sleep(5)
            continue

    return {
        "ok": False,
        "path": str(out_path),
        "error": "Wayback download failed",
        "attempts": max_attempts,
    }


def bulk_download(celex_list: list[str], delay_between: float = 4.0) -> dict:
    started = time.time()
    results: list[dict] = []

    for i, celex in enumerate(celex_list, 1):
        out_path = RAW_DIR / f"{celex}.html"

        # Skip if cached and looks valid
        if out_path.exists():
            existing_size = out_path.stat().st_size
            try:
                if looks_like_real_html(out_path.read_bytes()[:5000]):
                    log.info(
                        f"[{i}/{len(celex_list)}] {celex} — cached "
                        f"({existing_size:,} bytes), skipping"
                    )
                    results.append({
                        "celex": celex,
                        "ok": True,
                        "cached": True,
                        "bytes": existing_size,
                    })
                    continue
            except Exception:
                pass

        log.info(f"[{i}/{len(celex_list)}] {celex} — downloading via Wayback")
        result = download_via_wayback(celex, out_path)
        result["celex"] = celex
        result["cached"] = False
        results.append(result)

        if i < len(celex_list):
            log.info(f"  sleeping {delay_between}s before next request")
            time.sleep(delay_between)

    elapsed = time.time() - started
    n_ok = sum(1 for r in results if r["ok"])
    n_err = len(results) - n_ok
    total_bytes = sum(r.get("bytes", 0) for r in results)

    return {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "elapsed_seconds": elapsed,
        "total": len(results),
        "ok": n_ok,
        "err": n_err,
        "total_bytes": total_bytes,
        "results": results,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", nargs="+", help="Download only specific CELEX IDs.")
    p.add_argument("--all", action="store_true", help="Download all 28 canonical laws.")
    p.add_argument("--delay", type=float, default=4.0, help="Delay between requests (seconds).")
    p.add_argument("--out-meta", type=Path, default=ROOT / "data" / "wayback_download_log.json")
    args = p.parse_args()

    if args.only:
        celex_list = args.only
    elif args.all:
        celex_list = [e["celex"] for e in CANONICAL_LAWS]
    else:
        celex_list = CODE_COMPLIANCE_LAWS

    log.info(f"Will download {len(celex_list)} laws via Wayback:")
    for c in celex_list:
        entry = next((e for e in CANONICAL_LAWS if e["celex"] == c), None)
        name = entry["short_name"] if entry else "?"
        tier = entry.get("tier") if entry else "?"
        log.info(f"  {c}  T{tier}  {name}")
    log.info("")

    summary = bulk_download(celex_list, delay_between=args.delay)

    args.out_meta.parent.mkdir(parents=True, exist_ok=True)
    args.out_meta.write_text(json.dumps(summary, indent=2))

    log.info("")
    log.info("=" * 60)
    log.info(
        f"DONE: {summary['ok']}/{summary['total']} OK "
        f"in {summary['elapsed_seconds']:.0f}s "
        f"({summary['total_bytes']:,} bytes)"
    )
    if summary["err"] > 0:
        log.warning(f"Failed ({summary['err']}):")
        for r in summary["results"]:
            if not r["ok"]:
                log.warning(f"  {r['celex']}: {r.get('error', '?')}")
    log.info(f"Log written to {args.out_meta}")


if __name__ == "__main__":
    main()
