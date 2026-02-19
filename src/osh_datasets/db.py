"""SQLite database schema and connection management."""

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
    permission    TEXT
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_projects_source ON projects(source);
CREATE INDEX IF NOT EXISTS idx_projects_name   ON projects(name);
CREATE INDEX IF NOT EXISTS idx_projects_repo   ON projects(repo_url);
CREATE INDEX IF NOT EXISTS idx_tags_project    ON tags(project_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag        ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_licenses_proj   ON licenses(project_id);
CREATE INDEX IF NOT EXISTS idx_metrics_proj    ON metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_bom_proj        ON bom_components(project_id);
CREATE INDEX IF NOT EXISTS idx_pubs_proj       ON publications(project_id);
CREATE INDEX IF NOT EXISTS idx_pubs_doi        ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_contribs_proj   ON contributors(project_id);
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


def insert_contributor(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    name: str,
    role: str | None = None,
    permission: str | None = None,
) -> None:
    """Insert a contributor for a project.

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
        """,
        (project_id, name, role, permission),
    )
