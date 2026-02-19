"""Fetch comprehensive GitHub repository metadata.

Consolidates the legacy ``gh_data_extraction.py``, ``gh_opt.py``,
``repo_readme_tree_processer.py``, and ``gh_repometrics.py`` into a
single scraper using :class:`~osh_datasets.token_manager.TokenManager`.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
import requests

from osh_datasets.config import get_logger
from osh_datasets.scrapers.base import BaseScraper
from osh_datasets.token_manager import TokenManager

logger = get_logger(__name__)

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "OSH-Datasets-GitHub-Scraper/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _extract_owner_repo(url: str) -> tuple[str, str] | None:
    """Parse ``owner/repo`` from a GitHub URL.

    Args:
        url: GitHub repository URL.

    Returns:
        ``(owner, repo)`` tuple, or None if unparseable.
    """
    url = url.strip().rstrip("/")
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url, re.IGNORECASE)
    if m:
        repo = m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return m.group(1), repo
    return None


class GitHubScraper(BaseScraper):
    """Fetch metadata for GitHub repositories.

    Reads repo URLs from ``data/raw/github/repos.txt`` (one per line).
    Requires ``GITHUB_TOKEN`` in the environment.
    Output: ``data/raw/github/github_repos.json``
    """

    source_name = "github"

    def scrape(self) -> Path:
        """Read URLs and fetch metadata.

        Returns:
            Path to the output JSON file.
        """
        url_file = self.output_dir / "repos.txt"
        if not url_file.exists():
            logger.warning("No repo list at %s, skipping", url_file)
            out = self.output_dir / "github_repos.json"
            out.write_bytes(orjson.dumps([]))
            return out

        urls = [
            line.strip()
            for line in url_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        repos = []
        for u in urls:
            parsed = _extract_owner_repo(u)
            if parsed:
                repos.append(parsed)
        return self.scrape_repos(repos)

    def scrape_repos(
        self,
        repos: list[tuple[str, str]],
        max_workers: int = 5,
    ) -> Path:
        """Fetch metadata for the given ``(owner, repo)`` pairs.

        Args:
            repos: List of ``(owner, repo)`` tuples.
            max_workers: Concurrent request threads.

        Returns:
            Path to the output JSON file.
        """
        tm = TokenManager(env_var="GITHUB_TOKEN")
        results: list[dict[str, object]] = []

        for i, (owner, repo) in enumerate(repos):
            logger.info("[%d/%d] Fetching %s/%s", i + 1, len(repos), owner, repo)
            data = _fetch_repo(tm, owner, repo, max_workers)
            if data:
                results.append(data)
            time.sleep(0.5)

        logger.info("Fetched %d/%d repos", len(results), len(repos))

        out = self.output_dir / "github_repos.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out


def _make_session(tm: TokenManager) -> requests.Session:
    """Create a session with the current token."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    s.headers["Authorization"] = f"Bearer {tm.current}"
    return s


def _get_json(
    tm: TokenManager,
    url: str,
    retries: int = 3,
) -> dict[str, object] | list[object] | None:
    """GET with retry and token rotation on rate limit."""
    for attempt in range(retries):
        try:
            session = _make_session(tm)
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()  # type: ignore[no-any-return]
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
                if remaining == 0 or "rate limit" in resp.text.lower():
                    tm.rotate()
                    continue
            if resp.status_code == 401:
                tm.rotate()
                continue
            logger.warning("HTTP %d for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            logger.debug("Request error (attempt %d): %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(2**attempt)
    return None


def _fetch_repo(
    tm: TokenManager,
    owner: str,
    repo: str,
    max_workers: int = 5,
) -> dict[str, object] | None:
    """Fetch comprehensive metadata for a single repository.

    Args:
        tm: Token manager for authentication.
        owner: Repository owner.
        repo: Repository name.
        max_workers: Concurrent endpoint fetches.

    Returns:
        Structured repository metadata dict, or None.
    """
    base = f"https://api.github.com/repos/{owner}/{repo}"
    repo_data = _get_json(tm, base)
    if not isinstance(repo_data, dict):
        return None

    endpoints = {
        "contributors": f"{base}/contributors",
        "issues": f"{base}/issues?state=all&per_page=100",
        "pulls": f"{base}/pulls?state=all&per_page=100",
        "releases": f"{base}/releases",
        "branches": f"{base}/branches",
        "tags": f"{base}/tags",
        "community": f"{base}/community/profile",
        "readme": f"{base}/readme",
        "languages": f"{base}/languages",
        "topics": f"{base}/topics",
    }

    raw: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_get_json, tm, url): key
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
    pulls = raw.get("pulls") or []
    releases = raw.get("releases") or []
    branches = raw.get("branches") or []
    tags = raw.get("tags") or []
    community = raw.get("community") or {}
    readme = raw.get("readme") or {}
    languages = raw.get("languages") or {}
    topics = raw.get("topics") or {}

    if not isinstance(contributors, list):
        contributors = []
    if not isinstance(issues, list):
        issues = []
    if not isinstance(pulls, list):
        pulls = []
    if not isinstance(releases, list):
        releases = []
    if not isinstance(branches, list):
        branches = []
    if not isinstance(tags, list):
        tags = []
    if not isinstance(community, dict):
        community = {}
    if not isinstance(readme, dict):
        readme = {}
    if not isinstance(languages, dict):
        languages = {}
    if not isinstance(topics, dict):
        topics = {}

    actual_issues = [i for i in issues if "pull_request" not in i]
    open_prs = [p for p in pulls if p.get("state") == "open"]
    closed_prs = [p for p in pulls if p.get("state") == "closed"]

    lic = repo_data.get("license")

    return {
        "repository": {
            "owner": owner,
            "name": repo,
            "full_name": repo_data.get("full_name"),
            "description": repo_data.get("description", ""),
            "url": repo_data.get("html_url"),
            "created_at": repo_data.get("created_at"),
            "updated_at": repo_data.get("updated_at"),
            "pushed_at": repo_data.get("pushed_at"),
            "size": repo_data.get("size", 0),
            "default_branch": repo_data.get("default_branch"),
            "language": repo_data.get("language"),
            "license": lic.get("name") if isinstance(lic, dict) else None,
            "archived": repo_data.get("archived", False),
            "private": repo_data.get("private", False),
        },
        "metrics": {
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "watchers": repo_data.get("watchers_count", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "total_issues": len(actual_issues),
            "open_prs": len(open_prs),
            "closed_prs": len(closed_prs),
            "total_prs": len(pulls),
            "releases_count": len(releases),
            "branches_count": len(branches),
            "tags_count": len(tags),
            "contributors_count": len(contributors),
        },
        "activity": {
            "contributors": [
                {
                    "login": c.get("login"),
                    "contributions": c.get("contributions", 0),
                }
                for c in contributors[:10]
                if isinstance(c, dict)
            ],
            "recent_releases": [
                {
                    "tag_name": r.get("tag_name"),
                    "name": r.get("name"),
                    "published_at": r.get("published_at"),
                }
                for r in releases[:5]
                if isinstance(r, dict)
            ],
            "languages": languages,
            "topics": (
                topics.get("names", []) if isinstance(topics, dict) else []
            ),
        },
        "community": {
            "health_percentage": community.get("health_percentage"),
        },
        "readme": {
            "exists": bool(readme),
            "size": readme.get("size", 0),
            "download_url": readme.get("download_url"),
        },
    }
