"""SQLite database schema and connection management."""

import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger

logger = get_logger(__name__)

SCHEMA_SQL = """\
-- Core project table (all sources merge here)
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY,
    source        TEXT    NOT NULL,
    source_id     TEXT,
    name          TEXT    NOT NULL,
    description   TEXT,
    url           TEXT,
    repo_url      TEXT,
    documentation_url TEXT,
    author        TEXT,
    country       TEXT,
    category      TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS licenses (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(id),
    license_type  TEXT    NOT NULL,
    license_name  TEXT    NOT NULL,
    UNIQUE(project_id, license_type)
);

CREATE TABLE IF NOT EXISTS tags (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(id),
    tag           TEXT    NOT NULL,
    UNIQUE(project_id, tag)
);

CREATE TABLE IF NOT EXISTS contributors (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(id),
    name          TEXT    NOT NULL,
    role          TEXT,
    permission    TEXT,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(id),
    metric_name   TEXT    NOT NULL,
    metric_value  INTEGER,
    UNIQUE(project_id, metric_name)
);

CREATE TABLE IF NOT EXISTS bom_components (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    reference       TEXT,
    component_name  TEXT,
    quantity        INTEGER,
    unit_cost       REAL,
    manufacturer    TEXT,
    part_number     TEXT
);

CREATE TABLE IF NOT EXISTS publications (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL REFERENCES projects(id),
    doi               TEXT,
    title             TEXT,
    publication_year  INTEGER,
    journal           TEXT,
    cited_by_count    INTEGER,
    open_access       INTEGER,
    UNIQUE(project_id, doi)
);

CREATE TABLE IF NOT EXISTS cross_references (
    id            INTEGER PRIMARY KEY,
    project_id_a  INTEGER NOT NULL REFERENCES projects(id),
    project_id_b  INTEGER NOT NULL REFERENCES projects(id),
    match_type    TEXT    NOT NULL,
    confidence    REAL,
    UNIQUE(project_id_a, project_id_b)
);

CREATE TABLE IF NOT EXISTS repo_metrics (
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
);

CREATE TABLE IF NOT EXISTS bom_file_paths (
    id            INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(id),
    repo_url      TEXT    NOT NULL DEFAULT '',
    file_path     TEXT    NOT NULL,
    UNIQUE(project_id, repo_url, file_path)
);

CREATE TABLE IF NOT EXISTS component_prices (
    id                INTEGER PRIMARY KEY,
    bom_component_id  INTEGER NOT NULL REFERENCES bom_components(id),
    matched_mpn       TEXT,
    distributor       TEXT,
    unit_price        REAL,
    currency          TEXT    DEFAULT 'USD',
    quantity_break    INTEGER DEFAULT 1,
    price_date        TEXT    NOT NULL,
    price_source      TEXT    NOT NULL,
    UNIQUE(bom_component_id, distributor, quantity_break)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_projects_source ON projects(source);
CREATE INDEX IF NOT EXISTS idx_projects_name   ON projects(name);
CREATE INDEX IF NOT EXISTS idx_projects_repo   ON projects(repo_url);
CREATE INDEX IF NOT EXISTS idx_xref_a          ON cross_references(project_id_a);
CREATE INDEX IF NOT EXISTS idx_xref_b          ON cross_references(project_id_b);
CREATE INDEX IF NOT EXISTS idx_tags_project    ON tags(project_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag        ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_licenses_proj   ON licenses(project_id);
CREATE INDEX IF NOT EXISTS idx_metrics_proj    ON metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_bom_proj        ON bom_components(project_id);
CREATE INDEX IF NOT EXISTS idx_pubs_proj       ON publications(project_id);
CREATE INDEX IF NOT EXISTS idx_pubs_doi        ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_contribs_proj   ON contributors(project_id);
CREATE INDEX IF NOT EXISTS idx_repo_metrics    ON repo_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_repo_metrics_url ON repo_metrics(repo_url);
CREATE INDEX IF NOT EXISTS idx_bom_paths_proj  ON bom_file_paths(project_id);
CREATE INDEX IF NOT EXISTS idx_comp_prices_bom ON component_prices(bom_component_id);
"""


