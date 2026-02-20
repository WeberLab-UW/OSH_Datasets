"""Scrape PLOS articles for data availability statements and git repo links.

Consolidates the legacy ``plos_das.py`` and ``plos_gitLinks.py`` scripts into
a single scraper that fetches article XML and extracts both data availability
statements and repository URLs.
"""

import re
from pathlib import Path

import orjson
from bs4 import BeautifulSoup

from osh_datasets.config import get_logger
from osh_datasets.http import build_session, rate_limited_get
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_JOURNAL_MAP: dict[str, str] = {
    "journal.pone": "plosone",
    "journal.pmed": "plosmedicine",
    "journal.pcbi": "ploscompbiol",
    "journal.pgen": "plosgenetics",
    "journal.ppat": "plospathogens",
    "journal.pbio": "plosbiology",
    "journal.pntd": "plosntds",
}

_GIT_PATTERNS = [
    re.compile(r"https?://(?:www\.)?github\.com/[^\s)\],;]+", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?gitlab\.com/[^\s)\],;]+", re.IGNORECASE),
    re.compile(r"https?://gitlab\.[^\s/]+/[^\s)\],;]+", re.IGNORECASE),
]


def _journal_slug(doi: str) -> str:
    """Map a DOI to its PLOS journal slug."""
    for key, slug in _JOURNAL_MAP.items():
        if key in doi:
            return slug
    return "plosone"


def _xml_url(doi: str) -> str:
    """Construct the PLOS manuscript XML URL for a DOI."""
    slug = _journal_slug(doi)
    return f"https://journals.plos.org/{slug}/article/file?id={doi}&type=manuscript"


def _extract_das(soup: BeautifulSoup) -> str | None:
    """Extract the data availability statement from parsed XML."""
    from bs4 import Tag

    meta = soup.find("custom-meta", {"id": "data-availability"})
    if isinstance(meta, Tag):
        mv = meta.find("meta-value")
        if isinstance(mv, Tag):
            text: str = mv.get_text(strip=True)
            if text:
                return text

    for m in soup.find_all("custom-meta"):
        mn = m.find("meta-name")
        if isinstance(mn, Tag) and "data availability" in mn.get_text().lower():
            mv2 = m.find("meta-value")
            if isinstance(mv2, Tag):
                text2: str = mv2.get_text(strip=True)
                if text2:
                    return text2
    return None


def _extract_git_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract GitHub/GitLab repository links from article text."""
    full_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
    seen: set[str] = set()
    results: list[dict[str, str]] = []

    for pattern in _GIT_PATTERNS:
        for match in pattern.finditer(full_text):
            url = match.group().strip()
            if url not in seen:
                platform = "GitHub" if "github" in url.lower() else "GitLab"
                results.append({"repo_url": url, "platform": platform})
                seen.add(url)
    return results


class PlosScraper(BaseScraper):
    """Fetch PLOS article XML and extract DAS + repository links.

    Reads DOIs from ``data/raw/plos/dois.txt`` (one per line).
    Output: ``data/raw/plos/plos_articles.json``
    """

    source_name = "plos"

    def scrape(self) -> Path:
        """Process all DOIs and save combined results.

        Returns:
            Path to the output JSON file.
        """
        doi_file = self.output_dir / "dois.txt"
        if not doi_file.exists():
            logger.warning("No DOI file at %s, skipping", doi_file)
            out = self.output_dir / "plos_articles.json"
            out.write_bytes(orjson.dumps([]))
            return out

        dois = [
            line.strip()
            for line in doi_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return self.scrape_dois(dois)

    def scrape_dois(self, dois: list[str]) -> Path:
        """Fetch and parse articles for the given DOIs.

        Args:
            dois: List of PLOS DOI strings.

        Returns:
            Path to the output JSON file.
        """
        session = build_session()
        session.headers.update(
            {"User-Agent": "PLOS-OSH-Scraper/1.0"}
        )
        results: list[dict[str, object]] = []

        for i, doi in enumerate(dois):
            logger.info("[%d/%d] Processing %s", i + 1, len(dois), doi)
            url = _xml_url(doi)

            try:
                resp = rate_limited_get(session, url, delay=1.0)
                soup = BeautifulSoup(resp.text, "xml")

                results.append(
                    {
                        "doi": doi,
                        "data_availability_statement": _extract_das(soup),
                        "git_repo_links": _extract_git_links(soup),
                    }
                )
            except Exception:
                logger.exception("Failed to process %s", doi)
                results.append(
                    {
                        "doi": doi,
                        "data_availability_statement": None,
                        "git_repo_links": [],
                        "error": True,
                    }
                )

        logger.info(
            "Processed %d DOIs, %d with DAS",
            len(results),
            sum(1 for r in results if r.get("data_availability_statement")),
        )

        out = self.output_dir / "plos_articles.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out
