"""Tests for Track 1 metadata-based documentation quality scoring."""

from pathlib import Path

import pytest

from osh_datasets.db import init_db, open_connection
from osh_datasets.enrichment.doc_quality import (
    _compute_completeness,
    _compute_coverage,
    _compute_depth,
    _compute_open_o_meter,
    score_doc_quality,
)


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    # Ensure license_normalized column exists
    conn = open_connection(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
    if "license_normalized" not in cols:
        conn.execute("ALTER TABLE licenses ADD COLUMN license_normalized TEXT")
        conn.commit()
    conn.close()
    return db_path


def _insert_full_project(db_path: Path) -> int:
    """Insert a fully documented project with all metadata signals."""
    conn = open_connection(db_path)

    cursor = conn.execute(
        "INSERT INTO projects "
        "(source, source_id, name, description, url, repo_url, "
        "documentation_url, author, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "test", "full_1", "Full Project",
            "A" * 600,  # >500 chars for depth
            "https://example.com",
            "https://github.com/owner/repo",
            "https://docs.example.com",
            "Test Author",
            "2024-01-01",
        ),
    )
    pid = cursor.lastrowid
    assert pid is not None

    # Licenses (multi-type for coverage dim 4)
    conn.execute(
        "INSERT INTO licenses "
        "(project_id, license_type, license_name, license_normalized) "
        "VALUES (?, ?, ?, ?)",
        (pid, "hardware", "CERN-OHL-S-2.0", "CERN-OHL-S-2.0"),
    )
    conn.execute(
        "INSERT INTO licenses "
        "(project_id, license_type, license_name, license_normalized) "
        "VALUES (?, ?, ?, ?)",
        (pid, "software", "MIT", "MIT"),
    )

    # Tags
    conn.execute(
        "INSERT INTO tags (project_id, tag) VALUES (?, ?)",
        (pid, "hardware"),
    )

    # Contributors
    conn.execute(
        "INSERT INTO contributors (project_id, name) VALUES (?, ?)",
        (pid, "Alice"),
    )
    for i in range(4):
        conn.execute(
            "INSERT INTO contributors (project_id, name) VALUES (?, ?)",
            (pid, f"Contributor_{i}"),
        )

    # BOM components
    for i in range(12):
        conn.execute(
            "INSERT INTO bom_components (project_id, component_name, quantity) "
            "VALUES (?, ?, ?)",
            (pid, f"Part_{i}", i + 1),
        )

    # Publication
    conn.execute(
        "INSERT INTO publications (project_id, doi, title) VALUES (?, ?, ?)",
        (pid, "10.1234/test", "Test Paper"),
    )

    # Repo metrics
    conn.execute(
        "INSERT INTO repo_metrics "
        "(project_id, repo_url, has_bom, has_readme, total_issues, "
        "community_health, releases_count, pushed_at, contributors_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, "https://github.com/owner/repo", 1, 1, 10, 80, 5,
         "2025-12-01", 5),
    )

    conn.commit()
    conn.close()
    return pid


def _insert_minimal_project(db_path: Path) -> int:
    """Insert a project with only name and source (minimum required)."""
    conn = open_connection(db_path)
    cursor = conn.execute(
        "INSERT INTO projects (source, source_id, name) VALUES (?, ?, ?)",
        ("test", "min_1", "Minimal Project"),
    )
    pid = cursor.lastrowid
    assert pid is not None
    conn.commit()
    conn.close()
    return pid


class TestComputeCompleteness:
    """Tests for the completeness score computation."""

    def test_fully_documented(self) -> None:
        """All signals present gives 100."""
        row = {
            "has_bom_any": 1, "has_license": 1, "has_repo": 1,
            "has_readme": 1, "has_doc_url": 1, "has_description": 1,
            "has_contributors": 1, "has_author": 1,
            "has_timestamps": 1, "has_tags": 1,
        }
        assert _compute_completeness(row) == 100

    def test_empty(self) -> None:
        """No signals gives 0."""
        assert _compute_completeness({}) == 0

    def test_partial(self) -> None:
        """Only BOM and license gives 35."""
        row = {"has_bom_any": 1, "has_license": 1}
        assert _compute_completeness(row) == 35


class TestComputeCoverage:
    """Tests for the coverage score computation."""

    def test_full_coverage(self) -> None:
        """All 12 dimensions gives 100."""
        row = {
            "has_description": 1, "has_license": 1,
            "has_multi_license_type": 1, "has_repo": 1,
            "has_doc_url": 1, "has_bom_any": 1,
            "has_contributors": 1, "has_tags": 1,
            "has_publication": 1, "has_readme": 1, "has_issues": 1,
        }
        assert _compute_coverage(row) == 100

    def test_identity_only(self) -> None:
        """Only identity (always true) gives 1/12 = 8%."""
        assert _compute_coverage({}) == 8


class TestComputeDepth:
    """Tests for the depth score computation."""

    def test_no_signals(self) -> None:
        """No data returns 0."""
        assert _compute_depth({}) == 0

    def test_ignores_null_signals(self) -> None:
        """Only non-null signals contribute to the mean."""
        row: dict[str, int | float | None] = {
            "description_len": 500,  # -> 100
            "bom_component_count": None,
            "community_health": None,
            "contributor_count": None,
            "releases_count": None,
            "years_since_update": None,
            "license_specificity": None,
        }
        assert _compute_depth(row) == 100

    def test_mixed_signals(self) -> None:
        """Multiple signals averaged correctly."""
        row: dict[str, int | float | None] = {
            "description_len": 250,  # -> 50.0
            "bom_component_count": 5,  # -> 50.0
        }
        assert _compute_depth(row) == 50

    def test_recency_penalty(self) -> None:
        """Old projects are penalized by recency signal."""
        row: dict[str, int | float | None] = {
            "years_since_update": 6.0,  # -> max(0, 100 - 120) = 0
        }
        assert _compute_depth(row) == 0


