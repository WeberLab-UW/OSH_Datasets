"""Scrape project data from the OSHWA Certification API."""

from pathlib import Path

import orjson

from osh_datasets.config import get_logger, require_env
from osh_datasets.http import build_session, rate_limited_get
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

API_URL = "https://certificationapi.oshwa.org/api/projects"
PAGE_SIZE = 1000


class OshwaScraper(BaseScraper):
    """Fetch all certified projects from the OSHWA API.

    Requires the ``OSHWA_API_TOKEN`` environment variable (JWT).
    Output: ``data/raw/oshwa/oshwa_projects.json``
    """

    source_name = "oshwa"

    def scrape(self) -> Path:
        """Paginate through the OSHWA API and save all projects.

        Returns:
            Path to the output JSON file.
        """
        token = require_env("OSHWA_API_TOKEN")
        session = build_session()
        session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

        all_projects: list[dict[str, object]] = []
        offset = 0

        while True:
            params = {"limit": PAGE_SIZE, "offset": offset}
            logger.info("Fetching projects %d-%d ...", offset, offset + PAGE_SIZE - 1)

            resp = rate_limited_get(
                session, API_URL, delay=0.1, params=params
            )
            data = resp.json()
            items: list[dict[str, object]] = data.get("items", [])
            total: int = data.get("total", 0)

            if not items:
                break

            all_projects.extend(items)

            if len(all_projects) >= total or len(items) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        logger.info("Retrieved %d projects", len(all_projects))

        out = self.output_dir / "oshwa_projects.json"
        out.write_bytes(orjson.dumps(all_projects, option=orjson.OPT_INDENT_2))
        return out
