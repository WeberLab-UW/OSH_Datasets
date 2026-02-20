"""Fetch comprehensive GitHub repository metadata.

Consolidates the legacy ``gh_data_extraction.py``, ``gh_opt.py``,
``repo_readme_tree_processer.py``, and ``gh_repometrics.py`` into a
single scraper using :class:`~osh_datasets.token_manager.TokenManager`.

Includes file-tree scanning and BOM (Bill of Materials) detection.
"""

import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
import requests

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.scrapers.base import BaseScraper
from osh_datasets.token_manager import TokenManager

logger = get_logger(__name__)

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "OSH-Datasets-GitHub-Scraper/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Patterns that indicate a BOM file (case-insensitive matching)
_BOM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(^|/)bom[_\-.]", re.IGNORECASE),
    re.compile(r"(^|/)bill[_\-]of[_\-]materials", re.IGNORECASE),
    re.compile(r"(^|/)parts[_\-]?list", re.IGNORECASE),
    re.compile(r"(^|/)components\.(csv|tsv|xlsx?|json|xml)", re.IGNORECASE),
    re.compile(r"[_\-]bom\.(csv|tsv|xlsx?|json|xml)$", re.IGNORECASE),
]

# File extensions that could be BOM data files
_BOM_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".xlsx", ".xls", ".json", ".xml", ".yaml", ".yml",
    ".ods",
})


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


def _is_bom_file(path: str) -> bool:
    """Check whether a file path looks like a BOM file.

    Args:
        path: Relative file path from the repository root.

    Returns:
        True if the path matches a BOM naming pattern.
    """
    lower = path.lower()
    # Must have a data-file extension
    if not any(lower.endswith(ext) for ext in _BOM_EXTENSIONS):
        return False
    return any(pat.search(path) for pat in _BOM_PATTERNS)


def _detect_bom_files(tree_entries: list[dict[str, str]]) -> list[str]:
    """Scan a repo file tree for BOM candidates.

    Args:
        tree_entries: List of tree entry dicts from the GitHub API.

    Returns:
        Sorted list of BOM file paths found in the tree.
    """
    bom_paths: list[str] = []
    for entry in tree_entries:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        if _is_bom_file(path):
            bom_paths.append(path)
    bom_paths.sort()
    return bom_paths


def generate_repo_urls(db_path: Path = DB_PATH) -> list[str]:
    """Extract unique GitHub repo URLs from the database.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Deduplicated list of GitHub repo URLs.
    """
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT DISTINCT repo_url FROM projects "
        "WHERE repo_url LIKE '%github.com%'"
    ).fetchall()
    conn.close()

    seen: set[tuple[str, str]] = set()
    urls: list[str] = []
    for (raw_url,) in rows:
        # Some fields contain multiple comma-separated URLs
        for url in raw_url.split(","):
            url = url.strip()
            parsed = _extract_owner_repo(url)
            if parsed and parsed not in seen:
                seen.add(parsed)
                urls.append(f"https://github.com/{parsed[0]}/{parsed[1]}")
    return urls


class GitHubScraper(BaseScraper):
    """Fetch metadata for GitHub repositories.

    Reads repo URLs from ``data/raw/github/repos.txt`` (one per line).
    If no file exists, can auto-generate URLs from the database via
    :func:`generate_repo_urls`.

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
            logger.info(
                "No repos.txt found; generating from database"
            )
            urls = generate_repo_urls()
            if not urls:
                logger.warning("No GitHub URLs in database, skipping")
                out = self.output_dir / "github_repos.json"
                out.write_bytes(orjson.dumps([]))
                return out
            url_file.write_text("\n".join(urls) + "\n")
            logger.info("Wrote %d URLs to %s", len(urls), url_file)

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

    default_branch = repo_data.get("default_branch", "main")

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
        "tree": f"{base}/git/trees/{default_branch}?recursive=1",
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

    def _as_list(val: object) -> list[object]:
        return val if isinstance(val, list) else []

    def _as_dict(val: object) -> dict[str, object]:
        return val if isinstance(val, dict) else {}

    contributors = _as_list(raw.get("contributors"))
    issues = _as_list(raw.get("issues"))
    pulls = _as_list(raw.get("pulls"))
    releases = _as_list(raw.get("releases"))
    branches = _as_list(raw.get("branches"))
    tags = _as_list(raw.get("tags"))
    community = _as_dict(raw.get("community"))
    readme = _as_dict(raw.get("readme"))
    languages = _as_dict(raw.get("languages"))
    topics = _as_dict(raw.get("topics"))
    tree_data = _as_dict(raw.get("tree"))

    actual_issues = [
        i for i in issues
        if isinstance(i, dict) and "pull_request" not in i
    ]
    open_prs = [
        p for p in pulls
        if isinstance(p, dict) and p.get("state") == "open"
    ]
    closed_prs = [
        p for p in pulls
        if isinstance(p, dict) and p.get("state") == "closed"
    ]

    lic = repo_data.get("license")

    # File tree and BOM detection
    tree_entries: list[dict[str, str]] = []
    raw_tree = tree_data.get("tree")
    if isinstance(raw_tree, list):
        tree_entries = [
            e for e in raw_tree
            if isinstance(e, dict) and isinstance(e.get("path"), str)
        ]
    bom_files = _detect_bom_files(tree_entries)

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
            "default_branch": default_branch,
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
        "bom": {
            "has_bom": len(bom_files) > 0,
            "bom_files": bom_files,
        },
        "file_tree": {
            "total_files": sum(
                1 for e in tree_entries if e.get("type") == "blob"
            ),
            "truncated": tree_data.get("truncated", False),
        },
    }
