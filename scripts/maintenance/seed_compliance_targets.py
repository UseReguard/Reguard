"""Idempotently register the three pinned Article 12(1) targets.

The compliance pipeline's run_one() resolves a repo via
``agent_repositories.full_name``. On a fresh DB that table has
nothing in it, so the driver raises KeyError before the probe
even runs. This script ensures the three canonical targets are
present with the schema fields _lookup_repo() cares about
(full_name), and a minimal subset of the rest so the row is
realistic enough for downstream tools.

Run as part of any environment bootstrap, including GitHub
Actions. Safe to re-run: existing rows are preserved.

Usage:
    PYTHONPATH=src python3 scripts/maintenance/seed_compliance_targets.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from compliance.pipeline.persistence import default_db_path  # noqa: E402


# Pinned targets. The SHAs here are the same three used in
# .github/workflows/compliance.yml. If you change them, change
# both places together.
TARGETS = [
    {
        "github_id": 9000001,
        "full_name": "SWE-agent/mini-swe-agent",
        "owner": "SWE-agent",
        "name": "mini-swe-agent",
        "html_url": "https://github.com/SWE-agent/mini-swe-agent",
        "default_branch": "main",
        "sha": "25941c89cfbc91eb40b3f8756348c91d9977d57e",
    },
    {
        "github_id": 9000002,
        "full_name": "he-yufeng/CoreCoder",
        "owner": "he-yufeng",
        "name": "CoreCoder",
        "html_url": "https://github.com/he-yufeng/CoreCoder",
        "default_branch": "main",
        "sha": "a03ef36412e432fc49d972d4007b36ce44ec5d9a",
    },
    {
        "github_id": 9000003,
        "full_name": "HKUDS/nanobot",
        "owner": "HKUDS",
        "name": "nanobot",
        "html_url": "https://github.com/HKUDS/nanobot",
        "default_branch": "main",
        "sha": "4d204ba077a86dc42225c16f8f90032013ea1969",
    },
]


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dTH:%M:%SZ")


def seed(db_path: Path) -> int:
    """Insert targets that aren't already in agent_repositories.

    Returns the number of rows actually inserted (existing rows
    are skipped via INSERT OR IGNORE).
    """
    if not db_path.exists():
        print(f"DB not found at {db_path}; run src/compliance/db.py first", file=sys.stderr)
        return 0

    inserted = 0
    conn = sqlite3.connect(db_path)
    try:
        for t in TARGETS:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO agent_repositories (
                    github_id, full_name, owner, name, html_url,
                    clone_url, primary_language, stars, forks,
                    archived, fork, relevance_status, enabled,
                    discovered_at, last_metadata_refresh
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t["github_id"],
                    t["full_name"],
                    t["owner"],
                    t["name"],
                    t["html_url"],
                    f"{t['html_url']}.git",
                    "Python",
                    0,
                    0,
                    0,
                    0,
                    "accepted",
                    1,
                    _now_iso(),
                    _now_iso(),
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
                print(f"inserted {t['full_name']} (github_id={t['github_id']})")
            else:
                print(f"already present: {t['full_name']}")
        conn.commit()
    finally:
        conn.close()
    return inserted


def main() -> int:
    db_path = default_db_path()
    n = seed(db_path)
    print(f"seed_compliance_targets: {n}/{len(TARGETS)} new rows in {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
