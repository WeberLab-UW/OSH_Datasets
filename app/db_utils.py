"""Shared database utilities for the Streamlit web interface.

Provides cached, read-only query functions that return polars
DataFrames. All SQL uses parameterized queries.
"""

import sqlite3
from pathlib import Path
from typing import Literal

import polars as pl
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "osh_datasets.db"
DB_URI = f"file:{DB_PATH}?mode=ro"

_SORT_ALLOWLIST: frozenset[str] = frozenset({
    "name",
    "source",
    "completeness",
    "coverage",
    "depth",
    "open_o_meter",
    "stars",
    "created_at",
})


def _get_conn() -> sqlite3.Connection:
    """Open a read-only SQLite connection with optimized pragmas.

    Returns:
        Configured sqlite3.Connection in read-only mode.
    """
    conn = sqlite3.connect(DB_URI, uri=True)
    conn.execute("PRAGMA cache_size = -64000")
    conn.row_factory = sqlite3.Row
    return conn


def _query_df(sql: str, params: tuple[object, ...] = ()) -> pl.DataFrame:
    """Execute SQL and return a polars DataFrame.

    Args:
        sql: SQL query string with ? placeholders.
        params: Tuple of parameter values.

    Returns:
        Query results as a polars DataFrame.
    """
    conn = _get_conn()
    cursor = conn.execute(sql, params)
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return pl.DataFrame(
            {c: [] for c in cols},
        )
    return pl.DataFrame(
        {c: [r[i] for r in rows] for i, c in enumerate(cols)},
    )


def _query_one(
    sql: str, params: tuple[object, ...] = (),
) -> dict[str, object] | None:
    """Execute SQL and return a single row as a dict.

    Args:
        sql: SQL query string with ? placeholders.
        params: Tuple of parameter values.

    Returns:
        First row as dict, or None if no results.
    """
    conn = _get_conn()
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row, strict=True))


def _validated_sort(col: str) -> str:
    """Validate a sort column against the allowlist.

    Args:
        col: Requested sort column name.

    Returns:
        The column if allowed, otherwise 'name'.
    """
    return col if col in _SORT_ALLOWLIST else "name"


# ---- Home page queries ----


@st.cache_data(ttl=600)
def get_dataset_summary() -> dict[str, object]:
    """Fetch aggregate dataset statistics.

    Returns:
        Dict with total_projects, source_count, bom_count,
        llm_count, repo_metrics_count, projects_with_repo.
    """
    result = _query_one("""
        SELECT
            (SELECT COUNT(*) FROM projects) AS total_projects,
            (SELECT COUNT(DISTINCT source) FROM projects)
                AS source_count,
            (SELECT COUNT(*) FROM bom_components) AS bom_count,
            (SELECT COUNT(*) FROM llm_evaluations) AS llm_count,
            (SELECT COUNT(*) FROM repo_metrics)
                AS repo_metrics_count,
            (SELECT COUNT(DISTINCT id) FROM projects
             WHERE repo_url IS NOT NULL AND repo_url <> '')
                AS projects_with_repo
    """)
    return result or {}


@st.cache_data(ttl=600)
def get_sources_summary() -> pl.DataFrame:
    """Fetch per-source summary statistics.

    Returns:
        DataFrame with source, project_count, with_repo,
        with_llm_eval, avg_completeness, avg_coverage, avg_depth,
        avg_open_o_meter.
    """
    return _query_df("""
        SELECT
            p.source,
            COUNT(*) AS project_count,
            SUM(CASE WHEN p.repo_url IS NOT NULL
                     AND p.repo_url <> '' THEN 1 ELSE 0 END)
                AS with_repo,
            COUNT(le.id) AS with_llm_eval,
            ROUND(AVG(dqs.completeness_score), 1)
                AS avg_completeness,
            ROUND(AVG(dqs.coverage_score), 1) AS avg_coverage,
            ROUND(AVG(dqs.depth_score), 1) AS avg_depth,
            ROUND(AVG(dqs.open_o_meter_score), 1)
                AS avg_open_o_meter
        FROM projects p
        LEFT JOIN (
            SELECT DISTINCT project_id, id
            FROM llm_evaluations
        ) le ON le.project_id = p.id
        LEFT JOIN doc_quality_scores dqs
            ON dqs.project_id = p.id
        GROUP BY p.source
        ORDER BY COUNT(*) DESC
    """)


