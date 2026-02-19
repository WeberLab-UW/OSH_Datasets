"""Abstract base for all data source scrapers."""

from abc import ABC, abstractmethod
from pathlib import Path

from osh_datasets.config import RAW_DIR, get_logger

logger = get_logger(__name__)


class BaseScraper(ABC):
    """Scrape raw data from a single external source.

    Subclasses must implement :meth:`scrape` which fetches data from an
    external API or website and writes output to ``output_dir``.

    Args:
        output_dir: Directory for scraped output files.
            Defaults to ``RAW_DIR / <source_name>``.
    """

    source_name: str = ""

    def __init__(self, output_dir: Path | None = None) -> None:
        if output_dir is None:
            output_dir = RAW_DIR / self.source_name
        self.output_dir = output_dir

    @abstractmethod
    def scrape(self) -> Path:
        """Fetch data from the external source and write to disk.

        Returns:
            Path to the primary output file.
        """

    def run(self) -> Path:
        """Execute the scraper with logging and directory setup.

        Returns:
            Path to the primary output file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Scraping %s -> %s", self.source_name, self.output_dir)
        output = self.scrape()
        logger.info("Finished %s: %s", self.source_name, output)
        return output
