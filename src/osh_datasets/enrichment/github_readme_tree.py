"""Fetch README content and file trees from GitHub for LLM evaluation.

Populates ``readme_contents`` and ``repo_file_trees`` tables for all
projects with a GitHub ``repo_url`` that have not yet been fetched.

Uses the existing :class:`~osh_datasets.token_manager.TokenManager`
with ``GITHUB_TOKEN`` for authenticated API access (5,000 req/hr).

Usage::

    uv run python -m osh_datasets.enrichment.github_readme_tree --limit 100
"""

import argparse
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import (
    insert_repo_file_tree_entries,
    open_connection,
    upsert_readme_content,
)
from osh_datasets.token_manager import TokenManager

logger = get_logger(__name__)

_API_BASE = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "OSH-Datasets-README-Fetcher/1.0",
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
    m = re.search(
        r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
        url,
        re.IGNORECASE,
    )
    if m:
        repo = m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        if repo:
            return m.group(1), repo
    return None


def _get_json(
    tm: TokenManager,
    url: str,
    accept: str | None = None,
) -> dict[str, object] | list[object] | None:
    """GET with token rotation and rate-limit handling.

    Args:
        tm: Token manager for authentication.
        url: Full API URL.
        accept: Optional Accept header override.

    Returns:
        Parsed JSON response, or None on failure/404.
    """
    for attempt in range(3):
        try:
            headers = {**_HEADERS, "Authorization": f"Bearer {tm.current}"}
            if accept:
                headers["Accept"] = accept
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code == 200:
                return resp.json()  # type: ignore[no-any-return]
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                remaining = int(
                    resp.headers.get("X-RateLimit-Remaining", "0")
                )
                if remaining == 0 or "rate limit" in resp.text.lower():
                    tm.rotate()
                    reset_ts = int(
                        resp.headers.get("X-RateLimit-Reset", "0")
                    )
                    if reset_ts > 0:
                        wait = max(reset_ts - int(time.time()), 0) + 5
                        logger.info(
                            "Rate limited, waiting %d seconds", wait
                        )
                        time.sleep(wait)
                    continue
            if resp.status_code == 401:
                tm.rotate()
                continue
            logger.warning("HTTP %d for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            logger.debug("Request error (attempt %d): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)
    logger.error("All retries exhausted for %s", url)
    return None


def _get_raw_text(
    tm: TokenManager,
    url: str,
) -> str | None:
    """GET raw text content with token rotation.

    Args:
        tm: Token manager for authentication.
        url: Full API URL.

    Returns:
        Raw text response, or None on failure/404.
    """
    for attempt in range(3):
        try:
            headers = {
                **_HEADERS,
                "Authorization": f"Bearer {tm.current}",
                "Accept": "application/vnd.github.raw+json",
            }
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                remaining = int(
                    resp.headers.get("X-RateLimit-Remaining", "0")
                )
                if remaining == 0 or "rate limit" in resp.text.lower():
                    tm.rotate()
                    reset_ts = int(
                        resp.headers.get("X-RateLimit-Reset", "0")
                    )
                    if reset_ts > 0:
                        wait = max(reset_ts - int(time.time()), 0) + 5
                        logger.info(
                            "Rate limited, waiting %d seconds", wait
                        )
                        time.sleep(wait)
                    continue
            if resp.status_code == 401:
                tm.rotate()
                continue
            logger.warning("HTTP %d for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            logger.debug("Request error (attempt %d): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2**attempt)
    logger.error("All retries exhausted for %s", url)
    return None


def _fetch_default_branch(
    tm: TokenManager,
    owner: str,
    repo: str,
) -> str:
    """Fetch the default branch name for a repository.

    Args:
        tm: Token manager for authentication.
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Default branch name, or ``"main"`` as fallback.
    """
    url = f"{_API_BASE}/repos/{owner}/{repo}"
    data = _get_json(tm, url)
    if isinstance(data, dict):
        branch = data.get("default_branch")
        if isinstance(branch, str) and branch:
            return branch
    return "main"


