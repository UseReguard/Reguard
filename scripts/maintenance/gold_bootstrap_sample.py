#!/usr/bin/env python3
"""Build a stratified gold-bootstrap sample for the agent_repositories
corpus.

Per the user's specification (2026-08-28):
  - Stratify by category × star band
  - Oversample the troubled categories (tool_using_agent, multi_agent,
    general_agent, coding_agent)
  - High-precision categories need fewer examples
  - ~150 candidates total; nothing becomes gold until human confirms

Output:
    audit/2026-08-28-gold-bootstrap-sample.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import select

from compliance.db import session_scope
from compliance.models import AgentRepository


# Per-category sample targets (troubled categories get more).
CATEGORY_TARGETS: dict[str, int] = {
    "coding_agent":          30,   # user-listed priority
    "multi_agent":           25,
    "general_agent":         20,
    "tool_using_agent":      20,
    "workflow_agent":        15,
    "agent_framework":       12,
    "computer_use_agent":    10,
    "browser_agent":          7,
    "other_agent":           11,
}

STAR_BANDS: tuple[tuple[str, int, int], ...] = (
    ("5000+",     5000,  10**9),
    ("1000-4999", 1000,  4999),
    ("100-999",    100,   999),
    ("20-99",       20,    99),
    ("0-19",         0,    19),
)


def _band_for(stars: int) -> str:
    for name, lo, hi in STAR_BANDS:
        if lo <= stars <= hi:
            return name
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True)
    parser.add_argument("--out",  required=True)
    parser.add_argument("--status", default="accepted")
    args = parser.parse_args()

    with session_scope() as session:
        rows = session.execute(
            select(AgentRepository)
            .where(AgentRepository.relevance_status == args.status)
        ).scalars().all()
        snapshots = [
            {
                "id":              r.id,
                "full_name":       r.full_name,
                "stars":           r.stars,
                "agent_category":  r.agent_category,
                "topics_json":     r.topics_json or "[]",
                "description":     r.description or "",
            }
            for r in rows
        ]

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for s in snapshots:
        by_cat[s["agent_category"] or "unknown"].append(s)

    rng = random.Random(args.seed)

    # First pass: even star-band spread within each category.
    sample: list[dict] = []
    print(f"loaded {len(snapshots)} accepted rows; targets:")
    for cat, target in CATEGORY_TARGETS.items():
        bucket = by_cat.get(cat, [])
        if not bucket:
            print(f"  {cat:22s}: empty in corpus")
            continue
        n = min(target, len(bucket))
        # Split by star band.
        per_band: dict[str, list[dict]] = defaultdict(list)
        for r in bucket:
            per_band[_band_for(r["stars"])].append(r)
        # Take ~equally from each band, then fill remainder from largest.
        chosen: list[dict] = []
        bands_present = [(b, rs) for b, rs in per_band.items() if rs]
        # Even spread: try to give every band >=1 if it has rows.
        for band, rows_in_band in bands_present:
            if n >= len(chosen) + (len(bands_present) - len(chosen)) and rows_in_band:
                k = max(1, n // len(bands_present))
                k = min(k, len(rows_in_band))
                chosen.extend(rng.sample(rows_in_band, k))
        # Trim or fill to exactly n.
        if len(chosen) > n:
            chosen = rng.sample(chosen, n)
        else:
            remaining_pool = [r for r in bucket if r not in chosen]
            need = n - len(chosen)
            if remaining_pool and need > 0:
                chosen.extend(rng.sample(remaining_pool, min(need, len(remaining_pool))))
        chosen.sort(key=lambda r: r["stars"], reverse=True)
        sample.extend(chosen)
        print(f"  {cat:22s}: picked {len(chosen):3d}/{len(bucket):3d} (target {target})")

    # Materialise to JSON-friendly dicts.
    out_rows = [
        {
            "github_id":       r["id"],
            "full_name":       r["full_name"],
            "stars":           r["stars"],
            "band":            _band_for(r["stars"]),
            "agent_category":  r["agent_category"],
            "topics":          json.loads(r["topics_json"]),
            "description":     r["description"],
        }
        for r in sample
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "seed": args.seed,
        "status": args.status,
        "sample": out_rows,
    }, indent=2))
    print(f"\nwrote {len(out_rows)} rows → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())