def open_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with recommended pragmas.

    Args:
        path: Filesystem path for the database file.

    Returns:
        A configured ``sqlite3.Connection``.
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path = DB_PATH) -> None:
    """Create the database and all tables if they don't exist.

    Args:
        path: Filesystem path for the database file.
    """
    conn = open_connection(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", path)


@contextmanager
def transaction(path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that commits on success, rolls back on error.

    Args:
        path: Filesystem path for the database file.

    Yields:
        An open ``sqlite3.Connection`` inside a transaction.
    """
    conn = open_connection(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_project(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_id: str,
    name: str,
    description: str | None = None,
    url: str | None = None,
    repo_url: str | None = None,
    documentation_url: str | None = None,
    author: str | None = None,
    country: str | None = None,
    category: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> int:
    """Insert or update a project, returning its ``id``.

    On conflict (same source + source_id), non-NULL new values overwrite
    existing NULL values but do not overwrite existing non-NULL values.

    Args:
        conn: Active database connection.
        source: Data source name (e.g. ``"hackaday"``).
        source_id: Platform-specific identifier.
        name: Project name/title.
        description: Project description.
        url: Project web page URL.
        repo_url: Code repository URL.
        documentation_url: Documentation URL.
        author: Author or responsible party.
        country: Country of origin.
        category: Project category/type.
        created_at: Creation date (ISO 8601).
        updated_at: Last update date (ISO 8601).

    Returns:
        The ``projects.id`` for the upserted row.
    """
    cursor = conn.execute(
        """\
        INSERT INTO projects
            (source, source_id, name, description, url, repo_url,
             documentation_url, author, country, category,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, source_id) DO UPDATE SET
            description       = COALESCE(excluded.description, projects.description),
            url               = COALESCE(excluded.url, projects.url),
            repo_url          = COALESCE(excluded.repo_url, projects.repo_url),
            documentation_url = COALESCE(
                excluded.documentation_url,
                projects.documentation_url
            ),
            author            = COALESCE(excluded.author, projects.author),
            country           = COALESCE(excluded.country, projects.country),
            category          = COALESCE(excluded.category, projects.category),
            created_at        = COALESCE(excluded.created_at, projects.created_at),
            updated_at        = COALESCE(excluded.updated_at, projects.updated_at)
        RETURNING id
        """,
        (
            source,
            source_id,
            name,
            description,
            url,
            repo_url,
            documentation_url,
            author,
            country,
            category,
            created_at,
            updated_at,
        ),
    )
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def insert_tags(
    conn: sqlite3.Connection,
    project_id: int,
    tags: list[str],
) -> None:
    """Insert tags for a project, skipping duplicates.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id`` to associate tags with.
        tags: List of tag strings.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO tags (project_id, tag) VALUES (?, ?)",
        [(project_id, t.strip()) for t in tags if t.strip()],
    )


def insert_license(
    conn: sqlite3.Connection,
    project_id: int,
    license_type: str,
    license_name: str,
) -> None:
    """Insert a license record, skipping duplicates.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id`` to associate the license with.
        license_type: One of ``"hardware"``, ``"software"``, ``"documentation"``.
        license_name: License identifier (e.g. ``"CERN-OHL-S-2.0"``).
    """
    conn.execute(
        """\
        INSERT OR IGNORE INTO licenses (project_id, license_type, license_name)
        VALUES (?, ?, ?)
        """,
        (project_id, license_type, license_name),
    )


def insert_metric(
    conn: sqlite3.Connection,
    project_id: int,
    metric_name: str,
    metric_value: int | None,
) -> None:
    """Insert or update an engagement metric.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        metric_name: Metric key (e.g. ``"stars"``, ``"views"``).
        metric_value: Integer metric value.
    """
    conn.execute(
        """\
        INSERT INTO metrics (project_id, metric_name, metric_value)
        VALUES (?, ?, ?)
        ON CONFLICT(project_id, metric_name)
        DO UPDATE SET metric_value = excluded.metric_value
        """,
        (project_id, metric_name, metric_value),
    )


_GARBAGE_MPN = frozenset({
    "", "?", "-", "~", "custom", "ebay", "aliexpress",
    "n/a", "na", "null", "none", "tbd", "tba",
})

_GARBAGE_MPN_RE = re.compile(
    r"https?://"
    r"|^\$\d"
    r"|\.(?:com|org|io|net|cn)(?:/|\s|$)",
    re.IGNORECASE,
)


def sanitize_part_number(raw: str | None) -> str | None:
    """Sanitize a manufacturer part number, returning None for garbage.

    Filters empty strings, single characters, placeholder values,
    URLs, price-like strings, and domain names.

    Args:
        raw: Raw part number string from source data.

    Returns:
        Cleaned part number string, or None if invalid.
    """
    if raw is None:
        return None
    cleaned = raw.strip()
    if len(cleaned) <= 1:
        return None
    if cleaned.lower() in _GARBAGE_MPN:
        return None
    if _GARBAGE_MPN_RE.search(cleaned):
        return None
    return cleaned


def insert_bom_component(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    reference: str | None = None,
    component_name: str | None = None,
    quantity: int | None = None,
    unit_cost: float | None = None,
    manufacturer: str | None = None,
    part_number: str | None = None,
) -> None:
    """Insert a single BOM component.

    Sanitizes ``part_number`` to convert garbage values (empty strings,
    URLs, placeholders, price strings) to NULL before insertion.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        reference: Component reference designator.
        component_name: Component description/name.
        quantity: Part quantity.
        unit_cost: Per-unit cost.
        manufacturer: Manufacturer name.
        part_number: Manufacturer part number.
    """
    part_number = sanitize_part_number(part_number)
    conn.execute(
        """\
        INSERT INTO bom_components
            (project_id, reference, component_name, quantity,
             unit_cost, manufacturer, part_number)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            reference,
            component_name,
            quantity,
            unit_cost,
            manufacturer,
            part_number,
        ),
    )


def insert_publication(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    doi: str | None = None,
    title: str | None = None,
    publication_year: int | None = None,
    journal: str | None = None,
    cited_by_count: int | None = None,
    open_access: bool | None = None,
) -> None:
    """Insert a publication linked to a project.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        doi: Digital Object Identifier.
        title: Publication title.
        publication_year: Year published.
        journal: Journal or venue name.
        cited_by_count: Citation count from OpenAlex.
        open_access: Whether the publication is open access.
    """
    oa_int = int(open_access) if open_access is not None else None
    conn.execute(
        """\
        INSERT OR IGNORE INTO publications
            (project_id, doi, title, publication_year, journal,
             cited_by_count, open_access)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, doi, title, publication_year, journal, cited_by_count, oa_int),
    )


