"""Tests for app/db_utils.py query functions."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

# Add app/ to path so we can import db_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

# Must mock streamlit before importing db_utils
_mock_cache = patch(
    "streamlit.cache_data",
    side_effect=lambda **_kw: (lambda fn: fn),
)
_mock_cache.start()

import db_utils  # noqa: E402

_SCHEMA = """\
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    url TEXT,
    repo_url TEXT,
    documentation_url TEXT,
    author TEXT,
    country TEXT,
    category TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(source, source_id)
);
CREATE TABLE licenses (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    license_type TEXT NOT NULL,
    license_name TEXT NOT NULL,
    license_normalized TEXT,
    UNIQUE(project_id, license_type)
);
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    tag TEXT NOT NULL,
    UNIQUE(project_id, tag)
);
CREATE TABLE contributors (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    role TEXT,
    permission TEXT,
    UNIQUE(project_id, name)
);
CREATE TABLE bom_components (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    reference TEXT,
    component_name TEXT,
    quantity INTEGER,
    unit_cost REAL,
    manufacturer TEXT,
    part_number TEXT,
    footprint TEXT,
    component_category TEXT,
    manufacturer_canonical TEXT,
    footprint_normalized TEXT,
    footprint_mount_type TEXT,
    value_numeric REAL,
    value_unit TEXT
);
CREATE TABLE publications (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    doi TEXT,
    title TEXT,
    publication_year INTEGER,
    journal TEXT,
    cited_by_count INTEGER,
    open_access INTEGER,
    UNIQUE(project_id, doi)
);
CREATE TABLE repo_metrics (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    repo_url TEXT NOT NULL DEFAULT '',
    stars INTEGER,
    forks INTEGER,
    watchers INTEGER,
    open_issues INTEGER,
    total_issues INTEGER,
    open_prs INTEGER,
    closed_prs INTEGER,
    total_prs INTEGER,
    releases_count INTEGER,
    branches_count INTEGER,
    tags_count INTEGER,
    contributors_count INTEGER,
    community_health INTEGER,
    primary_language TEXT,
    has_bom INTEGER,
    has_readme INTEGER,
    repo_size_kb INTEGER,
    total_files INTEGER,
    archived INTEGER,
    pushed_at TEXT,
    UNIQUE(project_id, repo_url)
);
CREATE TABLE doc_quality_scores (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    completeness_score INTEGER NOT NULL,
    coverage_score INTEGER NOT NULL,
    depth_score INTEGER NOT NULL,
    open_o_meter_score INTEGER NOT NULL,
    scored_at TEXT NOT NULL,
    UNIQUE(project_id)
);
CREATE TABLE llm_evaluations (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    prompt_version TEXT NOT NULL,
    model_id TEXT NOT NULL,
    raw_response TEXT NOT NULL,
    project_type TEXT,
    structure_quality TEXT,
    maturity_stage TEXT,
    license_present INTEGER,
    license_type TEXT,
    license_name TEXT,
    contributing_present INTEGER,
    contributing_level INTEGER,
    bom_present INTEGER,
    bom_completeness TEXT,
    bom_component_count INTEGER,
    assembly_present INTEGER,
    assembly_detail TEXT,
    assembly_step_count INTEGER,
    hw_design_present INTEGER,
    hw_editable_source INTEGER,
    mech_design_present INTEGER,
    mech_editable_source INTEGER,
    sw_fw_present INTEGER,
    sw_fw_type TEXT,
    sw_fw_doc_level TEXT,
    testing_present INTEGER,
    testing_detail TEXT,
    cost_mentioned INTEGER,
    suppliers_referenced INTEGER,
    part_numbers_present INTEGER,
    hw_license_name TEXT,
    sw_license_name TEXT,
    doc_license_name TEXT,
    evaluated_at TEXT NOT NULL,
    UNIQUE(project_id, prompt_version)
);
CREATE TABLE component_prices (
    id INTEGER PRIMARY KEY,
    bom_component_id INTEGER NOT NULL REFERENCES bom_components(id),
    matched_mpn TEXT,
    distributor TEXT,
    unit_price REAL,
    currency TEXT DEFAULT 'USD',
    quantity_break INTEGER DEFAULT 1,
    price_date TEXT NOT NULL,
    price_source TEXT NOT NULL,
    UNIQUE(bom_component_id, distributor, quantity_break)
);
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    metric_name TEXT NOT NULL,
    metric_value INTEGER,
    UNIQUE(project_id, metric_name)
);
CREATE TABLE bom_file_paths (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    repo_url TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    component_count INTEGER,
    UNIQUE(project_id, repo_url, file_path)
);
"""


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite DB with schema and sample data.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the populated test database.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)

    # Insert sample projects
    conn.executemany(
        """
        INSERT INTO projects (id, source, source_id, name,
            description, url, repo_url, author, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1, "oshwa", "US001", "Widget",
                "A test widget", "https://example.com/1",
                "https://github.com/test/widget",
                "Alice", "Electronics",
            ),
            (
                2, "hackaday", "HAD002", "Gadget",
                "A test gadget", "https://example.com/2",
                None, "Bob", "Robotics",
            ),
            (
                3, "kitspace", "KIT003", "Board",
                "A test board", "https://example.com/3",
                "https://github.com/test/board",
                "Carol", "PCB",
            ),
        ],
    )

    # Doc quality scores
    conn.executemany(
        """
        INSERT INTO doc_quality_scores
            (project_id, completeness_score, coverage_score,
             depth_score, open_o_meter_score, scored_at)
        VALUES (?, ?, ?, ?, ?, '2026-01-01')
        """,
        [(1, 80, 70, 60, 6), (2, 50, 40, 30, 3), (3, 90, 85, 75, 7)],
    )

    # LLM evaluation for project 1
    conn.execute(
        """
        INSERT INTO llm_evaluations
            (project_id, prompt_version, model_id, raw_response,
             project_type, structure_quality, maturity_stage,
             license_present, bom_present, assembly_present,
             hw_design_present, mech_design_present,
             sw_fw_present, testing_present,
             contributing_present, cost_mentioned,
             suppliers_referenced, part_numbers_present,
             evaluated_at)
        VALUES (1, 'test_8', 'gemini', '{}',
                'hardware', 'well_structured', 'production',
                1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1,
                '2026-01-01')
        """,
    )

    # Repo metrics for project 1
    conn.execute(
        """
        INSERT INTO repo_metrics
            (project_id, repo_url, stars, forks,
             contributors_count, releases_count,
             community_health, primary_language,
             has_bom, has_readme, total_issues)
        VALUES (1, 'https://github.com/test/widget',
                42, 10, 5, 3, 50, 'Python', 1, 1, 15)
        """,
    )

    # BOM component for project 1
    conn.execute(
        """
        INSERT INTO bom_components
            (id, project_id, reference, component_name,
             quantity, manufacturer, part_number,
             component_category, manufacturer_canonical,
             footprint_normalized, footprint_mount_type)
        VALUES (1, 1, 'R1', '10k resistor', 2,
                'Yageo', 'RC0603', 'resistor', 'Yageo',
                '0603', 'smd')
        """,
    )

    # License, tag, contributor, publication for project 1
    conn.execute(
        """
        INSERT INTO licenses
            (project_id, license_type, license_name)
        VALUES (1, 'hardware', 'CERN-OHL-S-2.0')
        """,
    )
    conn.execute(
        "INSERT INTO tags (project_id, tag) VALUES (1, 'iot')",
    )
    conn.execute(
        """
        INSERT INTO contributors (project_id, name, role)
        VALUES (1, 'Alice', 'owner')
        """,
    )
    conn.execute(
        """
        INSERT INTO publications
            (project_id, doi, title, journal,
             publication_year, cited_by_count)
        VALUES (1, '10.1234/test', 'Test Paper',
                'JOH', 2024, 5)
        """,
    )

    conn.commit()
    conn.close()
    return db_path


