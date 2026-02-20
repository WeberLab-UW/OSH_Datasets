"""Cross-source deduplication: identify projects that appear in multiple sources.

Matches projects across sources using:
1. Normalized repository URLs (GitHub/GitLab)
2. OSF links (OHX projects that reference OSF repositories)

Results are stored in the ``cross_references`` table.
"""

import re
from collections import defaultdict
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)


def _normalize_repo(url: str) -> str | None:
    """Extract a canonical ``host/owner/repo`` from a URL.

    Args:
        url: Raw repository URL.

    Returns:
        Normalized key like ``github.com/owner/repo``, or None.
    """
    url = url.lower().strip().rstrip("/")
    url = re.sub(r"\.git$", "", url)
    url = re.sub(r"^https?://", "", url)
    m = re.match(r"(github\.com|gitlab\.com)/([^/]+/[^/]+)", url)
    if m:
        return m.group(0)
    return None


def _normalize_osf(url: str) -> str | None:
    """Extract an OSF project key from a URL or DOI.

    Args:
        url: Raw URL that may point to OSF.

    Returns:
        Canonical ``osf.io/<key>`` string, or None.
    """
    url = url.lower().strip().rstrip("/")
    url = url.replace("doi.org/10.17605/osf.io/", "osf.io/")
    m = re.search(r"osf\.io/([a-z0-9]+)", url)
    if m:
        return f"osf.io/{m.group(1)}"
    return None


def find_cross_references(db_path: Path = DB_PATH) -> int:
    """Detect and store cross-source project overlaps.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Number of cross-references inserted.
    """
    conn = open_connection(db_path)

    # Ensure the table exists (for DBs created before the schema update)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cross_references ("
        "  id INTEGER PRIMARY KEY,"
        "  project_id_a INTEGER NOT NULL REFERENCES projects(id),"
        "  project_id_b INTEGER NOT NULL REFERENCES projects(id),"
        "  match_type TEXT NOT NULL,"
        "  confidence REAL,"
        "  UNIQUE(project_id_a, project_id_b)"
        ")"
    )
    conn.execute("DELETE FROM cross_references")

    rows = conn.execute(
        "SELECT id, source, repo_url FROM projects "
        "WHERE repo_url IS NOT NULL AND repo_url != ''"
    ).fetchall()

    # --- Strategy 1: Shared repo URLs ---
    repo_map: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for pid, source, repo_url in rows:
        for url in str(repo_url).split(","):
            norm = _normalize_repo(url.strip())
            if norm:
                repo_map[norm].append((pid, source))

    pairs: list[tuple[int, int, str, float]] = []
    for _repo, projects in repo_map.items():
        cross_source = []
        seen_sources: dict[str, int] = {}
        for pid, source in projects:
            if source not in seen_sources:
                seen_sources[source] = pid
                cross_source.append((pid, source))

        if len(seen_sources) > 1:
            pids = list(seen_sources.values())
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    a, b = min(pids[i], pids[j]), max(pids[i], pids[j])
                    pairs.append((a, b, "repo_url", 1.0))

    # --- Strategy 2: OHX -> OSF links ---
    ohx_rows = conn.execute(
        "SELECT id, repo_url FROM projects "
        "WHERE source = 'ohx' AND repo_url LIKE '%osf.io%'"
    ).fetchall()
    osf_rows = conn.execute(
        "SELECT id, url FROM projects WHERE source = 'osf'"
    ).fetchall()

    osf_by_key: dict[str, int] = {}
    for pid, url in osf_rows:
        if url:
            key = _normalize_osf(url)
            if key:
                osf_by_key[key] = pid

    for ohx_pid, repo_url in ohx_rows:
        for url in str(repo_url).split(","):
            key = _normalize_osf(url.strip())
            if key and key in osf_by_key:
                osf_pid = osf_by_key[key]
                a, b = min(ohx_pid, osf_pid), max(ohx_pid, osf_pid)
                pairs.append((a, b, "osf_link", 0.9))

    # Deduplicate and insert
    unique: dict[tuple[int, int], tuple[str, float]] = {}
    for a, b, mtype, conf in pairs:
        pair_key = (a, b)
        if pair_key not in unique or conf > unique[pair_key][1]:
            unique[pair_key] = (mtype, conf)

    conn.executemany(
        "INSERT OR IGNORE INTO cross_references "
        "(project_id_a, project_id_b, match_type, confidence) "
        "VALUES (?, ?, ?, ?)",
        [(a, b, mt, c) for (a, b), (mt, c) in unique.items()],
    )
    conn.commit()

    count = len(unique)
    logger.info("Inserted %d cross-references", count)

    # Summary
    stats = conn.execute(
        "SELECT match_type, COUNT(*) FROM cross_references GROUP BY match_type"
    ).fetchall()
    for mtype, cnt in stats:
        logger.info("  %s: %d", mtype, cnt)

    # Source pair breakdown
    source_pairs = conn.execute(
        "SELECT pa.source, pb.source, COUNT(*) "
        "FROM cross_references cr "
        "JOIN projects pa ON cr.project_id_a = pa.id "
        "JOIN projects pb ON cr.project_id_b = pb.id "
        "GROUP BY pa.source, pb.source "
        "ORDER BY COUNT(*) DESC"
    ).fetchall()
    logger.info("Source pair breakdown:")
    for sa, sb, cnt in source_pairs:
        logger.info("  %s <-> %s: %d", sa, sb, cnt)

    conn.close()
    return count


if __name__ == "__main__":
    count = find_cross_references()
    print(f"Found {count} cross-references.")