def upsert_repo_metrics(
    conn: sqlite3.Connection,
    project_id: int,
    repo_url: str,
    *,
    stars: int | None = None,
    forks: int | None = None,
    watchers: int | None = None,
    open_issues: int | None = None,
    total_issues: int | None = None,
    open_prs: int | None = None,
    closed_prs: int | None = None,
    total_prs: int | None = None,
    releases_count: int | None = None,
    branches_count: int | None = None,
    tags_count: int | None = None,
    contributors_count: int | None = None,
    community_health: int | None = None,
    primary_language: str | None = None,
    has_bom: bool | None = None,
    has_readme: bool | None = None,
    repo_size_kb: int | None = None,
    total_files: int | None = None,
    archived: bool | None = None,
    pushed_at: str | None = None,
) -> None:
    """Insert or replace repo metrics for a specific repository.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        repo_url: Canonical GitHub URL (e.g. ``https://github.com/owner/repo``).
        stars: GitHub star count.
        forks: Fork count.
        watchers: Watcher count.
        open_issues: Open issue count.
        total_issues: Total issue count (excludes PRs).
        open_prs: Open pull request count.
        closed_prs: Closed pull request count.
        total_prs: Total pull request count.
        releases_count: Number of releases.
        branches_count: Number of branches.
        tags_count: Number of tags.
        contributors_count: Number of contributors.
        community_health: GitHub community health percentage (0-100).
        primary_language: Primary programming language.
        has_bom: Whether BOM files were detected.
        has_readme: Whether a README exists.
        repo_size_kb: Repository size in KB.
        total_files: Total file count in the repo tree.
        archived: Whether the repo is archived.
        pushed_at: Last push timestamp (ISO 8601).
    """
    conn.execute(
        """\
        INSERT INTO repo_metrics
            (project_id, repo_url, stars, forks, watchers,
             open_issues, total_issues,
             open_prs, closed_prs, total_prs, releases_count,
             branches_count, tags_count, contributors_count,
             community_health, primary_language, has_bom, has_readme,
             repo_size_kb, total_files, archived, pushed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, repo_url) DO UPDATE SET
            stars = excluded.stars,
            forks = excluded.forks,
            watchers = excluded.watchers,
            open_issues = excluded.open_issues,
            total_issues = excluded.total_issues,
            open_prs = excluded.open_prs,
            closed_prs = excluded.closed_prs,
            total_prs = excluded.total_prs,
            releases_count = excluded.releases_count,
            branches_count = excluded.branches_count,
            tags_count = excluded.tags_count,
            contributors_count = excluded.contributors_count,
            community_health = excluded.community_health,
            primary_language = excluded.primary_language,
            has_bom = excluded.has_bom,
            has_readme = excluded.has_readme,
            repo_size_kb = excluded.repo_size_kb,
            total_files = excluded.total_files,
            archived = excluded.archived,
            pushed_at = excluded.pushed_at
        """,
        (
            project_id, repo_url,
            stars, forks, watchers, open_issues, total_issues,
            open_prs, closed_prs, total_prs, releases_count, branches_count,
            tags_count, contributors_count, community_health,
            primary_language,
            int(has_bom) if has_bom is not None else None,
            int(has_readme) if has_readme is not None else None,
            repo_size_kb, total_files,
            int(archived) if archived is not None else None,
            pushed_at,
        ),
    )


