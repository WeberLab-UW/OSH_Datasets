"""Fetch comprehensive GitLab repository metadata.

Consolidates the legacy ``gitlab_metadata_extration.py`` and
``ohr_wiki_extraction.py`` into a single scraper using
:class:`~osh_datasets.token_manager.TokenManager`.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
import requests

from osh_datasets.config import get_logger
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "OSH-Datasets-GitLab-Scraper/1.0",
}


class GitLabScraper(BaseScraper):
    """Fetch metadata for GitLab repositories.

    Reads project IDs from ``data/raw/gitlab/project_ids.txt`` (one per line).
    Requires ``GITLAB_TOKEN`` in the environment (or operates unauthenticated
    for public repos).
    Output: ``data/raw/gitlab/gitlab_repos.json``
    """

    source_name = "gitlab"

    def scrape(self) -> Path:
        """Read project IDs and fetch metadata.

        Returns:
            Path to the output JSON file.
        """
        id_file = self.output_dir / "project_ids.txt"
        if not id_file.exists():
            logger.warning("No ID file at %s, skipping", id_file)
            out = self.output_dir / "gitlab_repos.json"
            out.write_bytes(orjson.dumps([]))
            return out

        ids = [
            line.strip()
            for line in id_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return self.scrape_projects(ids)

    def scrape_projects(
        self,
        project_ids: list[str],
        max_workers: int = 5,
    ) -> Path:
        """Fetch metadata for the given GitLab project IDs.

        Args:
            project_ids: List of GitLab project IDs (numeric strings).
            max_workers: Concurrent endpoint fetches per project.

        Returns:
            Path to the output JSON file.
        """
        token = os.environ.get("GITLAB_TOKEN")
        results: list[dict[str, object]] = []

        for i, pid in enumerate(project_ids):
            logger.info("[%d/%d] Fetching project %s", i + 1, len(project_ids), pid)
            data = _fetch_project(pid, token, max_workers)
            if data:
                results.append(data)
            time.sleep(0.5)

        logger.info("Fetched %d/%d projects", len(results), len(project_ids))

        out = self.output_dir / "gitlab_repos.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out


def _gl_get(
    url: str,
    token: str | None = None,
    retries: int = 3,
) -> dict[str, object] | list[object] | None:
    """GET a GitLab API endpoint with retry."""
    headers = dict(_HEADERS)
    if token:
        headers["PRIVATE-TOKEN"] = token

    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()  # type: ignore[no-any-return]
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                logger.warning("Rate limited, waiting 60s")
                time.sleep(60)
                continue
            logger.warning("HTTP %d for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            logger.debug("Request error (attempt %d): %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(2**attempt)
    return None


def _fetch_project(
    project_id: str,
    token: str | None,
    max_workers: int = 5,
) -> dict[str, object] | None:
    """Fetch metadata for a single GitLab project.

    Args:
        project_id: GitLab project ID.
        token: Optional GitLab API token.
        max_workers: Concurrent endpoint fetches.

    Returns:
        Structured project metadata dict, or None.
    """
    base = f"https://gitlab.com/api/v4/projects/{project_id}"
    repo_data = _gl_get(base, token)
    if not isinstance(repo_data, dict):
        return None

    endpoints = {
        "contributors": f"{base}/repository/contributors",
        "issues": f"{base}/issues?state=all&per_page=100",
        "merge_requests": f"{base}/merge_requests?state=all&per_page=100",
        "releases": f"{base}/releases",
        "branches": f"{base}/repository/branches",
        "tags": f"{base}/repository/tags",
        "tree": f"{base}/repository/tree",
    }

    raw: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_gl_get, url, token): key
            for key, url in endpoints.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                raw[key] = future.result()
            except Exception:
                raw[key] = None

    contributors = raw.get("contributors") or []
    issues = raw.get("issues") or []
    mrs = raw.get("merge_requests") or []
    releases = raw.get("releases") or []
    branches = raw.get("branches") or []
    tags = raw.get("tags") or []
    tree = raw.get("tree") or []

    if not isinstance(contributors, list):
        contributors = []
    if not isinstance(issues, list):
        issues = []
    if not isinstance(mrs, list):
        mrs = []
    if not isinstance(releases, list):
        releases = []
    if not isinstance(branches, list):
        branches = []
    if not isinstance(tags, list):
        tags = []
    if not isinstance(tree, list):
        tree = []

    stats = repo_data.get("statistics", {})
    if not isinstance(stats, dict):
        stats = {}

    return {
        "repository": {
            "name": repo_data.get("name", ""),
            "id": repo_data.get("id"),
            "full_name": repo_data.get("path_with_namespace", ""),
            "description": repo_data.get("description", ""),
            "url": repo_data.get("web_url", ""),
            "http_clone_url": repo_data.get("http_url_to_repo", ""),
            "created_at": repo_data.get("created_at"),
            "updated_at": repo_data.get("last_activity_at"),
            "size": stats.get("repository_size", 0),
            "default_branch": repo_data.get("default_branch"),
            "archived": repo_data.get("archived", False),
            "visibility": repo_data.get("visibility", "private"),
        },
        "metrics": {
            "stars": repo_data.get("star_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "releases_count": len(releases),
            "branches_count": len(branches),
            "tags_count": len(tags),
            "contributors_count": len(contributors),
        },
        "activity": {
            "contributors": [
                {
                    "name": c.get("name", ""),
                    "commits": c.get("commits", 0),
                }
                for c in contributors[:10]
                if isinstance(c, dict)
            ],
            "recent_releases": [
                {
                    "tag_name": r.get("tag_name"),
                    "name": r.get("name"),
                    "released_at": r.get("released_at"),
                }
                for r in releases[:5]
                if isinstance(r, dict)
            ],
        },
        "readme": {
            "readme_url": repo_data.get("readme_url", ""),
        },
        "wiki": {
            "wiki_enabled": repo_data.get("wiki_enabled", False),
        },
    }
