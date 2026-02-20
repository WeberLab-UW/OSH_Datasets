"""Abstract base for all data source loaders."""

from abc import ABC, abstractmethod
from pathlib import Path

from osh_datasets.config import get_logger

logger = get_logger(__name__)


class BaseLoader(ABC):
    """Load cleaned data from a single source into the unified database.

    Subclasses must implement :meth:`load` which receives a database path
    and inserts/upserts rows using helpers from :mod:`osh_datasets.db`.

    Args:
        data_dir: Root data directory (defaults to ``config.DATA_DIR``).
    """

    source_name: str = ""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            from osh_datasets.config import DATA_DIR

            data_dir = DATA_DIR
        self.data_dir = data_dir

    @abstractmethod
    def load(self, db_path: Path) -> int:
        """Read source data and insert into the database at *db_path*.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of project records loaded.
        """

    def run(self, db_path: Path) -> int:
        """Execute the loader with logging.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of project records loaded.
        """
        logger.info("Loading %s ...", self.source_name)
        count = self.load(db_path)
        logger.info("Loaded %d projects from %s", count, self.source_name)
        return count