def _fetch_readme(
    tm: TokenManager,
    owner: str,
    repo: str,
) -> tuple[str | None, int]:
    """Fetch raw README content from a repository.

    Args:
        tm: Token manager for authentication.
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Tuple of ``(content, size_bytes)``. Content is None if no
        README exists.
    """
    url = f"{_API_BASE}/repos/{owner}/{repo}/readme"
    content = _get_raw_text(tm, url)
    if content is None:
        return None, 0
    return content, len(content.encode("utf-8"))


def _fetch_file_tree(
    tm: TokenManager,
    owner: str,
    repo: str,
    branch: str,
) -> list[tuple[str, str, int | None]]:
    """Fetch the full recursive file tree for a repository.

    Args:
        tm: Token manager for authentication.
        owner: Repository owner.
        repo: Repository name.
        branch: Branch name (e.g. ``"main"``).

    Returns:
        List of ``(path, type, size)`` tuples. Type is ``'blob'``
        or ``'tree'``. Size may be None for tree entries.
    """
    url = (
        f"{_API_BASE}/repos/{owner}/{repo}"
        f"/git/trees/{branch}?recursive=1"
    )
    data = _get_json(tm, url)
    if not isinstance(data, dict):
        return []

    tree = data.get("tree")
    if not isinstance(tree, list):
        return []

    entries: list[tuple[str, str, int | None]] = []
    for item in tree:
        if not isinstance(item, dict):
            continue
        path = item.get("path", "")
        ftype = item.get("type", "blob")
        size = item.get("size")
        if isinstance(size, int):
            entries.append((path, ftype, size))
        else:
            entries.append((path, ftype, None))

    if data.get("truncated"):
        logger.warning(
            "%s/%s tree truncated (>100k entries)", owner, repo
        )

    return entries


def fetch_readme_and_trees(
    db_path: Path = DB_PATH,
    limit: int = 0,
) -> int:
    """Fetch README content and file trees for GitHub-linked projects.

    Queries projects with a GitHub ``repo_url`` that are not yet in
    ``readme_contents``, fetches their README and file tree, and
    stores results in the database.

    Args:
        db_path: Path to the SQLite database file.
        limit: Maximum number of projects to fetch. 0 = all.

    Returns:
        Number of projects successfully fetched.
    """
    tm = TokenManager(env_var="GITHUB_TOKEN")
    conn = open_connection(db_path)

    query = """\
        SELECT p.id, p.repo_url
        FROM projects p
        WHERE p.repo_url LIKE '%github.com%'
          AND NOT EXISTS (
              SELECT 1 FROM readme_contents rc
              WHERE rc.project_id = p.id
          )
        ORDER BY p.id
    """
    if limit > 0:
        query += f" LIMIT {limit}"

    candidates = conn.execute(query).fetchall()
    conn.close()

    if not candidates:
        logger.info("No new GitHub projects to fetch")
        return 0

    logger.info("Fetching README + tree for %d projects", len(candidates))
    fetched = 0

    for i, row in enumerate(candidates):
        project_id = row[0]
        repo_url = row[1]

        parsed = _extract_owner_repo(repo_url)
        if parsed is None:
            logger.debug("Cannot parse repo URL: %s", repo_url)
            continue

        owner, repo = parsed
        logger.info(
            "[%d/%d] %s/%s (project %d)",
            i + 1, len(candidates), owner, repo, project_id,
        )

        branch = _fetch_default_branch(tm, owner, repo)
        readme_content, size_bytes = _fetch_readme(tm, owner, repo)
        tree_entries = _fetch_file_tree(tm, owner, repo, branch)

        now = datetime.now(UTC).isoformat()
        canonical_url = f"https://github.com/{owner}/{repo}"

        conn = open_connection(db_path)
        try:
            upsert_readme_content(
                conn,
                project_id,
                repo_url=canonical_url,
                content=readme_content,
                size_bytes=size_bytes if readme_content else None,
                fetched_at=now,
            )
            insert_repo_file_tree_entries(conn, project_id, tree_entries)
            conn.commit()
            fetched += 1
        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to store data for %s/%s", owner, repo
            )
        finally:
            conn.close()

        time.sleep(0.5)

    logger.info("Fetched README + tree for %d projects", fetched)
    return fetched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch GitHub README content and file trees"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max projects to fetch (0 = all)",
    )
    args = parser.parse_args()
    count = fetch_readme_and_trees(limit=args.limit)
    print(f"Fetched {count} projects.")