class TestComputeOpenOMeter:
    """Tests for the Open-o-Meter score computation."""

    def test_max_score(self) -> None:
        """All dimensions gives 8."""
        row = {
            "has_repo": 1, "has_bom_any": 1, "has_assembly_proxy": 1,
            "has_license": 1, "has_vcs": 1, "has_contrib_guide": 1,
            "has_issues": 1,
        }
        # has_repo counts for both dim 1 and dim 4
        assert _compute_open_o_meter(row) == 8

    def test_zero_score(self) -> None:
        """No dimensions gives 0."""
        assert _compute_open_o_meter({}) == 0

    def test_range_0_to_8(self) -> None:
        """Score is always 0-8."""
        for i in range(100):
            row = {
                "has_repo": i % 2,
                "has_bom_any": (i // 2) % 2,
                "has_license": (i // 4) % 2,
            }
            score = _compute_open_o_meter(row)
            assert 0 <= score <= 8


class TestScoreDocQuality:
    """Integration tests for the full scoring pipeline."""

    def test_fully_documented_project(self, tmp_db: Path) -> None:
        """Full project gets high scores across all metrics."""
        pid = _insert_full_project(tmp_db)
        count = score_doc_quality(tmp_db)
        assert count >= 1

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT completeness_score, coverage_score, depth_score, "
            "open_o_meter_score FROM doc_quality_scores "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        completeness, coverage, depth, oom = row
        assert completeness == 100
        assert coverage >= 90
        assert depth >= 50
        assert oom >= 6

    def test_minimal_project(self, tmp_db: Path) -> None:
        """Minimal project gets low scores."""
        pid = _insert_minimal_project(tmp_db)
        score_doc_quality(tmp_db)

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT completeness_score, coverage_score, depth_score, "
            "open_o_meter_score FROM doc_quality_scores "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        completeness, coverage, depth, oom = row
        assert completeness == 0
        # Coverage: identity only = 1/12 = 8%
        assert coverage == 8
        assert depth == 0
        assert oom == 0

    def test_bom_via_components(self, tmp_db: Path) -> None:
        """BOM detected from bom_components table."""
        conn = open_connection(tmp_db)
        cursor = conn.execute(
            "INSERT INTO projects (source, source_id, name) VALUES (?, ?, ?)",
            ("test", "bom_comp", "BOM Component Project"),
        )
        pid = cursor.lastrowid
        conn.execute(
            "INSERT INTO bom_components (project_id, component_name) "
            "VALUES (?, ?)",
            (pid, "Resistor"),
        )
        conn.commit()
        conn.close()

        score_doc_quality(tmp_db)

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT completeness_score FROM doc_quality_scores "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] >= 20  # BOM = 20 points

    def test_bom_via_file_paths(self, tmp_db: Path) -> None:
        """BOM detected from bom_file_paths table."""
        conn = open_connection(tmp_db)
        cursor = conn.execute(
            "INSERT INTO projects (source, source_id, name, repo_url) "
            "VALUES (?, ?, ?, ?)",
            ("test", "bom_fp", "BOM File Path Project",
             "https://github.com/t/r"),
        )
        pid = cursor.lastrowid
        conn.execute(
            "INSERT INTO bom_file_paths (project_id, repo_url, file_path) "
            "VALUES (?, ?, ?)",
            (pid, "https://github.com/t/r", "bom.csv"),
        )
        conn.commit()
        conn.close()

        score_doc_quality(tmp_db)

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT completeness_score FROM doc_quality_scores "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] >= 20  # BOM = 20 points

    def test_bom_via_repo_metrics(self, tmp_db: Path) -> None:
        """BOM detected from repo_metrics.has_bom."""
        conn = open_connection(tmp_db)
        cursor = conn.execute(
            "INSERT INTO projects (source, source_id, name, repo_url) "
            "VALUES (?, ?, ?, ?)",
            ("test", "bom_rm", "BOM Repo Metrics Project",
             "https://github.com/t/r2"),
        )
        pid = cursor.lastrowid
        conn.execute(
            "INSERT INTO repo_metrics (project_id, repo_url, has_bom) "
            "VALUES (?, ?, ?)",
            (pid, "https://github.com/t/r2", 1),
        )
        conn.commit()
        conn.close()

        score_doc_quality(tmp_db)

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT completeness_score FROM doc_quality_scores "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        # BOM (20) + repo (15)
        assert row[0] >= 35

    def test_idempotent_upsert(self, tmp_db: Path) -> None:
        """Running twice produces identical results."""
        _insert_full_project(tmp_db)

        count1 = score_doc_quality(tmp_db)
        conn = open_connection(tmp_db)
        scores1 = conn.execute(
            "SELECT completeness_score, coverage_score, depth_score, "
            "open_o_meter_score FROM doc_quality_scores"
        ).fetchall()
        conn.close()

        count2 = score_doc_quality(tmp_db)
        conn = open_connection(tmp_db)
        scores2 = conn.execute(
            "SELECT completeness_score, coverage_score, depth_score, "
            "open_o_meter_score FROM doc_quality_scores"
        ).fetchall()
        conn.close()

        assert count1 == count2
        assert scores1 == scores2

    def test_empty_database(self, tmp_db: Path) -> None:
        """Empty DB returns 0, no crashes."""
        count = score_doc_quality(tmp_db)
        assert count == 0
