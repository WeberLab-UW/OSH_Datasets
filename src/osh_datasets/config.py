"""Centralized configuration: logging, paths, and environment variables."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
CLEANED_DIR: Path = DATA_DIR / "cleaned"
DB_PATH: Path = DATA_DIR / "osh_datasets.db"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with console output.

    Args:
        name: Logger name (typically ``__name__``).
        level: Logging level.

    Returns:
        Configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def require_env(key: str) -> str:
    """Return an environment variable or raise with a clear message.

    Args:
        key: Environment variable name.

    Returns:
        The variable's value.

    Raises:
        EnvironmentError: If the variable is not set.
    """
    value = os.environ.get(key)
    if value is None:
        raise OSError(
            f"Required environment variable {key!r} is not set. "
            f"Add it to .env or export it in your shell."
        )
    return value
