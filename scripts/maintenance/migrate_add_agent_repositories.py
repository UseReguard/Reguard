"""Migration: create the agent_repositories table.

Idempotent — safe to run multiple times. Applies
``migrations/001_agent_repositories.sql`` to the database configured by
``DATABASE_URL``. The script only creates a new table and its indexes;
it does not modify any existing table.

Usage:
    python3 scripts/migrate_add_agent_repositories.py
    python3 scripts/migrate_add_agent_repositories.py --backup   # also snapshot the DB first
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from compliance.config import DATABASE_URL  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate_agent_repositories")

MIGRATION_FILE = ROOT / "migrations" / "001_agent_repositories.sql"


def backup_db(db_path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = db_path.with_suffix(db_path.suffix + f".backup-{ts}")
    shutil.copy2(db_path, dest)
    log.info(f"Backup written to {dest}")
    return dest


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def apply_sql_script(db_path: Path, sql_path: Path) -> dict:
    """Execute the migration SQL file. Each statement is committed individually."""
    if not sql_path.exists():
        log.error(f"Migration file not found: {sql_path}")
        sys.exit(1)

    log.info(f"Connecting to {db_path}")
    conn = sqlite3.connect(db_path)
    stats = {
        "statements_run": 0,
        "already_present": [],
        "created": [],
    }

    try:
        # Pre-check: tell the user clearly if the table already exists.
        if table_exists(conn, "agent_repositories"):
            log.info("⊙ agent_repositories already exists — migration will be a no-op.")
            stats["already_present"].append("agent_repositories")
        else:
            log.info("+ Creating agent_repositories table.")

        # Execute the migration script. We strip full-line comments first
        # so that semicolons inside `--` comments (e.g. inside parentheses)
        # don't confuse the statement splitter. executescript() would also
        # work but emits no per-statement feedback, which we want for logging.
        raw_lines = sql_path.read_text().splitlines()
        cleaned_lines = []
        for line in raw_lines:
            stripped = line.lstrip()
            if stripped.startswith("--"):
                continue  # drop whole-line comments
            cleaned_lines.append(line)
        cleaned_script = "\n".join(cleaned_lines)

        for raw_stmt in cleaned_script.split(";"):
            stmt = raw_stmt.strip()
            if not stmt:
                continue
            conn.execute(stmt)
            stats["statements_run"] += 1

        conn.commit()

        if "agent_repositories" not in stats["already_present"]:
            stats["created"].append("agent_repositories")

        log.info(
            f"\n=== Migration complete: {stats['statements_run']} statements run, "
            f"{len(stats['created'])} tables created, "
            f"{len(stats['already_present'])} skipped ==="
        )
    finally:
        conn.close()

    return stats


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--backup", action="store_true",
        help="Write a timestamped copy of the database next to the original before migrating.",
    )
    args = p.parse_args()

    if not DATABASE_URL.startswith("sqlite"):
        log.error(
            "This migration script only handles SQLite. The current DATABASE_URL "
            "looks like PostgreSQL — apply migrations/001_agent_repositories.sql "
            "manually via psql instead."
        )
        sys.exit(1)

    db_path = Path(DATABASE_URL.replace("sqlite:///", ""))
    if not db_path.exists():
        log.error(f"Database file not found at {db_path}")
        sys.exit(1)

    if args.backup:
        backup_db(db_path)

    apply_sql_script(db_path, MIGRATION_FILE)


if __name__ == "__main__":
    main()
