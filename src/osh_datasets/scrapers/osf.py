"""Scrape project metadata from the OSF (Open Science Framework) API.

Consolidates the legacy ``osf_metadata_fetcher.py`` and
``osf_comprehensive_metadata_collector.py`` into a single scraper.
"""

import re
import time
from pathlib import Path

import orjson

from osh_datasets.config import get_logger
from osh_datasets.http import build_session
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://api.osf.io/v2"
_OSF_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}


def _extract_project_id(url: str) -> str | None:
    """Extract an OSF project ID from a URL."""
    m = re.search(r"osf\.io/([a-zA-Z0-9]{5,})", url)
    return m.group(1) if m else None


def _safe_get(
    session: object,
    url: str,
    timeout: float = 30.0,
) -> dict[str, object] | list[object] | None:
    """GET with error handling -- returns parsed JSON or None."""
    import requests

    if not isinstance(session, requests.Session):
        return None
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()  # type: ignore[no-any-return]
    except requests.RequestException as exc:
        logger.debug("Request failed for %s: %s", url, exc)
    return None


class OsfScraper(BaseScraper):
    """Fetch OSF project metadata for a list of project URLs.

    Reads URLs from ``data/raw/osf/urls.txt`` (one per line).
    Output: ``data/raw/osf/osf_metadata.json``
    """

    source_name = "osf"

    def scrape(self) -> Path:
        """Read URLs from file and fetch metadata.

        Returns:
            Path to the output JSON file.
        """
        url_file = self.output_dir / "urls.txt"
        if not url_file.exists():
            logger.warning("No URL file at %s, skipping", url_file)
            out = self.output_dir / "osf_metadata.json"
            out.write_bytes(orjson.dumps([]))
            return out

        urls = [
            line.strip()
            for line in url_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        # Ensure URLs have scheme
        urls = [
            u if u.startswith("http") else f"https://{u}" for u in urls
        ]
        return self.scrape_urls(urls)

    def scrape_urls(self, urls: list[str]) -> Path:
        """Fetch metadata for the given OSF project URLs.

        Args:
            urls: List of OSF project URLs.

        Returns:
            Path to the output JSON file.
        """
        session = build_session()
        session.headers.update(_OSF_HEADERS)
        results: list[dict[str, object]] = []

        for i, url in enumerate(urls):
            logger.info("[%d/%d] Processing %s", i + 1, len(urls), url)
            project_id = _extract_project_id(url)

            if not project_id:
                logger.warning("Could not extract ID from %s", url)
                results.append({"url": url, "error": "invalid_url"})
                continue

            result = self._fetch_project(session, project_id, url)
            results.append(result)
            time.sleep(2.0)

        logger.info(
            "Processed %d URLs, %d successful",
            len(results),
            sum(1 for r in results if "error" not in r),
        )

        out = self.output_dir / "osf_metadata.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out

    def _fetch_project(
        self,
        session: object,
        project_id: str,
        url: str,
    ) -> dict[str, object]:
        """Fetch comprehensive metadata for a single OSF project.

        Args:
            session: Active requests session.
            project_id: OSF project identifier.
            url: Original project URL.

        Returns:
            Dict of project metadata.
        """
        import requests

        if not isinstance(session, requests.Session):
            return {"url": url, "error": "invalid_session"}

        node_url = f"{BASE_URL}/nodes/{project_id}/"
        metadata = _safe_get(session, node_url)
        if not isinstance(metadata, dict):
            return {"url": url, "project_id": project_id, "error": "fetch_failed"}

        data = metadata.get("data", {})
        if not isinstance(data, dict):
            return {"url": url, "project_id": project_id, "error": "no_data"}

        attrs = data.get("attributes", {})
        if not isinstance(attrs, dict):
            attrs = {}
        embeds = data.get("embeds", {})
        if not isinstance(embeds, dict):
            embeds = {}

        # License
        license_info: dict[str, str] = {}
        lic_embed = embeds.get("license", {})
        if isinstance(lic_embed, dict):
            lic_data = lic_embed.get("data")
            if isinstance(lic_data, dict):
                lic_attrs = lic_data.get("attributes", {})
                if isinstance(lic_attrs, dict):
                    license_info = {
                        "name": lic_attrs.get("name", ""),
                        "url": lic_attrs.get("url", ""),
                    }

        # Subjects
        subjects: list[dict[str, object]] = []
        subj_embed = embeds.get("subjects", {})
        if isinstance(subj_embed, dict):
            subj_data = subj_embed.get("data", [])
            if isinstance(subj_data, list):
                for s in subj_data:
                    if isinstance(s, dict):
                        s_attrs = s.get("attributes", {})
                        if isinstance(s_attrs, dict):
                            subjects.append({"text": s_attrs.get("text", "")})

        # Contributors
        contributors: list[dict[str, object]] = []
        contribs_data = _safe_get(
            session, f"{BASE_URL}/nodes/{project_id}/contributors/"
        )
        if isinstance(contribs_data, dict):
            c_list = contribs_data.get("data", [])
            if not isinstance(c_list, list):
                c_list = []
            for c in c_list:
                if not isinstance(c, dict):
                    continue
                user = c.get("embeds", {}).get("users", {}).get("data", {})
                if isinstance(user, dict):
                    contributors.append(
                        {
                            "name": user.get("attributes", {}).get(
                                "full_name", "Unknown"
                            ),
                            "permission": c.get("attributes", {}).get("permission"),
                        }
                    )

        return {
            "project_id": project_id,
            "url": url,
            "title": attrs.get("title", ""),
            "description": attrs.get("description", ""),
            "created": attrs.get("date_created"),
            "modified": attrs.get("date_modified"),
            "public": attrs.get("public", False),
            "tags": attrs.get("tags", []),
            "category": attrs.get("category"),
            "license": license_info,
            "subjects": subjects,
            "contributors": contributors,
        }
