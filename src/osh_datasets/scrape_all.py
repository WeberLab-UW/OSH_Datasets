"""Run all scrapers and collect raw data from external sources."""

from pathlib import Path

from osh_datasets.config import get_logger
from osh_datasets.scrapers import ALL_SCRAPERS

logger = get_logger(__name__)


def scrape_all(
    sources: list[str] | None = None,
) -> dict[str, Path]:
    """Run scrapers and return mapping of source name to output path.

    Args:
        sources: Optional list of source names to run. If ``None``,
            runs all scrapers.

    Returns:
        Mapping from source name to the primary output file path.
    """
    results: dict[str, Path] = {}

    for scraper_cls in ALL_SCRAPERS:
        scraper = scraper_cls()  # type: ignore[abstract]
        if sources is not None and scraper.source_name not in sources:
            logger.info("Skipping %s (not in source list)", scraper.source_name)
            continue

        try:
            output = scraper.run()
            results[scraper.source_name] = output
        except Exception:
            logger.exception("Scraper %s failed", scraper.source_name)

    logger.info(
        "Scraping complete: %d/%d sources succeeded",
        len(results),
        len(ALL_SCRAPERS) if sources is None else len(sources),
    )
    return results


if __name__ == "__main__":
    import sys

    sources_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    results = scrape_all(sources_arg)
    for source, path in results.items():
        print(f"  {source}: {path}")
