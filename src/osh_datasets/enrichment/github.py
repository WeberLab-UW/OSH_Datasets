"""Enrich database projects with scraped GitHub repository metadata.

Reads ``data/raw/github/github_repos.jsonl`` (produced by
:class:`~osh_datasets.scrapers.github.GitHubScraper`) and updates
matching projects with repo metrics, contributors, topics, licenses,
and BOM file paths.
"""

import sqlite3
from pathlib import Path

import orjson

from osh_datasets.config import DB_PATH, RAW_DIR, get_logger
from osh_datasets.db import (
    insert_bom_file_path,
    insert_contributor,
    insert_license,
    insert_tags,
    transaction,
    upsert_repo_metrics,
)

logger = get_logger(__name__)


def _normalize_github_url(owner: str, repo: str) -> str:
    """Build a canonical GitHub URL for matching.

    Args:
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Lowercase canonical URL.
    """
    return f"https://github.com/{owner}/{repo}".lower()


def _find_project_id(
    conn: sqlite3.Connection,
    owner: str,
    repo: str,
) -> int | None:
    """Find the project ID matching a GitHub owner/repo.

    Searches ``repo_url`` for any project containing the
    ``github.com/owner/repo`` pattern.

    Args:
        conn: Active database connection.
        owner: Repository owner.
        repo: Repository name.

    Returns:
        The ``projects.id`` or None if not found.
    """
    pattern = f"%github.com/{owner}/{repo}%"
    row = conn.execute(
        "SELECT id FROM projects WHERE repo_url LIKE ? LIMIT 1",
        (pattern,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    return None


def _safe_int(val: object) -> int | None:
    """Safely convert a value to int.

    Args:
        val: Value to convert.

    Returns:
        Integer value or None.
    """
    if val is None:
        return None
    try:
        return int(str(val))
    except (ValueError, TypeError):
        return None


def enrich_from_github(
    db_path: Path = DB_PATH,
    json_path: Path | None = None,
) -> int:
    """Update database projects with scraped GitHub metadata.

    Args:
        db_path: Path to the SQLite database.
        json_path: Path to ``github_repos.jsonl``. Defaults to
            ``data/raw/github/github_repos.jsonl``.

    Returns:
        Number of projects enriched.
    """
    if json_path is None:
        json_path = RAW_DIR / "github" / "github_repos.jsonl"

    if not json_path.exists():
        logger.warning("No GitHub data at %s, skipping enrichment", json_path)
        return 0

    records: list[dict[str, object]] = []
    with open(json_path, "rb") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                item = orjson.loads(raw_line)
            except orjson.JSONDecodeError:
                logger.warning("Skipping corrupt JSONL line in %s", json_path)
                continue
            if isinstance(item, dict):
                records.append(item)

    if not records:
        logger.info("Empty GitHub data file, nothing to enrich")
        return 0

    logger.info("Enriching from %d GitHub repo records", len(records))
    enriched = 0

    with transaction(db_path) as conn:
        for record in records:
            repo_info = record.get("repository")
            if not isinstance(repo_info, dict):
                continue

            owner = str(repo_info.get("owner", ""))
            repo_name = str(repo_info.get("name", ""))
            if not owner or not repo_name:
                continue

            project_id = _find_project_id(conn, owner, repo_name)
            if project_id is None:
                logger.debug(
                    "No project found for %s/%s", owner, repo_name
                )
                continue

            # Update project timestamps and description if missing
            description = str(repo_info.get("description") or "").strip()
            created_at = str(repo_info.get("created_at") or "").strip()
            updated_at = str(repo_info.get("updated_at") or "").strip()
            if description or created_at or updated_at:
                conn.execute(
                    """\
                    UPDATE projects SET
                        description = COALESCE(
                            projects.description, ?
                        ),
                        created_at = COALESCE(
                            projects.created_at, ?
                        ),
                        updated_at = COALESCE(
                            projects.updated_at, ?
                        )
                    WHERE id = ?
                    """,
                    (
                        description or None,
                        created_at or None,
                        updated_at or None,
                        project_id,
                    ),
                )

            # Repo metrics
            metrics = record.get("metrics")
            community = record.get("community")
            readme = record.get("readme")
            bom = record.get("bom")
            file_tree = record.get("file_tree")

            if not isinstance(metrics, dict):
                metrics = {}
            if not isinstance(community, dict):
                community = {}
            if not isinstance(readme, dict):
                readme = {}
            if not isinstance(bom, dict):
                bom = {}
            if not isinstance(file_tree, dict):
                file_tree = {}

            repo_url = f"https://github.com/{owner}/{repo_name}"

            upsert_repo_metrics(
                conn,
                project_id,
                repo_url,
                stars=_safe_int(metrics.get("stars")),
                forks=_safe_int(metrics.get("forks")),
                watchers=_safe_int(metrics.get("watchers")),
                open_issues=_safe_int(metrics.get("open_issues")),
                total_issues=_safe_int(metrics.get("total_issues")),
                open_prs=_safe_int(metrics.get("open_prs")),
                closed_prs=_safe_int(metrics.get("closed_prs")),
                total_prs=_safe_int(metrics.get("total_prs")),
                releases_count=_safe_int(metrics.get("releases_count")),
                branches_count=_safe_int(metrics.get("branches_count")),
                tags_count=_safe_int(metrics.get("tags_count")),
                contributors_count=_safe_int(
                    metrics.get("contributors_count")
                ),
                community_health=_safe_int(
                    community.get("health_percentage")
                ),
                primary_language=str(
                    repo_info.get("language") or ""
                ) or None,
                has_bom=bool(bom.get("has_bom")),
                has_readme=bool(readme.get("exists")),
                repo_size_kb=_safe_int(repo_info.get("size")),
                total_files=_safe_int(file_tree.get("total_files")),
                archived=bool(repo_info.get("archived")),
                pushed_at=str(
                    repo_info.get("pushed_at") or ""
                ) or None,
            )

            # BOM file paths
            bom_files = bom.get("bom_files")
            if isinstance(bom_files, list):
                for fp in bom_files:
                    if isinstance(fp, str) and fp:
                        insert_bom_file_path(
                            conn, project_id, repo_url, fp,
                        )

            # License from GitHub
            gh_license = str(repo_info.get("license") or "").strip()
            if gh_license:
                insert_license(conn, project_id, "software", gh_license)

            # Topics -> tags
            activity = record.get("activity")
            if isinstance(activity, dict):
                topics = activity.get("topics")
                if isinstance(topics, list) and topics:
                    insert_tags(
                        conn,
                        project_id,
                        [str(t) for t in topics if t],
                    )

                # Contributors
                contribs = activity.get("contributors")
                if isinstance(contribs, list):
                    for c in contribs:
                        if isinstance(c, dict):
                            login = str(c.get("login") or "").strip()
                            contributions = _safe_int(
                                c.get("contributions")
                            )
                            if login:
                                insert_contributor(
                                    conn,
                                    project_id,
                                    name=login,
                                    role=(
                                        f"{contributions} commits"
                                        if contributions
                                        else None
                                    ),
                                )

            enriched += 1

    logger.info("Enriched %d/%d projects", enriched, len(records))
    return enriched


if __name__ == "__main__":
    count = enrich_from_github()
    print(f"Enriched {count} projects with GitHub metadata")
