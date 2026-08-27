#!/usr/bin/env python3
"""Apply migration 002: add agent_repositories.reclassified_at.

Mirrors the style of scripts/migrate_add_agent_repositories.py.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION_FILE = PROJECT_ROOT / "migrations" / "002_agent_repositories_reclassified_at.sql"

# Same DB resolution as scripts/init_db.sh: respect DATABASE_URL if set,
# else fall back to the canonical SQLite path.
import re
_env_db = os.environ.get("EU_AI_DB_PATH")
DEFAULT_DB = Path(_env_db) if _env_db else (PROJECT_ROOT / "data" / "eu_ai_compliance.db")


def strip_full_line_comments(sql: str) -> str:
    """Drop whole-line `-- ...` comments before splitting on `;`.

    Multi-statement migrations sometimes put semicolons inside comments,
    which makes a naive split on `;` break.
    """
    out_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def split_statements(sql: str) -> list[str]:
    cleaned = strip_full_line_comments(sql)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def main() -> int:
    if not DEFAULT_DB.exists():
        print(f"DB not found: {DEFAULT_DB}", file=sys.stderr)
        return 1
    if not MIGRATION_FILE.exists():
        print(f"Migration file not found: {MIGRATION_FILE}", file=sys.stderr)
        return 1

    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    statements = split_statements(sql)
    print(f"applying {len(statements)} statement(s) from {MIGRATION_FILE.name} → {DEFAULT_DB}")

    conn = sqlite3.connect(str(DEFAULT_DB))
    try:
        for stmt in statements:
            print(f"  exec: {stmt[:80]}{'...' if len(stmt) > 80 else ''}")
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
