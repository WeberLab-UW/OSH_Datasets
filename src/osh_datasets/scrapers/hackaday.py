"""Scrape project data from the Hackaday.io API with multi-key rotation."""

import os
import time
from pathlib import Path

import orjson
import requests

from osh_datasets.config import get_logger
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://dev.hackaday.io/v2"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3


def _load_api_keys() -> list[str]:
    """Load Hackaday API keys from environment.

    Returns:
        List of valid API key strings.

    Raises:
        ValueError: If no keys are found.
    """
    raw = os.environ.get("HACKADAY_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ValueError(
            "No Hackaday API keys found. Set HACKADAY_API_KEYS "
            "(comma-separated) in .env"
        )
    logger.info("Loaded %d Hackaday API key(s)", len(keys))
    return keys


class HackadayClient:
    """Rate-limited Hackaday API client with key rotation.

    Args:
        api_keys: List of API keys to rotate through.
        requests_per_hour: Per-key hourly limit.
    """

    def __init__(
        self,
        api_keys: list[str],
        requests_per_hour: int = 900,
    ) -> None:
        self.api_keys = api_keys
        self.min_delay = 4.0 / len(api_keys)
        self.total_requests = 0
        self.hour_start = time.time()
        self.max_hourly = len(api_keys) * requests_per_hour
        self.session = requests.Session()

    def _next_key(self) -> str:
        """Return the next API key via round-robin."""
        now = time.time()
        if now - self.hour_start >= 3600:
            self.total_requests = 0
            self.hour_start = now

        if self.total_requests >= self.max_hourly:
            wait = 3600 - (now - self.hour_start)
            if wait > 0:
                logger.warning("Hourly limit reached, waiting %.0fs", wait)
                time.sleep(wait)
                self.total_requests = 0
                self.hour_start = time.time()

        self.total_requests += 1
        return self.api_keys[self.total_requests % len(self.api_keys)]

    def get(self, path: str) -> dict[str, object] | list[object] | None:
        """Make an authenticated GET request with retry.

        Args:
            path: API path (appended to BASE_URL).

        Returns:
            Parsed JSON response, or None on failure.
        """
        key = self._next_key()
        sep = "&" if "?" in path else "?"
        url = f"{BASE_URL}/{path}{sep}api_key={key}"

        for attempt in range(MAX_RETRIES):
            time.sleep(self.min_delay)
            try:
                resp = self.session.get(url, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json()  # type: ignore[no-any-return]
                if resp.status_code == 429:
                    logger.warning("Rate limited, waiting 60s")
                    time.sleep(60)
                    continue
                logger.warning("HTTP %d for %s", resp.status_code, path)
                return None
            except requests.exceptions.Timeout:
                logger.warning("Timeout, retry %d", attempt + 1)
                time.sleep(2**attempt)
            except requests.RequestException as exc:
                logger.error("Request error: %s", exc)
                time.sleep(2**attempt)
        return None

    def search_projects(self, term: str, limit: int = 100) -> list[dict[str, object]]:
        """Search for projects by keyword.

        Args:
            term: Search term.
            limit: Page size.

        Returns:
            List of project dicts.
        """
        all_projects: list[dict[str, object]] = []
        offset = 0

        while True:
            data = self.get(
                f"search?search_term={term}&limit={limit}&offset={offset}"
            )
            if not isinstance(data, dict):
                break
            results: list[dict[str, object]] = data.get("results", [])  # type: ignore[assignment]
            if not results:
                break
            all_projects.extend(results)
            offset += limit
            logger.info("Fetched %d projects", len(all_projects))

        return all_projects

    def get_project_links(self, project_id: str) -> list[str]:
        """Fetch repository links for a project.

        Args:
            project_id: Hackaday project ID.

        Returns:
            List of GitHub/GitLab URLs.
        """
        data = self.get(f"projects/{project_id}/links")
        if not isinstance(data, list):
            return []
        domains = ("github.com", "gitlab.com")
        return [
            link.get("url", "")
            for link in data
            if isinstance(link, dict)
            and any(d in link.get("url", "") for d in domains)
        ]

    def close(self) -> None:
        """Close the underlying session."""
        self.session.close()


class HackadayScraper(BaseScraper):
    """Search Hackaday.io for hardware projects and fetch repo links.

    Requires ``HACKADAY_API_KEYS`` in the environment.
    Output: ``data/raw/hackaday/hackaday_projects.json``
    """

    source_name = "hackaday"

    def scrape(self) -> Path:
        """Search for projects and enrich with repository links.

        Returns:
            Path to the output JSON file.
        """
        keys = _load_api_keys()
        client = HackadayClient(keys)

        try:
            projects = client.search_projects("hardware")
            logger.info("Found %d projects", len(projects))

            # Enrich with repo links
            for i, proj in enumerate(projects):
                pid = str(proj.get("rid") or proj.get("id", ""))
                if pid:
                    links = client.get_project_links(pid)
                    proj["repo_links"] = links
                if (i + 1) % 100 == 0:
                    logger.info("Enriched %d/%d", i + 1, len(projects))

            out = self.output_dir / "hackaday_projects.json"
            out.write_bytes(orjson.dumps(projects, option=orjson.OPT_INDENT_2))
            return out
        finally:
            client.close()