# ---- Browse Projects queries ----


@st.cache_data(ttl=600)
def get_distinct_sources() -> list[str]:
    """Fetch all distinct source names.

    Returns:
        Sorted list of source names.
    """
    df = _query_df(
        "SELECT DISTINCT source FROM projects ORDER BY source",
    )
    return df["source"].to_list()


@st.cache_data(ttl=600)
def get_project_count(
    sources: tuple[str, ...] | None = None,
    search: str = "",
    has_repo: bool = False,
    has_bom: bool = False,
) -> int:
    """Count projects matching the given filters.

    Args:
        sources: Tuple of source names to filter by.
        search: Text to search in name/description/author.
        has_repo: If True, only projects with repo_url.
        has_bom: If True, only projects with BOM data.

    Returns:
        Number of matching projects.
    """
    clauses: list[str] = []
    params: list[object] = []

    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"p.source IN ({placeholders})")
        params.extend(sources)
    if search:
        like = f"%{search}%"
        clauses.append(
            "(p.name LIKE ? OR p.description LIKE ?"
            " OR p.author LIKE ?)",
        )
        params.extend([like, like, like])
    if has_repo:
        clauses.append(
            "p.repo_url IS NOT NULL AND p.repo_url <> ''",
        )
    if has_bom:
        clauses.append(
            "EXISTS (SELECT 1 FROM bom_components bc"
            " WHERE bc.project_id = p.id)",
        )

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    result = _query_one(
        f"SELECT COUNT(*) AS cnt FROM projects p {where}",
        tuple(params),
    )
    if not result:
        return 0
    cnt = result["cnt"]
    return int(str(cnt)) if cnt is not None else 0


