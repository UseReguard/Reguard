"""Pretty-print statistics about the agent_repositories corpus."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select

from compliance.db import session_scope
from compliance.models import AgentRepository


def _humanise_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "n/a"
    return dt.strftime("%Y-%m-%d")


def _bucket_for_stars(stars: int) -> str:
    if stars >= 5000:
        return "5000+"
    if stars >= 1000:
        return "1000-4999"
    if stars >= 100:
        return "100-999"
    if stars >= 20:
        return "20-99"
    return "0-19"


def _bucket_for_pushed(days: Optional[int]) -> str:
    if days is None:
        return "unknown"
    if days < 30:
        return "<30 days"
    if days < 90:
        return "30-89 days"
    if days < 180:
        return "90-179 days"
    if days < 365:
        return "180-364 days"
    return "1y+"


def print_stats() -> dict:
    """Print a human-readable summary and return the raw counters as a dict."""
    with session_scope() as session:
        total: int = session.execute(select(func.count(AgentRepository.id))).scalar_one()
        rows: Iterable[AgentRepository] = session.execute(select(AgentRepository)).scalars().all()

        if total == 0:
            print("agent_repositories is empty — run `python -m repo_corpus discover` first.")
            return {"total": 0}

        # Relevance status counts
        status_counts = Counter(r.relevance_status for r in rows)
        # Category counts — only for rows that survived the relevance filter.
        # Rejected rows carry category=not_agent by design; showing them
        # here would inflate the headline distribution.
        category_counts = Counter(
            r.agent_category for r in rows
            if r.agent_category
            and r.agent_category not in ("unknown", "not_agent")
            and r.relevance_status in ("accepted", "candidate")
        )
        star_buckets = Counter(_bucket_for_stars(r.stars) for r in rows)

        today = datetime.utcnow()
        pushed_buckets = Counter(
            _bucket_for_pushed(
                (today - r.github_pushed_at).days if r.github_pushed_at else None
            )
            for r in rows
        )

        # Sanity check: every accepted row should be Python.
        non_py_accepted = [
            r for r in rows
            if r.relevance_status == "accepted"
            and (r.primary_language or "").strip() != "Python"
        ]

        # Stars distribution
        print("\n=== agent_repositories ===")
        print(f"total discovered: {total}")
        print(f"  accepted:   {status_counts.get('accepted', 0):5d}")
        print(f"  candidate:  {status_counts.get('candidate', 0):5d}")
        print(f"  rejected:   {status_counts.get('rejected', 0):5d}")
        print(f"  unknown:    {status_counts.get('unknown', 0):5d}")

        print("\nby category (accepted + candidate only):")
        if not category_counts:
            print("  (none)")
        else:
            for cat, n in sorted(category_counts.items(), key=lambda kv: -kv[1]):
                print(f"  {cat:22s} {n:5d}")

        print("\nby star band:")
        for band in ("5000+", "1000-4999", "100-999", "20-99", "0-19"):
            print(f"  {band:11s} {star_buckets.get(band, 0):5d}")

        print("\nby last-pushed bucket:")
        for band in ("<30 days", "30-89 days", "90-179 days", "180-364 days", "1y+", "unknown"):
            print(f"  {band:13s} {pushed_buckets.get(band, 0):5d}")

        if non_py_accepted:
            print(
                f"\n⚠ {len(non_py_accepted)} accepted rows are not Python primary — "
                f"investigate the classifier."
            )

    return {
        "total": total,
        "accepted": status_counts.get("accepted", 0),
        "candidate": status_counts.get("candidate", 0),
        "rejected": status_counts.get("rejected", 0),
        "unknown": status_counts.get("unknown", 0),
        "categories": dict(category_counts),
        "star_bands": dict(star_buckets),
        "pushed_buckets": dict(pushed_buckets),
        "non_python_accepted": len(non_py_accepted),
    }
