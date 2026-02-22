"""One-time migration: add repo_url to repo_metrics and bom_file_paths.

Uses rename-recreate-copy to preserve all existing data while changing
UNIQUE constraints. Then backfills repo_url and inserts missing rows
from the raw JSONL.

Usage: uv run python scripts/migrate_repo_url.py
"""

import sqlite3
from pathlib import Path

import orjson

from osh_datasets.config import DB_PATH, get_logger

logger = get_logger(__name__)

RAW_JSONL = Path("data/raw/github/github_repos_raw.jsonl")


def _migrate_repo_metrics(conn: sqlite3.Connection) -> None:
    """Add repo_url column to repo_metrics with new UNIQUE constraint."""
    conn.execute("ALTER TABLE repo_metrics RENAME TO _repo_metrics_old")
    conn.execute("""\
        CREATE TABLE repo_metrics (
            id                  INTEGER PRIMARY KEY,
            project_id          INTEGER NOT NULL REFERENCES projects(id),
            repo_url            TEXT    NOT NULL DEFAULT '',
            stars               INTEGER,
            forks               INTEGER,
            watchers            INTEGER,
            open_issues         INTEGER,
            total_issues        INTEGER,
            open_prs            INTEGER,
            closed_prs          INTEGER,
            total_prs           INTEGER,
            releases_count      INTEGER,
            branches_count      INTEGER,
            tags_count          INTEGER,
            contributors_count  INTEGER,
            community_health    INTEGER,
            primary_language    TEXT,
            has_bom             INTEGER,
            has_readme          INTEGER,
            repo_size_kb        INTEGER,
            total_files         INTEGER,
            archived            INTEGER,
            pushed_at           TEXT,
            UNIQUE(project_id, repo_url)
        )
    """)
    conn.execute("""\
        INSERT INTO repo_metrics (
            id, project_id, repo_url, stars, forks, watchers,
            open_issues, total_issues, open_prs, closed_prs, total_prs,
            releases_count, branches_count, tags_count, contributors_count,
            community_health, primary_language, has_bom, has_readme,
            repo_size_kb, total_files, archived, pushed_at
        )
        SELECT
            id, project_id, '', stars, forks, watchers,
            open_issues, total_issues, open_prs, closed_prs, total_prs,
            releases_count, branches_count, tags_count, contributors_count,
            community_health, primary_language, has_bom, has_readme,
            repo_size_kb, total_files, archived, pushed_at
        FROM _repo_metrics_old
    """)
    count = conn.execute(
        "SELECT COUNT(*) FROM repo_metrics"
    ).fetchone()[0]
    conn.execute("DROP TABLE _repo_metrics_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repo_metrics "
        "ON repo_metrics(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repo_metrics_url "
        "ON repo_metrics(repo_url)"
    )
    logger.info("Migrated repo_metrics: %d rows preserved", count)


def _migrate_bom_file_paths(conn: sqlite3.Connection) -> None:
    """Add repo_url column to bom_file_paths with new UNIQUE constraint."""
    conn.execute(
        "ALTER TABLE bom_file_paths RENAME TO _bom_file_paths_old"
    )
    conn.execute("""\
        CREATE TABLE bom_file_paths (
            id            INTEGER PRIMARY KEY,
            project_id    INTEGER NOT NULL REFERENCES projects(id),
            repo_url      TEXT    NOT NULL DEFAULT '',
            file_path     TEXT    NOT NULL,
            UNIQUE(project_id, repo_url, file_path)
        )
    """)
    conn.execute("""\
        INSERT INTO bom_file_paths (id, project_id, repo_url, file_path)
        SELECT id, project_id, '', file_path
        FROM _bom_file_paths_old
    """)
    count = conn.execute(
        "SELECT COUNT(*) FROM bom_file_paths"
    ).fetchone()[0]
    conn.execute("DROP TABLE _bom_file_paths_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_paths_proj "
        "ON bom_file_paths(project_id)"
    )
    logger.info("Migrated bom_file_paths: %d rows preserved", count)


def _migrate_contributors(conn: sqlite3.Connection) -> None:
    """Add UNIQUE(project_id, name) to contributors, dedup existing."""
    conn.execute(
        "ALTER TABLE contributors RENAME TO _contributors_old"
    )
    conn.execute("""\
        CREATE TABLE contributors (
            id            INTEGER PRIMARY KEY,
            project_id    INTEGER NOT NULL REFERENCES projects(id),
            name          TEXT    NOT NULL,
            role          TEXT,
            permission    TEXT,
            UNIQUE(project_id, name)
        )
    """)
    # Keep the row with the highest id (latest insert) per (project_id, name)
    conn.execute("""\
        INSERT INTO contributors (project_id, name, role, permission)
        SELECT project_id, name, role, permission
        FROM _contributors_old
        WHERE id IN (
            SELECT MAX(id) FROM _contributors_old
            GROUP BY project_id, name
        )
    """)
    old_count = conn.execute(
        "SELECT COUNT(*) FROM _contributors_old"
    ).fetchone()[0]
    new_count = conn.execute(
        "SELECT COUNT(*) FROM contributors"
    ).fetchone()[0]
    conn.execute("DROP TABLE _contributors_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contribs_proj "
        "ON contributors(project_id)"
    )
    logger.info(
        "Migrated contributors: %d -> %d rows (deduped %d)",
        old_count, new_count, old_count - new_count,
    )


def _find_project_id(
    conn: sqlite3.Connection, owner: str, repo: str,
) -> int | None:
    """Find the project ID matching a GitHub owner/repo."""
    pattern = f"%github.com/{owner}/{repo}%"
    row = conn.execute(
        "SELECT id FROM projects WHERE repo_url LIKE ? LIMIT 1",
        (pattern,),
    ).fetchone()
    return int(row[0]) if row is not None else None


