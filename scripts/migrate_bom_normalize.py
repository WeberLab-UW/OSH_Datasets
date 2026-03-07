"""One-time migration: add BOM normalization columns and populate them.

Adds seven columns to ``bom_components``: component_category,
manufacturer_canonical, manufacturer_is_distributor, footprint_normalized,
footprint_mount_type, value_numeric, value_unit.

Safe to run multiple times -- adds columns only if missing, then
re-populates all rows.

Usage: uv run python scripts/migrate_bom_normalize.py
"""

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.enrichment.bom_normalize import enrich_bom_components

logger = get_logger(__name__)


def main() -> None:
    """Run BOM normalization enrichment on the existing database."""
    logger.info("Running BOM normalization migration on %s", DB_PATH)
    count = enrich_bom_components(DB_PATH)
    logger.info("Migration complete: %d rows enriched", count)


if __name__ == "__main__":
    main()
