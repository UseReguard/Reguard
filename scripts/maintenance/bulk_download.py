"""Smart bulk download of EU law content via CELLAR RDF.

EUR-Lex HTML endpoint is WAF-blocked (HTTP 202 + ~2KB challenge page).
Alternative: `publications.europa.eu/resource/celex/{celex}` 303-redirects to
`publications.europa.eu/resource/cellar/{uuid}/rdf/object/full` which returns
the raw law as RDF/XML (~1-60 MB depending on law size).

Why CELLAR RDF beats EUR-Lex HTML:
- Not WAF-blocked (different infrastructure, different rate limiting)
- Structured data (RDF triples, CDM ontology)
- Easy to parse (XML, not mangled HTML)
- Includes metadata, cross-references, dates

Laws to download (subset relevant to code compliance):
- Tier 1: AI Act, GDPR, CRA, AI Act implementing regs
- Tier 2 high-relevance: NIS2, Data Act, Product Liability, Data Governance Act

Usage:
    python3 scripts/bulk_download.py
    python3 scripts/bulk_download.py --only 32024R1689 32016R0679
    python3 scripts/bulk_download.py --all  # all 28 canonical laws
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
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
# Force unbuffered output
for h in logging.getLogger().handlers:
    h.flush = lambda: None
log = logging.getLogger("bulk_download")


# CELLAR endpoint for CELEX → RDF/XML
# publications.europa.eu/resource/celex/{celex} redirects to:
#   publications.europa.eu/resource/cellar/{uuid}/rdf/object/full
CELLAR_CELEX_URL = "https://publications.europa.eu/resource/celex/{celex}"

RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# Laws relevant to code compliance — focused subset, not all 28
CODE_COMPLIANCE_LAWS: list[str] = [
    # Tier 1 — Core (must-have)
    "32024R1689",  # EU AI Act
    "32016R0679",  # GDPR
    "32024R2847",  # Cyber Resilience Act
    "32025R0454",  # AI Act Scientific Panel Reg
    "32026R1755",  # AI Act Commission Proceedings Reg
    "32026R1744",  # Digital Omnibus on AI
    # Tier 2 — High relevance to code
    "32022L2555",  # NIS2
    "32023R2854",  # Data Act
    "32024L2853",  # Product Liability Directive
    "32022R0868",  # Data Governance Act
]


def looks_like_real_rdf(content: bytes) -> bool:
    """Sanity check: does this look like a CELLAR RDF document?"""
    # Use the start of the file for marker checks; do NOT require a minimum
    # size here — that's a separate gate. Files we accept are always >10KB
    # in practice but we shouldn't fail the head check just because the
    # caller passed a sliced buffer.
    head = content[:2000].decode("utf-8", errors="ignore")
    return ("rdf:RDF" in head or "<rdf:" in head) and "publications.europa.eu" in head


def download_one(celex: str, out_path: Path, max_attempts: int = 4) -> dict:
    """Download one CELEX from CELLAR with retry."""
    url = CELLAR_CELEX_URL.format(celex=celex)
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            log.info(f"  attempt {attempt}/{max_attempts}: GET {url}")
            with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
                r.raise_for_status()
                # Stream to disk in chunks to handle large files (GDPR is 60MB)
                sha = hashlib.sha256()
                size = 0
                with open(out_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=64 * 1024):
                        f.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
                sha_hex = sha.hexdigest()

            if not looks_like_real_rdf(out_path.read_bytes()[:5000]):
                log.warning(f"  response doesn't look like RDF (size={size})")
                last_error = "Response not RDF"
                if attempt < max_attempts:
                    time.sleep(5)
                continue

            log.info(f"  OK: {out_path.name} ({size:,} bytes, sha256={sha_hex[:12]}...)")
            return {
                "ok": True,
                "path": str(out_path),
                "bytes": size,
                "attempts": attempt,
                "sha256": sha_hex,
            }

        except httpx.HTTPError as e:
            last_error = str(e)
            log.warning(f"  HTTP error: {e}")
            if attempt < max_attempts:
                time.sleep(5)
            continue

    return {
        "ok": False,
        "path": str(out_path),
        "error": last_error or "Unknown error",
        "attempts": max_attempts,
    }


def bulk_download(celex_list: list[str], delay_between: float = 2.0) -> dict:
    """Download a list of CELEX IDs sequentially with polite delays."""
    started = time.time()
    results: list[dict] = []

    for i, celex in enumerate(celex_list, 1):
        out_path = RAW_DIR / f"{celex}.rdf"

        # Skip if cached and looks valid
        if out_path.exists():
            existing_size = out_path.stat().st_size
            try:
                if looks_like_real_rdf(out_path.read_bytes()[:5000]):
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

        log.info(f"[{i}/{len(celex_list)}] {celex} — downloading")
        result = download_one(celex, out_path)
        result["celex"] = celex
        result["cached"] = False
        results.append(result)

        # Polite delay between requests
        if i < len(celex_list):
            log.info(f"  sleeping {delay_between}s before next request")
            time.sleep(delay_between)

    elapsed = time.time() - started
    n_ok = sum(1 for r in results if r["ok"])
    n_err = len(results) - n_ok
    total_bytes = sum(r.get("bytes", 0) for r in results)

    summary = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "elapsed_seconds": elapsed,
        "total": len(results),
        "ok": n_ok,
        "err": n_err,
        "total_bytes": total_bytes,
        "results": results,
    }
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--only",
        nargs="+",
        help="Download only specific CELEX IDs (space-separated).",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Download all 28 canonical laws.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between successful requests (seconds, default 2.0)",
    )
    p.add_argument(
        "--out-meta",
        type=Path,
        default=ROOT / "data" / "download_log.json",
    )
    args = p.parse_args()

    if args.only:
        celex_list = args.only
    elif args.all:
        celex_list = [e["celex"] for e in CANONICAL_LAWS]
    else:
        celex_list = CODE_COMPLIANCE_LAWS

    log.info(f"Will download {len(celex_list)} laws via CELLAR RDF:")
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
