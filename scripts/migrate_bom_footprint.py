"""One-time migration: add footprint column and dedup index to bom_components.

Usage: uv run python scripts/migrate_bom_footprint.py
"""

import sqlite3
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger

logger = get_logger(__name__)


def migrate(db_path: Path = DB_PATH) -> None:
    """Add footprint column and dedup index to bom_components.

    Also resets previously-failed BOM file paths so they can be
    re-processed with the improved parser.

    Args:
        db_path: Path to the SQLite database.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")

    existing = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(bom_components)"
        ).fetchall()
    }

    added: list[str] = []

    if "footprint" not in existing:
        conn.execute(
            "ALTER TABLE bom_components ADD COLUMN footprint TEXT"
        )
        added.append("footprint")

    # Remove existing duplicates before creating the unique index
    cursor = conn.execute(
        "DELETE FROM bom_components "
        "WHERE rowid NOT IN ("
        "  SELECT MIN(rowid) "
        "  FROM bom_components "
        "  WHERE reference IS NOT NULL AND part_number IS NOT NULL "
        "  GROUP BY project_id, reference, part_number"
        ") "
        "AND reference IS NOT NULL AND part_number IS NOT NULL"
    )
    if cursor.rowcount:
        logger.info("Removed %d duplicate rows", cursor.rowcount)

    # Dedup partial index
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bom_comp_dedup "
        "ON bom_components(project_id, reference, part_number) "
        "WHERE reference IS NOT NULL AND part_number IS NOT NULL"
    )
    added.append("idx_bom_comp_dedup")

    # Reset previously-failed files for re-processing
    cursor = conn.execute(
        "UPDATE bom_file_paths SET processed = 0 "
        "WHERE processed = 1 AND component_count = 0"
    )
    reset_count = cursor.rowcount

    conn.commit()

    if added:
        logger.info("Added to bom_components: %s", ", ".join(added))
    if reset_count:
        logger.info("Reset %d failed BOM file paths for reprocessing", reset_count)

    total = conn.execute(
        "SELECT COUNT(*) FROM bom_components"
    ).fetchone()[0]
    logger.info("bom_components has %d rows", total)

    conn.close()


if __name__ == "__main__":
    migrate()
