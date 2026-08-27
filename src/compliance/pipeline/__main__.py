"""CLI entry point.

Usage:
    python -m compliance.pipeline run --repo OWNER/NAME [--sha SHA]
    python -m compliance.pipeline run-gold --limit 3
    python -m compliance.pipeline list-repos
    python -m compliance.pipeline list-requirements
    python -m compliance.pipeline recent [--requirement ID]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from compliance.adapters import ADAPTER_REGISTRY
from compliance.pipeline.driver import (
    DEFAULT_SCENARIO_12_1,
    list_registered_requirements,
    run_one,
)
from compliance.pipeline.persistence import default_db_path, recent_runs


def _gold_repos(db_path: Path) -> list[str]:
    """List repos in the frozen gold_article12_v1 set, sorted."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT a.full_name
            FROM agent_repositories a
            JOIN article_runtime_assessments b
              ON b.repository_id = a.id
             AND b.celex = '32024R1689'
             AND b.article_number = '12'
            WHERE a.relevance_status = 'agent_relevant'
            ORDER BY a.full_name
            """
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _sha_for(db_path: Path, full_name: str) -> str | None:
    """Look up the most recent recorded SHA for the repo."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT repo_sha FROM compliance_runtime_runs
            WHERE repo_full_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (full_name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]
    except sqlite3.OperationalError:
        # table missing
        return None
    finally:
        conn.close()


def _cmd_run(args: argparse.Namespace) -> int:
    sha = args.sha
    if sha is None:
        sha = _sha_for(default_db_path(), args.repo)
    if sha is None:
        print(
            f"--sha is required (no prior run for {args.repo}); "
            f"set the SHA explicitly",
            file=sys.stderr,
        )
        return 2

    record = run_one(full_name=args.repo, sha=sha)
    print(json.dumps({
        "repository": record.repository.full_name,
        "sha": record.repository.sha,
        "requirement_id": record.requirement_id,
        "scenario_id": record.scenario_id,
        "status": record.status.value,
        "reason": record.reason,
        "duration_seconds": round(record.duration_seconds, 3),
        "event_count": len(record.evidence.events),
    }, indent=2))
    return 0


def _cmd_run_gold(args: argparse.Namespace) -> int:
    db_path = default_db_path()
    gold = _gold_repos(db_path)
    if args.limit is not None:
        gold = gold[: args.limit]

    print(f"running gold set: {len(gold)} repos", file=sys.stderr)
    results = []
    for full_name in gold:
        sha = _sha_for(db_path, full_name)
        if sha is None:
            results.append({
                "repository": full_name,
                "status": "SKIPPED",
                "reason": "no prior SHA in DB; --sha required for first run",
            })
            continue

        try:
            record = run_one(full_name=full_name, sha=sha)
            results.append({
                "repository": full_name,
                "sha": record.repository.sha,
                "status": record.status.value,
                "reason": record.reason,
                "duration_seconds": round(record.duration_seconds, 3),
                "event_count": len(record.evidence.events),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "repository": full_name,
                "status": "ERROR",
                "reason": repr(exc),
            })

    print(json.dumps(results, indent=2))
    return 0


def _cmd_list_repos(args: argparse.Namespace) -> int:
    for full_name in sorted(ADAPTER_REGISTRY.keys()):
        print(full_name)
    return 0


def _cmd_list_requirements(args: argparse.Namespace) -> int:
    for rid in list_registered_requirements():
        print(rid)
    return 0


def _cmd_recent(args: argparse.Namespace) -> int:
    rows = recent_runs(
        default_db_path(),
        limit=args.limit,
        requirement_id=args.requirement,
    )
    for row in rows:
        print(
            f"{row['created_at']}\t{row['repo_full_name']}\t"
            f"{row['requirement_id']}\t{row['status']}\t{row['reason']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compliance_pipeline",
        description=(
            "Deterministic agent-runtime compliance pipeline. "
            "First requirement: EU AI Act Article 12(1) — automatic event "
            "recording over the lifetime of the system."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run one repo against one requirement")
    p_run.add_argument("--repo", required=True, help="owner/name")
    p_run.add_argument("--sha", help="exact commit SHA; required on first run")
    p_run.set_defaults(func=_cmd_run)

    p_gold = sub.add_parser("run-gold", help="run the gold_article12_v1 set")
    p_gold.add_argument("--limit", type=int, help="cap to first N repos")
    p_gold.set_defaults(func=_cmd_run_gold)

    p_lr = sub.add_parser("list-repos", help="list registered repo adapters")
    p_lr.set_defaults(func=_cmd_list_repos)

    p_lreq = sub.add_parser(
        "list-requirements", help="list registered requirement tests"
    )
    p_lreq.set_defaults(func=_cmd_list_requirements)

    p_rec = sub.add_parser("recent", help="show recent runs")
    p_rec.add_argument("--limit", type=int, default=20)
    p_rec.add_argument("--requirement")
    p_rec.set_defaults(func=_cmd_recent)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())