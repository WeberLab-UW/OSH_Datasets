"""One-time migration: add processed and component_count to bom_file_paths.

SQLite supports ALTER TABLE ADD COLUMN, so no rename-recreate needed.

Usage: uv run python scripts/migrate_bom_processed.py
"""

import sqlite3
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger

logger = get_logger(__name__)


def migrate(db_path: Path = DB_PATH) -> None:
    """Add tracking columns to existing bom_file_paths table.

    Args:
        db_path: Path to the SQLite database.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")

    # Check which columns already exist
    existing = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(bom_file_paths)"
        ).fetchall()
    }

    added: list[str] = []

    if "processed" not in existing:
        conn.execute(
            "ALTER TABLE bom_file_paths "
            "ADD COLUMN processed INTEGER NOT NULL DEFAULT 0"
        )
        added.append("processed")

    if "component_count" not in existing:
        conn.execute(
            "ALTER TABLE bom_file_paths "
            "ADD COLUMN component_count INTEGER"
        )
        added.append("component_count")

    conn.commit()

    if added:
        logger.info("Added columns to bom_file_paths: %s", ", ".join(added))
    else:
        logger.info("Columns already exist, nothing to migrate")

    total = conn.execute(
        "SELECT COUNT(*) FROM bom_file_paths"
    ).fetchone()[0]
    logger.info("bom_file_paths has %d rows", total)

    conn.close()


if __name__ == "__main__":
    migrate()
