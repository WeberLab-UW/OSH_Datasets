"""Fetch paper metadata from the OpenAlex API for a list of DOIs."""

import os
from pathlib import Path

import orjson

from osh_datasets.config import get_logger
from osh_datasets.http import build_session, rate_limited_get
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

API_URL = "https://api.openalex.org/works/doi:"


def _clean_doi(doi: str) -> str:
    """Normalize a DOI string: lowercase, strip protocol prefix."""
    doi = doi.lower().strip()
    if "https://doi.org/" in doi:
        doi = doi.replace("https://doi.org/", "")
    if "http://doi.org/" in doi:
        doi = doi.replace("http://doi.org/", "")
    return doi


class OpenAlexScraper(BaseScraper):
    """Fetch OpenAlex metadata for a list of DOIs.

    Reads DOIs from a text file (one per line) at
    ``data/raw/openalex/dois.txt``, or accepts them via :meth:`scrape_dois`.

    Output: ``data/raw/openalex/openalex_metadata.json``
    """

    source_name = "openalex"

    def scrape(self) -> Path:
        """Read DOIs from the input file and fetch metadata.

        Returns:
            Path to the output JSON file.
        """
        doi_file = self.output_dir / "dois.txt"
        if not doi_file.exists():
            logger.warning("No DOI file at %s, skipping", doi_file)
            out = self.output_dir / "openalex_metadata.json"
            out.write_bytes(orjson.dumps([]))
            return out

        dois = [
            line.strip()
            for line in doi_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return self.scrape_dois(dois)

    def scrape_dois(self, dois: list[str]) -> Path:
        """Fetch OpenAlex metadata for the given DOIs.

        Args:
            dois: List of DOI strings.

        Returns:
            Path to the output JSON file.
        """
        mailto = os.environ.get("OPENALEX_EMAIL", "")
        session = build_session()
        results: list[dict[str, object]] = []

        for i, doi in enumerate(dois):
            clean = _clean_doi(doi)
            logger.info("[%d/%d] Fetching: %s", i + 1, len(dois), clean)

            try:
                params: dict[str, str] = {}
                if mailto:
                    params["mailto"] = mailto
                resp = rate_limited_get(
                    session, f"{API_URL}{clean}", delay=0.5, params=params
                )
                data = resp.json()
                if isinstance(data, dict):
                    results.append(data)
            except Exception:
                logger.exception("Failed to fetch DOI %s", clean)

        logger.info("Fetched %d/%d papers", len(results), len(dois))

        out = self.output_dir / "openalex_metadata.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out
