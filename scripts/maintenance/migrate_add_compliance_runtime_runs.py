"""Apply migrations/005_compliance_runtime_runs.sql to the local SQLite DB.

Idempotent: re-running is a no-op because the migration uses CREATE TABLE
IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.

Usage:
    python scripts/migrate_add_compliance_runtime_runs.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "eu_ai_compliance.db"
MIGRATION = ROOT / "migrations" / "005_compliance_runtime_runs.sql"


def main(db_path: Path = DEFAULT_DB, migration_path: Path = MIGRATION) -> int:
    if not migration_path.exists():
        print(f"migration not found: {migration_path}", file=sys.stderr)
        return 2
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 2

    sql = migration_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

    print(f"applied {migration_path.name} -> {db_path}")
    return 0


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    raise SystemExit(main(db))