def _patch_conn(db_path: Path):
    """Create a patch for _get_conn to use the test database.

    Args:
        db_path: Path to the test database.

    Returns:
        Mock context manager.
    """
    def mock_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    return patch.object(db_utils, "_get_conn", mock_conn)


class TestDatasetSummary:
    """Tests for get_dataset_summary."""

    def test_returns_correct_counts(self, tmp_db: Path) -> None:
        """Summary returns expected aggregate counts."""
        with _patch_conn(tmp_db):
            result = db_utils.get_dataset_summary()
        assert result["total_projects"] == 3
        assert result["source_count"] == 3
        assert result["projects_with_repo"] == 2


class TestSourcesSummary:
    """Tests for get_sources_summary."""

    def test_returns_all_sources(self, tmp_db: Path) -> None:
        """Summary includes all sources."""
        with _patch_conn(tmp_db):
            df = db_utils.get_sources_summary()
        assert isinstance(df, pl.DataFrame)
        assert df.height == 3
        sources = set(df["source"].to_list())
        assert sources == {"oshwa", "hackaday", "kitspace"}

    def test_avg_scores_computed(self, tmp_db: Path) -> None:
        """Average scores are non-null for scored projects."""
        with _patch_conn(tmp_db):
            df = db_utils.get_sources_summary()
        oshwa = df.filter(pl.col("source") == "oshwa")
        assert oshwa["avg_completeness"][0] == 80.0


class TestProjectCount:
    """Tests for get_project_count."""

    def test_no_filters(self, tmp_db: Path) -> None:
        """Count returns total when no filters applied."""
        with _patch_conn(tmp_db):
            assert db_utils.get_project_count() == 3

    def test_source_filter(self, tmp_db: Path) -> None:
        """Count filters by source correctly."""
        with _patch_conn(tmp_db):
            count = db_utils.get_project_count(
                sources=("oshwa",),
            )
        assert count == 1

    def test_search_filter(self, tmp_db: Path) -> None:
        """Count filters by search text."""
        with _patch_conn(tmp_db):
            count = db_utils.get_project_count(search="Widget")
        assert count == 1

    def test_has_repo_filter(self, tmp_db: Path) -> None:
        """Count filters for projects with repo URL."""
        with _patch_conn(tmp_db):
            count = db_utils.get_project_count(has_repo=True)
        assert count == 2


