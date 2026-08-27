"""Migration: add detection_method columns to law_articles + framework_items.

SQLAlchemy's create_all() only creates missing tables, not missing columns on
existing tables. This script runs ALTER TABLE ADD COLUMN for each new column.

Safe to run multiple times — it checks for column existence first.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from compliance.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate_detection_columns")


# Columns to add: (table, column_name, sql_type)
COLUMNS = [
    ("law_articles", "detection_method", "VARCHAR(10)"),
    ("law_articles", "detection_confidence", "REAL"),
    ("law_articles", "detection_classified_by", "VARCHAR(30)"),
    ("law_articles", "detection_reasoning", "TEXT"),
    ("law_articles", "detection_reviewed_at", "DATETIME"),

    ("framework_items", "detection_method", "VARCHAR(10)"),
    ("framework_items", "detection_confidence", "REAL"),
    ("framework_items", "detection_classified_by", "VARCHAR(30)"),
    ("framework_items", "detection_reasoning", "TEXT"),
    ("framework_items", "detection_reviewed_at", "DATETIME"),
]

# Indexes to create after columns exist
INDEXES = [
    ("law_articles", "ix_law_articles_detection_method", "detection_method"),
    ("framework_items", "ix_fw_items_detection_method", "detection_method"),
]


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cur.fetchone() is not None


def run() -> dict:
    if not DATABASE_URL.startswith("sqlite"):
        log.error("This migration script only handles SQLite. Use Alembic for PostgreSQL.")
        sys.exit(1)

    db_path = DATABASE_URL.replace("sqlite:///", "")
    log.info(f"Connecting to {db_path}")
    conn = sqlite3.connect(db_path)
    stats = {"columns_added": [], "columns_skipped": [], "indexes_created": []}

    try:
        for table, column, sql_type in COLUMNS:
            existing = existing_columns(conn, table)
            if column in existing:
                log.info(f"  � {table}.{column} already exists")
                stats["columns_skipped"].append(f"{table}.{column}")
                continue
            log.info(f"  + Adding {table}.{column} ({sql_type})")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
            stats["columns_added"].append(f"{table}.{column}")

        for table, index_name, column in INDEXES:
            if index_exists(conn, index_name):
                log.info(f"  ⊙ Index {index_name} already exists")
                continue
            log.info(f"  + Creating index {index_name}")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})"
            )
            stats["indexes_created"].append(index_name)

        conn.commit()
    finally:
        conn.close()

    log.info(
        f"\n=== Migration complete: "
        f"{len(stats['columns_added'])} columns added, "
        f"{len(stats['columns_skipped'])} skipped, "
        f"{len(stats['indexes_created'])} indexes created ==="
    )
    return stats


if __name__ == "__main__":
    run()
