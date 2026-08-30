"""Apply migrations 006–009 (corpus_runs, corpus_run_repositories,
evaluation_jobs, evaluation_attempts) to the local SQLite DB.

Idempotent — every migration uses CREATE TABLE IF NOT EXISTS and
CREATE INDEX IF NOT EXISTS. Article 12(1) v1.4.0 frozen contract is
unaffected.

Usage:
    python3 scripts/migrate_add_corpus_runs.py
    python3 scripts/migrate_add_corpus_runs.py /path/to/eu_ai_compliance.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "eu_ai_compliance.db"

MIGRATIONS = (
    ROOT / "migrations" / "006_corpus_runs.sql",
    ROOT / "migrations" / "007_corpus_run_repositories.sql",
    ROOT / "migrations" / "008_evaluation_jobs.sql",
    ROOT / "migrations" / "009_evaluation_attempts.sql",
)


def main(db_path: Path = DEFAULT_DB) -> int:
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(db_path)
    try:
        for migration in MIGRATIONS:
            if not migration.exists():
                print(f"migration not found: {migration}", file=sys.stderr)
                return 2
            sql = migration.read_text(encoding="utf-8")
            conn.executescript(sql)
            print(f"applied {migration.name} -> {db_path}")
        conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    raise SystemExit(main(db))