@st.cache_data(ttl=600)
def get_projects_page(
    sources: tuple[str, ...] | None = None,
    search: str = "",
    has_repo: bool = False,
    has_bom: bool = False,
    sort_col: str = "name",
    sort_dir: Literal["ASC", "DESC"] = "ASC",
    offset: int = 0,
    limit: int = 50,
) -> pl.DataFrame:
    """Fetch a page of projects with scores and metrics.

    Args:
        sources: Tuple of source names to filter by.
        search: Text to search in name/description/author.
        has_repo: If True, only projects with repo_url.
        has_bom: If True, only projects with BOM data.
        sort_col: Column to sort by (validated against allowlist).
        sort_dir: Sort direction, ASC or DESC.
        offset: Number of rows to skip.
        limit: Maximum rows to return.

    Returns:
        DataFrame with project fields, scores, and stars.
    """
    clauses: list[str] = []
    params: list[object] = []

    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"p.source IN ({placeholders})")
        params.extend(sources)
    if search:
        like = f"%{search}%"
        clauses.append(
            "(p.name LIKE ? OR p.description LIKE ?"
            " OR p.author LIKE ?)",
        )
        params.extend([like, like, like])
    if has_repo:
        clauses.append(
            "p.repo_url IS NOT NULL AND p.repo_url <> ''",
        )
    if has_bom:
        clauses.append(
            "EXISTS (SELECT 1 FROM bom_components bc"
            " WHERE bc.project_id = p.id)",
        )

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    validated = _validated_sort(sort_col)
    direction = "DESC" if sort_dir == "DESC" else "ASC"
    params.extend([limit, offset])

    return _query_df(
        f"""
        SELECT
            p.id,
            p.source,
            p.name,
            p.author,
            COALESCE(dqs.completeness_score, 0)
                AS completeness,
            COALESCE(dqs.coverage_score, 0) AS coverage,
            COALESCE(dqs.depth_score, 0) AS depth,
            COALESCE(dqs.open_o_meter_score, 0)
                AS open_o_meter,
            rm.stars
        FROM projects p
        LEFT JOIN doc_quality_scores dqs
            ON dqs.project_id = p.id
        LEFT JOIN (
            SELECT project_id, MAX(stars) AS stars
            FROM repo_metrics GROUP BY project_id
        ) rm ON rm.project_id = p.id
        {where}
        ORDER BY {validated} {direction}
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )


# ---- Score Distribution queries ----


@st.cache_data(ttl=600)
def get_track1_scores() -> pl.DataFrame:
    """Fetch all Track 1 scores with source labels.

    Returns:
        DataFrame with source, completeness_score,
        coverage_score, depth_score, open_o_meter_score.
    """
    return _query_df("""
        SELECT
            p.source,
            dqs.completeness_score,
            dqs.coverage_score,
            dqs.depth_score,
            dqs.open_o_meter_score
        FROM doc_quality_scores dqs
        JOIN projects p ON p.id = dqs.project_id
    """)


@st.cache_data(ttl=600)
def get_track2_binary_rates() -> pl.DataFrame:
    """Fetch Track 2 binary dimension rates by source.

    Returns:
        DataFrame with source, total, and sum of each binary
        dimension column.
    """
    return _query_df("""
        SELECT
            p.source,
            COUNT(*) AS total,
            SUM(le.license_present) AS license_present,
            SUM(le.bom_present) AS bom_present,
            SUM(le.assembly_present) AS assembly_present,
            SUM(le.hw_design_present) AS hw_design_present,
            SUM(le.mech_design_present) AS mech_design_present,
            SUM(le.sw_fw_present) AS sw_fw_present,
            SUM(le.testing_present) AS testing_present,
            SUM(le.contributing_present)
                AS contributing_present,
            SUM(le.cost_mentioned) AS cost_mentioned,
            SUM(le.suppliers_referenced)
                AS suppliers_referenced,
            SUM(le.part_numbers_present)
                AS part_numbers_present
        FROM llm_evaluations le
        JOIN projects p ON p.id = le.project_id
        GROUP BY p.source
    """)


@st.cache_data(ttl=600)
def get_track2_categorical() -> pl.DataFrame:
    """Fetch Track 2 categorical fields with source.

    Returns:
        DataFrame with source, project_type,
        structure_quality, maturity_stage.
    """
    return _query_df("""
        SELECT
            p.source,
            le.project_type,
            le.structure_quality,
            le.maturity_stage
        FROM llm_evaluations le
        JOIN projects p ON p.id = le.project_id
    """)


# ---- Compare Sources queries ----


@st.cache_data(ttl=600)
def get_source_coverage_matrix() -> pl.DataFrame:
    """Fetch per-source artifact coverage rates.

    Returns:
        DataFrame with source, total, and counts of various
        metadata presence signals.
    """
    return _query_df("""
        SELECT
            p.source,
            COUNT(*) AS total,
            SUM(CASE WHEN p.repo_url IS NOT NULL
                     AND p.repo_url <> '' THEN 1 ELSE 0 END)
                AS has_repo,
            SUM(CASE WHEN EXISTS (
                SELECT 1 FROM licenses l
                WHERE l.project_id = p.id
            ) THEN 1 ELSE 0 END) AS has_license,
            SUM(CASE WHEN EXISTS (
                SELECT 1 FROM bom_components bc
                WHERE bc.project_id = p.id
            ) THEN 1 ELSE 0 END) AS has_bom,
            SUM(CASE WHEN EXISTS (
                SELECT 1 FROM contributors c
                WHERE c.project_id = p.id
            ) THEN 1 ELSE 0 END) AS has_contributors,
            SUM(CASE WHEN EXISTS (
                SELECT 1 FROM publications pub
                WHERE pub.project_id = p.id
            ) THEN 1 ELSE 0 END) AS has_publications,
            SUM(CASE WHEN p.description IS NOT NULL
                     AND p.description <> ''
                THEN 1 ELSE 0 END) AS has_description
        FROM projects p
        GROUP BY p.source
        ORDER BY COUNT(*) DESC
    """)


# ---- Project Detail queries ----


@st.cache_data(ttl=600)
def get_project_detail(project_id: int) -> dict[str, object] | None:
    """Fetch core project fields by ID.

    Args:
        project_id: The project's primary key.

    Returns:
        Dict of project fields, or None if not found.
    """
    return _query_one(
        """
        SELECT id, source, source_id, name, description,
               url, repo_url, documentation_url, author,
               country, category, created_at, updated_at
        FROM projects WHERE id = ?
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_scores(
    project_id: int,
) -> dict[str, object] | None:
    """Fetch Track 1 doc quality scores for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        Dict with 4 score fields, or None if not scored.
    """
    return _query_one(
        """
        SELECT completeness_score, coverage_score,
               depth_score, open_o_meter_score
        FROM doc_quality_scores WHERE project_id = ?
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_llm_eval(
    project_id: int,
) -> dict[str, object] | None:
    """Fetch the latest Track 2 LLM evaluation for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        Dict with 30+ evaluation fields, or None if not evaluated.
    """
    return _query_one(
        """
        SELECT
            project_type, structure_quality, maturity_stage,
            license_present, license_type, license_name,
            contributing_present, contributing_level,
            bom_present, bom_completeness, bom_component_count,
            assembly_present, assembly_detail,
            assembly_step_count,
            hw_design_present, hw_editable_source,
            mech_design_present, mech_editable_source,
            sw_fw_present, sw_fw_type, sw_fw_doc_level,
            testing_present, testing_detail,
            cost_mentioned, suppliers_referenced,
            part_numbers_present,
            hw_license_name, sw_license_name, doc_license_name,
            model_id, prompt_version, evaluated_at
        FROM llm_evaluations
        WHERE project_id = ?
        ORDER BY evaluated_at DESC LIMIT 1
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_repo_metrics(
    project_id: int,
) -> dict[str, object] | None:
    """Fetch GitHub repository metrics for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        Dict with repo metrics, or None if unavailable.
    """
    return _query_one(
        """
        SELECT stars, forks, watchers, open_issues,
               total_issues, open_prs, closed_prs,
               total_prs, releases_count, branches_count,
               tags_count, contributors_count,
               community_health, primary_language,
               has_bom, has_readme, repo_size_kb,
               total_files, archived, pushed_at
        FROM repo_metrics WHERE project_id = ?
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_bom(project_id: int) -> pl.DataFrame:
    """Fetch BOM components for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        DataFrame with component details.
    """
    return _query_df(
        """
        SELECT
            reference, component_name,
            component_category AS category,
            quantity,
            manufacturer_canonical AS manufacturer,
            part_number,
            footprint_normalized AS footprint,
            footprint_mount_type AS mount,
            unit_cost,
            value_numeric, value_unit
        FROM bom_components
        WHERE project_id = ?
        ORDER BY reference
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_licenses(project_id: int) -> pl.DataFrame:
    """Fetch licenses for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        DataFrame with license_type, license_name,
        license_normalized.
    """
    return _query_df(
        """
        SELECT license_type, license_name, license_normalized
        FROM licenses
        WHERE project_id = ?
        ORDER BY license_type
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_tags(project_id: int) -> list[str]:
    """Fetch tags for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        Sorted list of tag strings.
    """
    df = _query_df(
        "SELECT tag FROM tags WHERE project_id = ? ORDER BY tag",
        (project_id,),
    )
    return df["tag"].to_list() if df.height > 0 else []


@st.cache_data(ttl=600)
def get_project_contributors(project_id: int) -> pl.DataFrame:
    """Fetch contributors for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        DataFrame with name, role, permission.
    """
    return _query_df(
        """
        SELECT name, role, permission
        FROM contributors
        WHERE project_id = ?
        ORDER BY name
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def get_project_publications(project_id: int) -> pl.DataFrame:
    """Fetch publications for a project.

    Args:
        project_id: The project's primary key.

    Returns:
        DataFrame with doi, title, journal,
        publication_year, cited_by_count, open_access.
    """
    return _query_df(
        """
        SELECT doi, title, journal, publication_year,
               cited_by_count, open_access
        FROM publications
        WHERE project_id = ?
        ORDER BY publication_year DESC
        """,
        (project_id,),
    )


@st.cache_data(ttl=600)
def search_projects(query: str, limit: int = 20) -> pl.DataFrame:
    """Search projects by name for autocomplete.

    Args:
        query: Search string to match against project name.
        limit: Maximum results to return.

    Returns:
        DataFrame with id, name, source.
    """
    return _query_df(
        """
        SELECT id, name, source
        FROM projects
        WHERE name LIKE ?
        ORDER BY name
        LIMIT ?
        """,
        (f"%{query}%", limit),
    )
