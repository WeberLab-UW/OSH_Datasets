"""Download, parse, and load BOM files detected in GitHub repositories.

Reads unprocessed rows from ``bom_file_paths``, downloads the raw file
from ``raw.githubusercontent.com``, parses it into structured component
data, and inserts rows into ``bom_components``.

Usage::

    uv run python -m osh_datasets.enrichment.bom_files
    uv run python -m osh_datasets.enrichment.bom_files --limit 50
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import orjson
import polars as pl
import requests

from osh_datasets.bom_parser import (
    infer_quantity,
    parse_bom_file,
    safe_float_str,
)
from osh_datasets.config import DB_PATH, RAW_DIR, get_logger
from osh_datasets.db import insert_bom_component, open_connection
from osh_datasets.http import build_session

logger = get_logger(__name__)

_RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
_CACHE_DIR = RAW_DIR / "github" / "bom_cache"


def _build_branch_lookup(jsonl_path: Path) -> dict[str, str]:
    """Build owner/repo -> default_branch lookup from scraped JSONL.

    Args:
        jsonl_path: Path to ``github_repos.jsonl``.

    Returns:
        Mapping of ``"owner/repo"`` (lowercased) to default branch name.
    """
    lookup: dict[str, str] = {}
    if not jsonl_path.exists():
        return lookup
    with open(jsonl_path, "rb") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            repo = record.get("repository")
            if not isinstance(repo, dict):
                continue
            owner = str(repo.get("owner", "")).strip()
            name = str(repo.get("name", "")).strip()
            branch = str(repo.get("default_branch", "main")).strip()
            if owner and name:
                lookup[f"{owner}/{name}".lower()] = branch or "main"
    return lookup


def _parse_repo_url(repo_url: str) -> tuple[str, str] | None:
    """Extract owner and repo name from a GitHub URL.

    Args:
        repo_url: GitHub URL (e.g. ``https://github.com/owner/repo``).

    Returns:
        Tuple of (owner, repo) or None if not a GitHub URL.
    """
    parts = repo_url.rstrip("/").split("/")
    try:
        idx = parts.index("github.com")
        if idx + 2 < len(parts):
            return parts[idx + 1], parts[idx + 2]
    except ValueError:
        pass
    return None


def _download_file(
    session: requests.Session,
    owner: str,
    repo: str,
    branch: str,
    file_path: str,
) -> bytes | None:
    """Download a file from raw.githubusercontent.com with disk cache.

    Args:
        session: HTTP session with retry logic.
        owner: Repository owner.
        repo: Repository name.
        branch: Branch name.
        file_path: Relative path within the repo.

    Returns:
        File bytes, or None on failure.
    """
    cache_path = _CACHE_DIR / owner / repo / file_path
    if cache_path.exists():
        return cache_path.read_bytes()

    url = _RAW_URL.format(
        owner=owner, repo=repo, branch=branch, path=file_path,
    )
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.debug("Failed to download %s/%s/%s: %s", owner, repo, file_path, exc)
        return None

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(resp.content)
    return resp.content


def _get_unprocessed_rows(
    conn: sqlite3.Connection,
    limit: int | None = None,
) -> list[tuple[int, int, str, str]]:
    """Fetch bom_file_paths rows that have not been processed yet.

    Args:
        conn: Active database connection.
        limit: Maximum rows to fetch, or None for all.

    Returns:
        List of (id, project_id, repo_url, file_path) tuples.
    """
    query = (
        "SELECT id, project_id, repo_url, file_path "
        "FROM bom_file_paths "
        "WHERE processed = 0 AND repo_url != ''"
    )
    if limit is not None:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    return [(int(r[0]), int(r[1]), str(r[2]), str(r[3])) for r in rows]


def enrich_bom_files(
    db_path: Path = DB_PATH,
    jsonl_path: Path | None = None,
    limit: int | None = None,
) -> int:
    """Download and parse BOM files, inserting components into the DB.

    Args:
        db_path: Path to the SQLite database.
        jsonl_path: Path to ``github_repos.jsonl`` for branch lookup.
        limit: Maximum number of BOM files to process.

    Returns:
        Total number of components inserted.
    """
    if jsonl_path is None:
        jsonl_path = RAW_DIR / "github" / "github_repos.jsonl"

    branch_lookup = _build_branch_lookup(jsonl_path)
    logger.info(
        "Branch lookup: %d repos", len(branch_lookup),
    )

    conn = open_connection(db_path)
    rows = _get_unprocessed_rows(conn, limit)
    conn.close()

    if not rows:
        logger.info("No unprocessed BOM file paths")
        return 0

    logger.info("Processing %d BOM files", len(rows))
    session = build_session(retries=2, backoff_factor=0.5)
    total_components = 0

    for row_id, project_id, repo_url, file_path in rows:
        parsed = _parse_repo_url(repo_url)
        if parsed is None:
            _mark_processed(db_path, row_id, 0)
            continue

        owner, repo = parsed
        key = f"{owner}/{repo}".lower()
        branch = branch_lookup.get(key, "main")

        data = _download_file(session, owner, repo, branch, file_path)
        if data is None:
            _mark_processed(db_path, row_id, 0)
            continue

        df = parse_bom_file(data, file_path)
        if df is None:
            _mark_processed(db_path, row_id, 0)
            continue

        component_count = _insert_components(
            db_path, project_id, df,
        )
        _mark_processed(db_path, row_id, component_count)
        total_components += component_count

        if component_count > 0:
            logger.info(
                "  %s/%s/%s: %d components",
                owner, repo, file_path, component_count,
            )

    logger.info(
        "Done: %d components from %d files", total_components, len(rows),
    )
    return total_components


def _insert_components(
    db_path: Path,
    project_id: int,
    df: pl.DataFrame,
) -> int:
    """Insert parsed BOM components into the database.

    Args:
        db_path: Path to the SQLite database.
        project_id: Project to link components to.
        df: Normalized BOM dataframe.

    Returns:
        Number of components inserted.
    """
    conn = open_connection(db_path)
    count = 0
    try:
        for row in df.iter_rows(named=True):
            insert_bom_component(
                conn,
                project_id,
                reference=row.get("reference"),
                component_name=row.get("component_name"),
                quantity=infer_quantity(
                    row.get("reference"), row.get("quantity_raw"),
                ),
                unit_cost=safe_float_str(row.get("unit_cost_raw")),
                manufacturer=row.get("manufacturer"),
                part_number=row.get("part_number"),
                footprint=row.get("footprint"),
            )
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return count


def _mark_processed(
    db_path: Path,
    row_id: int,
    component_count: int,
) -> None:
    """Mark a bom_file_paths row as processed.

    Args:
        db_path: Path to the SQLite database.
        row_id: The ``bom_file_paths.id``.
        component_count: Number of components extracted.
    """
    conn = open_connection(db_path)
    try:
        conn.execute(
            "UPDATE bom_file_paths "
            "SET processed = 1, component_count = ? "
            "WHERE id = ?",
            (component_count, row_id),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download and parse BOM files from GitHub repos",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max BOM files to process",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to SQLite database",
    )
    args = parser.parse_args()
    db = Path(args.db) if args.db else DB_PATH
    total = enrich_bom_files(db_path=db, limit=args.limit)
    print(f"Inserted {total} BOM components")
