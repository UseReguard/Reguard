#!/usr/bin/env python3
"""Export the frozen gold_article12_v1 repository set.

Reads from the canonical SQLite database and writes:
    audit/gold_article12_v1_repos.md
    audit/gold_article12_v1_repos.json

No GitHub calls. No cloning. No reclassification. No DB writes.

Validates:
    - exactly 26 repositories exported
    - all rows have verdict='gold'
    - all rows belong to audit_batch='gold_article12_v1'
    - all rows have primary_language='Python'
    - no duplicate github_id / full_name / html_url
    - all html_url values point to github.com
    - no rejected/candidate/unreviewed repos are included

Sort: agent_category, then full_name.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "eu_ai_compliance.db"
OUT_DIR = PROJECT_ROOT / "audit"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_gold(conn: sqlite3.Connection, batch: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            r.full_name,
            r.html_url,
            r.clone_url,
            r.agent_category,
            r.primary_language,
            r.stars,
            r.github_id
        FROM agent_repository_audits a
        JOIN agent_repositories r ON r.id = a.repository_id
        WHERE a.audit_batch = ? AND a.verdict = 'gold'
        ORDER BY r.agent_category ASC, r.full_name ASC
        """,
        (batch,),
    ).fetchall()


def _validate(rows: list[sqlite3.Row]) -> list[str]:
    """Return a list of validation problems; empty list if clean."""
    problems: list[str] = []

    if len(rows) != 26:
        problems.append(f"expected 26 repos, got {len(rows)}")

    github_ids = [r["github_id"] for r in rows]
    full_names = [r["full_name"] for r in rows]
    html_urls = [r["html_url"] for r in rows]

    for label, vals in (
        ("github_id", github_ids),
        ("full_name", full_names),
        ("html_url", html_urls),
    ):
        seen: set = set()
        dupes: list = []
        for v in vals:
            if v in seen:
                dupes.append(v)
            seen.add(v)
        if dupes:
            problems.append(f"duplicate {label}: {sorted(set(dupes))}")

    for r in rows:
        if r["primary_language"] != "Python":
            problems.append(
                f"{r['full_name']}: primary_language={r['primary_language']!r} (expected 'Python')"
            )
        if not r["html_url"].startswith("https://github.com/"):
            problems.append(
                f"{r['full_name']}: html_url={r['html_url']!r} not on github.com"
            )
        if not r["html_url"]:
            problems.append(f"{r['full_name']}: html_url is empty")
        if not r["full_name"]:
            problems.append(f"row with github_id={r['github_id']}: full_name is empty")

    return problems


def _render_markdown(rows: list[sqlite3.Row]) -> str:
    lines: list[str] = []
    lines.append("# gold_article12_v1 repositories\n\n")
    lines.append("Frozen gold set for deterministic runtime-test development.\n\n")
    lines.append("| # | Repository | Category | URL |\n")
    lines.append("|---|------------|----------|-----|\n")
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['full_name']} | {r['agent_category']} | {r['html_url']} |\n"
        )
    lines.append("\n```text\n")
    for r in rows:
        lines.append(f"{r['html_url']}\n")
    lines.append("```\n")
    return "".join(lines)


def _render_json(rows: list[sqlite3.Row]) -> str:
    payload = [
        {
            "full_name": r["full_name"],
            "html_url": r["html_url"],
            "clone_url": r["clone_url"],
            "agent_category": r["agent_category"],
            "primary_language": r["primary_language"],
            "stars": r["stars"],
            # default_branch is not stored in agent_repositories —
            # surfaced as null so downstream consumers don't surprise on
            # missing-key access.
            "default_branch": None,
            "github_id": r["github_id"],
        }
        for r in rows
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    db_path = Path(os.environ.get("EU_AI_DB_PATH", DEFAULT_DB))
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = _connect(db_path)
    try:
        rows = _load_gold(conn, "gold_article12_v1")
    finally:
        conn.close()

    problems = _validate(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / "gold_article12_v1_repos.md"
    json_path = OUT_DIR / "gold_article12_v1_repos.json"
    md_path.write_text(_render_markdown(rows), encoding="utf-8")
    json_path.write_text(_render_json(rows), encoding="utf-8")

    by_category = Counter(r["agent_category"] for r in rows)
    missing = [k for k in ("clone_url", "html_url", "agent_category",
                           "primary_language", "full_name")
               if any(not r[k] for r in rows)]

    print(f"total repos: {len(rows)}")
    print("count by category:")
    for cat, n in sorted(by_category.items()):
        print(f"  {cat}: {n}")
    if missing:
        print(f"missing URL fields (any empty): {missing}")
    else:
        print("missing URL fields: none")
    if problems:
        print("DUPLICATE / VALIDATION CHECKS FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 2
    else:
        print("duplicate checks: all passed")

    print(f"\nwrote {md_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
