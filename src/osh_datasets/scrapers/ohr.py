"""Scrape project metadata from the CERN Open Hardware Repository (GitLab)."""

from pathlib import Path

import orjson

from osh_datasets.config import get_logger
from osh_datasets.http import build_session, rate_limited_get
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

GROUP_URL = "https://gitlab.com/api/v4/groups/ohwr/projects"
FIELDS = (
    "id",
    "description",
    "name",
    "path",
    "path_with_namespace",
    "created_at",
    "default_branch",
    "tag_list",
    "topics",
    "ssh_url_to_repo",
    "http_url_to_repo",
    "web_url",
    "readme_url",
    "forks_count",
    "star_count",
    "empty_repo",
    "archived",
    "visibility",
    "creator_id",
    "open_issues_count",
)
NAMESPACE_FIELDS = ("id", "name", "path", "kind", "full_path", "parent_id", "web_url")


class OhrScraper(BaseScraper):
    """Fetch all projects from the OHWR GitLab group (public, no token needed).

    Output: ``data/raw/ohr/ohr_projects.json``
    """

    source_name = "ohr"

    def scrape(self) -> Path:
        """Paginate through the GitLab group API.

        Returns:
            Path to the output JSON file.
        """
        session = build_session()
        all_projects: list[dict[str, object]] = []
        page = 1

        while True:
            resp = rate_limited_get(
                session,
                GROUP_URL,
                delay=0.3,
                params={
                    "include_subgroups": "true",
                    "per_page": 100,
                    "page": page,
                },
            )
            data: list[dict[str, object]] = resp.json()
            if not data:
                break

            for project in data:
                ns = project.get("namespace", {})
                if not isinstance(ns, dict):
                    ns = {}
                record: dict[str, object] = {
                    f: project.get(f) for f in FIELDS
                }
                for nf in NAMESPACE_FIELDS:
                    record[f"namespace.{nf}"] = ns.get(nf)
                all_projects.append(record)

            page += 1

        logger.info("Retrieved %d OHR projects", len(all_projects))

        out = self.output_dir / "ohr_projects.json"
        out.write_bytes(orjson.dumps(all_projects, option=orjson.OPT_INDENT_2))
        return out