def _backfill_from_jsonl(conn: sqlite3.Connection) -> None:
    """Backfill repo_url on existing rows and insert missing repos.

    Reads every record in the raw JSONL. For each:
    - UPDATE existing repo_metrics rows that have repo_url=''
    - INSERT new rows for repos that were previously overwritten
    """
    if not RAW_JSONL.exists():
        logger.warning("No raw JSONL at %s, skipping backfill", RAW_JSONL)
        return

    updated = 0
    inserted = 0
    skipped = 0

    with open(RAW_JSONL, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            repo_info = item.get("repository")
            if not isinstance(repo_info, dict):
                continue

            owner = str(repo_info.get("owner", ""))
            repo_name = str(repo_info.get("name", ""))
            if not owner or not repo_name:
                continue

            project_id = _find_project_id(conn, owner, repo_name)
            if project_id is None:
                skipped += 1
                continue

            repo_url = f"https://github.com/{owner}/{repo_name}"

            # Check if this project already has a row with empty repo_url
            existing = conn.execute(
                "SELECT id FROM repo_metrics "
                "WHERE project_id = ? AND repo_url = ''",
                (project_id,),
            ).fetchone()

            if existing:
                # Backfill the repo_url on the existing row
                conn.execute(
                    "UPDATE repo_metrics SET repo_url = ? WHERE id = ?",
                    (repo_url, existing[0]),
                )
                updated += 1
            else:
                # Check if this specific repo_url already exists
                has_url = conn.execute(
                    "SELECT 1 FROM repo_metrics "
                    "WHERE project_id = ? AND repo_url = ?",
                    (project_id, repo_url),
                ).fetchone()
                if has_url:
                    continue

                # Insert the missing second/third repo
                metrics = item.get("metrics") or {}
                community = item.get("community") or {}
                readme = item.get("readme") or {}
                bom = item.get("bom") or {}
                file_tree = item.get("file_tree") or {}

                def safe_int(val: object) -> int | None:
                    if val is None:
                        return None
                    try:
                        return int(str(val))
                    except (ValueError, TypeError):
                        return None

                conn.execute(
                    """\
                    INSERT INTO repo_metrics (
                        project_id, repo_url, stars, forks, watchers,
                        open_issues, total_issues, open_prs, closed_prs,
                        total_prs, releases_count, branches_count,
                        tags_count, contributors_count, community_health,
                        primary_language, has_bom, has_readme,
                        repo_size_kb, total_files, archived, pushed_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        project_id, repo_url,
                        safe_int(metrics.get("stars")),
                        safe_int(metrics.get("forks")),
                        safe_int(metrics.get("watchers")),
                        safe_int(metrics.get("open_issues")),
                        safe_int(metrics.get("total_issues")),
                        safe_int(metrics.get("open_prs")),
                        safe_int(metrics.get("closed_prs")),
                        safe_int(metrics.get("total_prs")),
                        safe_int(metrics.get("releases_count")),
                        safe_int(metrics.get("branches_count")),
                        safe_int(metrics.get("tags_count")),
                        safe_int(metrics.get("contributors_count")),
                        safe_int(
                            community.get("health_percentage")
                            if isinstance(community, dict)
                            else None
                        ),
                        str(repo_info.get("language") or "") or None,
                        int(bool(bom.get("has_bom")))
                        if isinstance(bom, dict) else 0,
                        int(bool(readme.get("exists")))
                        if isinstance(readme, dict) else 0,
                        safe_int(repo_info.get("size")),
                        safe_int(file_tree.get("total_files"))
                        if isinstance(file_tree, dict) else None,
                        int(bool(repo_info.get("archived"))),
                        str(repo_info.get("pushed_at") or "") or None,
                    ),
                )
                inserted += 1

            # Also backfill bom_file_paths
            bom = item.get("bom")
            if isinstance(bom, dict):
                bom_files = bom.get("bom_files")
                if isinstance(bom_files, list):
                    for fp in bom_files:
                        if isinstance(fp, str) and fp:
                            conn.execute(
                                "UPDATE bom_file_paths "
                                "SET repo_url = ? "
                                "WHERE project_id = ? "
                                "AND file_path = ? "
                                "AND repo_url = ''",
                                (repo_url, project_id, fp),
                            )

    logger.info(
        "Backfill: %d updated, %d inserted, %d skipped (no project)",
        updated, inserted, skipped,
    )


def migrate(db_path: Path = DB_PATH) -> None:
    """Run the full migration."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        conn.execute("BEGIN")
        _migrate_repo_metrics(conn)
        _migrate_bom_file_paths(conn)
        _migrate_contributors(conn)
        _backfill_from_jsonl(conn)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        logger.error("Migration failed, rolled back")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    logger.info("Migration complete")


if __name__ == "__main__":
    migrate()
    # Verify
    conn = sqlite3.connect(str(DB_PATH))
    rm = conn.execute("SELECT COUNT(*) FROM repo_metrics").fetchone()[0]
    bf = conn.execute("SELECT COUNT(*) FROM bom_file_paths").fetchone()[0]
    ct = conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0]

    # Check project 1 (Polymorphic Hardware, 2 repos)
    p1 = conn.execute(
        "SELECT repo_url, stars FROM repo_metrics WHERE project_id = 1"
    ).fetchall()

    print(f"repo_metrics:   {rm} rows")
    print(f"bom_file_paths: {bf} rows")
    print(f"contributors:   {ct} rows")
    print(f"Project 1 repos: {len(p1)}")
    for row in p1:
        print(f"  {row[0]}: stars={row[1]}")

    conn.close()
