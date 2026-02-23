"""Run all data loaders and populate the unified SQLite database."""

from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import init_db
from osh_datasets.loaders.hackaday import HackadayLoader
from osh_datasets.loaders.hardwareio import HardwareioLoader
from osh_datasets.loaders.joh import JohLoader
from osh_datasets.loaders.kitspace import KitspaceLoader
from osh_datasets.loaders.mendeley import MendeleyLoader
from osh_datasets.loaders.ohr import OhrLoader
from osh_datasets.loaders.ohx import OhxLoader
from osh_datasets.loaders.osf import OsfLoader
from osh_datasets.loaders.oshwa import OshwaLoader
from osh_datasets.loaders.plos import PlosLoader

logger = get_logger(__name__)

ALL_LOADERS = [
    HackadayLoader,
    OshwaLoader,
    OhrLoader,
    KitspaceLoader,
    HardwareioLoader,
    OhxLoader,
    MendeleyLoader,
    OsfLoader,
    PlosLoader,
    JohLoader,
]


def load_all(db_path: Path = DB_PATH) -> dict[str, int]:
    """Initialize the database and run every loader.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Mapping from source name to number of records loaded.
    """
    init_db(db_path)
    results: dict[str, int] = {}
    total = 0

    for loader_cls in ALL_LOADERS:
        loader = loader_cls()
        count = loader.run(db_path)
        results[loader.source_name] = count
        total += count

    logger.info("All loaders complete: %d total projects", total)

    # Post-processing enrichment
    from osh_datasets.component_normalizer import (
        add_component_normalized_column,
    )
    from osh_datasets.dedup import find_cross_references
    from osh_datasets.enrich_ohx_dois import backfill_dois
    from osh_datasets.enrichment.fred_ppi import add_historical_prices
    from osh_datasets.enrichment.github import enrich_from_github
    from osh_datasets.enrichment.pricing import enrich_pricing
    from osh_datasets.license_normalizer import add_normalized_column

    add_normalized_column(db_path)
    add_component_normalized_column(db_path)
    backfill_dois(db_path)
    find_cross_references(db_path)
    enrich_from_github(db_path)
    enrich_pricing(db_path)
    add_historical_prices(db_path)

    from osh_datasets.enrichment.doc_quality import score_doc_quality

    score_doc_quality(db_path)

    return results


if __name__ == "__main__":
    results = load_all()
    for source, count in results.items():
        print(f"  {source}: {count}")
    print(f"  TOTAL: {sum(results.values())}")
