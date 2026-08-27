#!/usr/bin/env python3
"""Pick a deterministic stratified sample of accepted agent_repositories.

Stratification is across star bands: 5000+, 1000-4999, 100-999, 20-99,
0-19. We pick roughly equal counts from each band so the audit doesn't
over-represent the most-starred or least-starred repos.

Output:
    audit/<seed>-sample.json — list of dicts with full_name, stars, and
    GitHub id so a downstream stage can fetch READMEs.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# Bootstrap sys.path so `from compliance.db import …` works whether the script
# is invoked via `python scripts/audit_sample.py` (where sys.path[0] is
# the scripts directory and the `src` package isn't visible) or via
# `python -m`. Mirrors the pattern in src/repo_corpus/__main__.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import select  # noqa: E402

from compliance.db import session_scope  # noqa: E402
from compliance.models import AgentRepository  # noqa: E402


STAR_BANDS: tuple[tuple[str, int, int], ...] = (
    ("5000+",   5000,    10**9),
    ("1000-4999", 1000, 4999),
    ("100-999", 100,    999),
    ("20-99",   20,     99),
    ("0-19",    0,      19),
)


def band_for(stars: int) -> str:
    for name, lo, hi in STAR_BANDS:
        if lo <= stars <= hi:
            return name
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, help="Random seed (used for reproducibility).")
    parser.add_argument("--per-band", type=int, default=20,
                        help="Target number of repos per star band (default 20).")
    parser.add_argument("--status", default="accepted", choices=("accepted", "candidate", "rejected"),
                        help="Which relevance_status to sample from.")
    parser.add_argument("--out", required=True, help="Output JSON file.")
    args = parser.parse_args()

    with session_scope() as session:
        orm_rows = session.execute(
            select(AgentRepository)
            .where(AgentRepository.relevance_status == args.status)
            .order_by(AgentRepository.stars.desc(), AgentRepository.id.asc())
        ).scalars().all()
        # Materialise inside the session — we need r.stars / r.topics_json
        # to remain readable after the session is closed.
        rows = [
            {
                "id":            r.id,
                "github_id":     r.github_id,
                "full_name":     r.full_name,
                "stars":         r.stars,
                "topics_json":   r.topics_json or "[]",
                "description":   r.description or "",
                "agent_category": r.agent_category,
                "relevance_status": r.relevance_status,
            }
            for r in orm_rows
        ]

    print(f"loaded {len(rows)} rows with status={args.status}")
    by_band: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_band[band_for(r["stars"])].append(r)

    rng = random.Random(args.seed)
    sample: list[dict] = []
    for band, _lo, _hi in STAR_BANDS:
        band_rows = by_band.get(band, [])
        n = min(args.per_band, len(band_rows))
        if n == 0:
            print(f"  band {band:11s}: empty")
            continue
        chosen = rng.sample(band_rows, n)
        chosen.sort(key=lambda r: r["stars"], reverse=True)
        sample.extend(
            {
                "github_id":         r["github_id"],
                "full_name":         r["full_name"],
                "stars":             r["stars"],
                "band":              band,
                "relevance_status":  r["relevance_status"],
                "agent_category":    r["agent_category"],
                "topics":            json.loads(r["topics_json"]),
                "description":       r["description"],
            }
            for r in chosen
        )
        print(f"  band {band:11s}: picked {n}/{len(band_rows)}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.seed, "status": args.status, "sample": sample}, indent=2))
    print(f"\nwrote {len(sample)} sample rows → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