class TestProjectsPage:
    """Tests for get_projects_page."""

    def test_returns_dataframe(self, tmp_db: Path) -> None:
        """Page query returns a polars DataFrame."""
        with _patch_conn(tmp_db):
            df = db_utils.get_projects_page()
        assert isinstance(df, pl.DataFrame)
        assert df.height == 3

    def test_pagination(self, tmp_db: Path) -> None:
        """Limit and offset work correctly."""
        with _patch_conn(tmp_db):
            df = db_utils.get_projects_page(limit=2, offset=0)
        assert df.height == 2

    def test_sort_validation(self, tmp_db: Path) -> None:
        """Invalid sort column falls back to name."""
        with _patch_conn(tmp_db):
            df = db_utils.get_projects_page(
                sort_col="DROP TABLE",
            )
        assert df.height == 3


class TestTrack1Scores:
    """Tests for get_track1_scores."""

    def test_returns_all_scored(self, tmp_db: Path) -> None:
        """Returns scores for all scored projects."""
        with _patch_conn(tmp_db):
            df = db_utils.get_track1_scores()
        assert df.height == 3
        assert "completeness_score" in df.columns


class TestTrack2Rates:
    """Tests for get_track2_binary_rates."""

    def test_returns_source_aggregates(
        self, tmp_db: Path,
    ) -> None:
        """Returns per-source aggregates."""
        with _patch_conn(tmp_db):
            df = db_utils.get_track2_binary_rates()
        assert df.height == 1
        assert df["source"][0] == "oshwa"
        assert df["total"][0] == 1


class TestProjectDetail:
    """Tests for project detail queries."""

    def test_get_detail(self, tmp_db: Path) -> None:
        """Returns correct project details."""
        with _patch_conn(tmp_db):
            detail = db_utils.get_project_detail(1)
        assert detail is not None
        assert detail["name"] == "Widget"
        assert detail["source"] == "oshwa"

    def test_get_detail_missing(self, tmp_db: Path) -> None:
        """Returns None for non-existent project."""
        with _patch_conn(tmp_db):
            assert db_utils.get_project_detail(999) is None

    def test_get_scores(self, tmp_db: Path) -> None:
        """Returns Track 1 scores for a project."""
        with _patch_conn(tmp_db):
            scores = db_utils.get_project_scores(1)
        assert scores is not None
        assert scores["completeness_score"] == 80

    def test_get_llm_eval(self, tmp_db: Path) -> None:
        """Returns LLM evaluation for a project."""
        with _patch_conn(tmp_db):
            llm = db_utils.get_project_llm_eval(1)
        assert llm is not None
        assert llm["project_type"] == "hardware"

    def test_get_repo_metrics(self, tmp_db: Path) -> None:
        """Returns repo metrics for a project."""
        with _patch_conn(tmp_db):
            metrics = db_utils.get_project_repo_metrics(1)
        assert metrics is not None
        assert metrics["stars"] == 42

    def test_get_bom(self, tmp_db: Path) -> None:
        """Returns BOM components for a project."""
        with _patch_conn(tmp_db):
            bom = db_utils.get_project_bom(1)
        assert bom.height == 1
        assert bom["category"][0] == "resistor"

    def test_get_licenses(self, tmp_db: Path) -> None:
        """Returns licenses for a project."""
        with _patch_conn(tmp_db):
            lics = db_utils.get_project_licenses(1)
        assert lics.height == 1

    def test_get_tags(self, tmp_db: Path) -> None:
        """Returns tags for a project."""
        with _patch_conn(tmp_db):
            tags = db_utils.get_project_tags(1)
        assert tags == ["iot"]

    def test_get_contributors(self, tmp_db: Path) -> None:
        """Returns contributors for a project."""
        with _patch_conn(tmp_db):
            contribs = db_utils.get_project_contributors(1)
        assert contribs.height == 1

    def test_get_publications(self, tmp_db: Path) -> None:
        """Returns publications for a project."""
        with _patch_conn(tmp_db):
            pubs = db_utils.get_project_publications(1)
        assert pubs.height == 1
        assert pubs["doi"][0] == "10.1234/test"


class TestSearchProjects:
    """Tests for search_projects."""

    def test_search_by_name(self, tmp_db: Path) -> None:
        """Search finds projects by name substring."""
        with _patch_conn(tmp_db):
            df = db_utils.search_projects("Wid")
        assert df.height == 1
        assert df["name"][0] == "Widget"

    def test_search_no_match(self, tmp_db: Path) -> None:
        """Search returns empty for no matches."""
        with _patch_conn(tmp_db):
            df = db_utils.search_projects("nonexistent")
        assert df.height == 0


class TestSortValidation:
    """Tests for _validated_sort."""

    def test_valid_column(self) -> None:
        """Valid column passes through."""
        assert db_utils._validated_sort("stars") == "stars"

    def test_invalid_column(self) -> None:
        """Invalid column falls back to name."""
        assert db_utils._validated_sort("DROP TABLE") == "name"

    def test_empty_string(self) -> None:
        """Empty string falls back to name."""
        assert db_utils._validated_sort("") == "name"