def insert_bom_file_path(
    conn: sqlite3.Connection,
    project_id: int,
    repo_url: str,
    file_path: str,
) -> None:
    """Record a BOM file path found in a specific repository.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        repo_url: Canonical GitHub URL for the repo.
        file_path: Relative path to the BOM file in the repo.
    """
    conn.execute(
        "INSERT OR IGNORE INTO bom_file_paths "
        "(project_id, repo_url, file_path) VALUES (?, ?, ?)",
        (project_id, repo_url, file_path),
    )


def insert_contributor(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    name: str,
    role: str | None = None,
    permission: str | None = None,
) -> None:
    """Insert or update a contributor for a project.

    Args:
        conn: Active database connection.
        project_id: The ``projects.id``.
        name: Contributor name.
        role: Contributor role description.
        permission: Permission level (e.g. ``"admin"``, ``"write"``).
    """
    conn.execute(
        """\
        INSERT INTO contributors (project_id, name, role, permission)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(project_id, name) DO UPDATE SET
            role = excluded.role,
            permission = excluded.permission
        """,
        (project_id, name, role, permission),
    )


def upsert_component_price(
    conn: sqlite3.Connection,
    bom_component_id: int,
    *,
    matched_mpn: str | None = None,
    distributor: str | None = None,
    unit_price: float | None = None,
    currency: str = "USD",
    quantity_break: int = 1,
    price_date: str,
    price_source: str,
) -> None:
    """Insert or update a component price record.

    Args:
        conn: Active database connection.
        bom_component_id: The ``bom_components.id``.
        matched_mpn: Manufacturer part number matched via API.
        distributor: Distributor name (e.g. ``"DigiKey"``).
        unit_price: Per-unit price.
        currency: ISO 4217 currency code.
        quantity_break: Quantity tier for this price.
        price_date: Date the price was fetched (ISO 8601).
        price_source: Source of pricing data (e.g. ``"nexar"``).
    """
    conn.execute(
        """\
        INSERT INTO component_prices
            (bom_component_id, matched_mpn, distributor, unit_price,
             currency, quantity_break, price_date, price_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bom_component_id, distributor, quantity_break)
        DO UPDATE SET
            matched_mpn  = excluded.matched_mpn,
            unit_price   = excluded.unit_price,
            currency     = excluded.currency,
            price_date   = excluded.price_date,
            price_source = excluded.price_source
        """,
        (
            bom_component_id, matched_mpn, distributor, unit_price,
            currency, quantity_break, price_date, price_source,
        ),
    )
