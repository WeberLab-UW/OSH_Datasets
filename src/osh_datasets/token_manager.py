"""Multi-token rotation for API rate-limit management."""

import os
from threading import Lock

import yaml

from osh_datasets.config import get_logger

logger = get_logger(__name__)


class TokenManager:
    """Rotate through multiple API tokens to distribute rate limits.

    Tokens can be loaded from a YAML file (list of strings) or from a
    single environment variable.

    Args:
        env_var: Environment variable holding a single token.
        token_file: Path to a YAML file containing a list of tokens.

    Raises:
        ValueError: If no tokens can be loaded from either source.
    """

    def __init__(
        self,
        env_var: str = "GITHUB_TOKEN",
        token_file: str | None = None,
    ) -> None:
        self._tokens: list[str] = []
        self._index: int = 0
        self._lock = Lock()

        if token_file and os.path.exists(token_file):
            self._tokens = self._load_file(token_file)

        if not self._tokens:
            single = os.environ.get(env_var)
            if single:
                self._tokens = [single.strip()]

        if not self._tokens:
            raise ValueError(f"No tokens found. Set {env_var} or provide a token_file.")
        logger.info("Loaded %d token(s)", len(self._tokens))

    @staticmethod
    def _load_file(path: str) -> list[str]:
        """Load tokens from a YAML file.

        Args:
            path: Filesystem path to the YAML file.

        Returns:
            List of non-empty token strings.
        """
        with open(path) as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, list):
            return [str(t).strip() for t in data if str(t).strip()]
        return []

    @property
    def current(self) -> str:
        """Return the current token without rotating."""
        with self._lock:
            return self._tokens[self._index]

    def rotate(self) -> str:
        """Advance to the next token and return it.

        Returns:
            The next token in the rotation.
        """
        with self._lock:
            self._index = (self._index + 1) % len(self._tokens)
            logger.debug("Rotated to token index %d", self._index)
            return self._tokens[self._index]
