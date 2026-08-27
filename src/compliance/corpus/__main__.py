"""CLI entry point: ``python -m compliance.corpus <command> [options]``.

Commands
--------
discover    Run GitHub searches, classify, and insert into agent_repositories.
stats       Print corpus statistics.
list        Print a tabular list of stored repositories.
refresh     Re-fetch GitHub metadata for stored repositories.
reclassify  Re-run the heuristic on stored rows and update relevance_*
            fields without calling GitHub. Cheap; no API budget consumed.

Common options
--------------
--limit N         Cap on results (rows inserted / rows listed / rows refreshed).
--query Q         Override the default query list for `discover` (repeatable).
--min-stars N     Drop items below this star count (default 0).
--category CAT    Filter by agent_category (list / stats).
--status STATUS   Filter by relevance_status (list).
--only-status S   Restrict ``reclassify`` to rows whose current status is S.
--dry-run         Show what ``reclassify`` would change without writing.

Examples
--------
    # Initial discovery (default queries, unlimited)
    PYTHONPATH=src python -m compliance.corpus discover --limit 5000

    # Discovery with a tighter star floor
    PYTHONPATH=src python -m compliance.corpus discover --min-stars 50

    # Single custom query
    PYTHONPATH=src python -m compliance.corpus discover --query 'topic:llm-agent language:Python'

    # Show corpus stats
    PYTHONPATH=src python -m compliance.corpus stats

    # List the top 20 candidates by recency
    PYTHONPATH=src python -m compliance.corpus list --status candidate --limit 20

    # Refresh the 50 most-stale rows
    PYTHONPATH=src python -m compliance.corpus refresh --limit 50

    # Preview reclassification impact (no writes)
    PYTHONPATH=src python -m compliance.corpus reclassify --dry-run

    # Reclassify only the rows currently labelled ``candidate``
    PYTHONPATH=src python -m compliance.corpus reclassify --only-status candidate
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make `src.repo_corpus` and `src.db` importable whether the user invokes
# us as `python -m compliance.corpus` (requires the project root on sys.path) or
# `PYTHONPATH=src python -m compliance.corpus` from inside `src/`. The existing
# scripts in this project follow the same `from compliance.db import ...` pattern
# (see scripts/init_db.sh, scripts/migrate_add_detection_columns.py).
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from compliance.corpus import pipeline, queries, stats  # noqa: E402
from compliance.corpus.classifier import ALL_CATEGORIES, ALL_STATUSES  # noqa: E402


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--limit", type=int, default=None,
                   help="Cap on number of rows (default: unlimited for discover, 50 for list/refresh).")


def cmd_discover(args: argparse.Namespace) -> int:
    q_list = args.query if args.query else None
    if q_list:
        q_list = [queries.parse_user_query(q) for q in q_list]
    run = pipeline.discover(
        queries=q_list,
        min_stars=args.min_stars or 0,
        max_total=args.limit,
    )
    print("\n=== discover summary ===")
    print(f"queries run:           {run.queries_run}")
    print(f"items fetched:         {run.fetched}")
    print(f"after lang=Python:     {run.after_lang_filter}")
    print(f"after dedup vs DB:     {run.after_dedup}")
    print(f"  inserted:            {run.inserted}")
    print(f"  accepted:            {run.classified.get('accepted', 0)}")
    print(f"  candidate:           {run.classified.get('candidate', 0)}")
    print(f"  rejected:            {run.classified.get('rejected', 0)}")
    if args.query:
        print(f"queries:               {args.query}")
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    stats.print_stats()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    limit = args.limit if args.limit is not None else 50
    rows = pipeline.list_repositories(
        limit=limit,
        category=args.category,
        status=args.status,
        min_stars=args.min_stars or 0,
    )
    if not rows:
        print("(no rows match)")
        return 0

    headers = ("stars", "status", "category", "pushed", "full_name")
    widths  = (6, 10, 22, 12, 60)

    def fmt(values):
        return "  ".join(str(v)[:w].ljust(w) for v, w in zip(values, widths))

    print(fmt(headers))
    print(fmt(tuple("-" * w for w in widths)))
    for r in rows:
        pushed = r["github_pushed_at"].strftime("%Y-%m-%d") if r["github_pushed_at"] else "n/a"
        print(fmt((r["stars"], r["relevance_status"], r["agent_category"] or "—",
                   pushed, r["full_name"])))
    print(f"\n{len(rows)} row(s)")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    run = pipeline.refresh_metadata(
        full_name=args.full_name,
        limit=args.limit if args.limit is not None else 50,
    )
    print(f"refreshed: {run.inserted}")
    return 0


def cmd_reclassify(args: argparse.Namespace) -> int:
    run = pipeline.reclassify(
        only_status=args.only_status,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print("\n=== reclassify summary ===")
    print(f"scanned:           {run.scanned}")
    print(f"updated:           {run.updated}")
    print(f"  status changes:  {run.status_changes}")
    print(f"  category changes:{run.category_changes}")
    if run.before or run.after:
        print("\nbefore:")
        for k in ("accepted", "candidate", "rejected", "unknown"):
            print(f"  {k:9s} {run.before.get(k, 0):5d}")
        print("after:")
        for k in ("accepted", "candidate", "rejected", "unknown"):
            print(f"  {k:9s} {run.after.get(k, 0):5d}")
    if args.dry_run:
        print("\n(dry-run: no rows were written)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m compliance.corpus",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("discover", help="Run GitHub searches and insert.")
    pd.add_argument("--query", action="append", help="Override default query (repeatable).")
    pd.add_argument("--min-stars", type=int, default=0, help="Drop items below this star count.")
    pd.add_argument("--limit", type=int, default=None, help="Cap on rows inserted.")
    pd.set_defaults(func=cmd_discover)

    ps = sub.add_parser("stats", help="Print corpus statistics.")
    ps.set_defaults(func=cmd_stats)

    pl = sub.add_parser("list", help="List stored repositories.")
    pl.add_argument("--category", choices=ALL_CATEGORIES, help="Filter by agent_category.")
    pl.add_argument("--status",   choices=ALL_STATUSES,   help="Filter by relevance_status.")
    pl.add_argument("--min-stars", type=int, default=0)
    pl.add_argument("--limit", type=int, default=50)
    pl.set_defaults(func=cmd_list)

    pr = sub.add_parser("refresh", help="Re-fetch GitHub metadata for stored repositories.")
    pr.add_argument("--full-name", help="Refresh exactly one repository by full_name.")
    pr.add_argument("--limit", type=int, default=50)
    pr.set_defaults(func=cmd_refresh)

    px = sub.add_parser("reclassify", help="Re-run heuristic on stored rows; update relevance fields.")
    px.add_argument("--only-status", choices=ALL_STATUSES,
                    help="Reclassify only rows whose current relevance_status matches.")
    px.add_argument("--limit", type=int, default=None,
                    help="Cap on rows scanned (default: all).")
    px.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing.")
    px.set_defaults(func=cmd_reclassify)

    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
