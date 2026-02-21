"""Tests for the database module."""

from pathlib import Path

import pytest

from osh_datasets.db import (
    init_db,
    insert_bom_component,
    insert_bom_file_path,
    insert_contributor,
    insert_license,
    insert_metric,
    insert_publication,
    insert_tags,
    open_connection,
    sanitize_part_number,
    transaction,
    upsert_project,
    upsert_repo_metrics,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database and return its path."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestInitDb:
    """Tests for database initialization."""

    def test_creates_tables(self, db_path: Path) -> None:
        """All expected tables exist after init."""
        conn = open_connection(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        expected = {
            "projects",
            "licenses",
            "tags",
            "contributors",
            "metrics",
            "bom_components",
            "publications",
            "repo_metrics",
            "bom_file_paths",
        }
        assert expected.issubset(tables)

    def test_foreign_keys_enabled(self, db_path: Path) -> None:
        """Foreign keys pragma is on."""
        conn = open_connection(db_path)
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        conn.close()
        assert result is not None
        assert result[0] == 1

    def test_wal_mode(self, db_path: Path) -> None:
        """WAL journal mode is set."""
        conn = open_connection(db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result is not None
        assert result[0] == "wal"


class TestUpsertProject:
    """Tests for project upsert logic."""

    def test_insert_returns_id(self, db_path: Path) -> None:
        """Inserting a new project returns a positive id."""
        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="test", source_id="1", name="Test Project"
            )
        assert pid > 0

    def test_upsert_preserves_existing(self, db_path: Path) -> None:
        """Upserting with NULL does not overwrite existing non-NULL."""
        with transaction(db_path) as conn:
            pid1 = upsert_project(
                conn,
                source="test",
                source_id="1",
                name="Test",
                description="Original",
            )
            pid2 = upsert_project(
                conn,
                source="test",
                source_id="1",
                name="Test",
                description=None,
            )
        assert pid1 == pid2
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT description FROM projects WHERE id = ?", (pid1,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "Original"

    def test_unique_constraint(self, db_path: Path) -> None:
        """Same source + source_id maps to same project id."""
        with transaction(db_path) as conn:
            pid1 = upsert_project(conn, source="src", source_id="x", name="A")
            pid2 = upsert_project(conn, source="src", source_id="x", name="A")
        assert pid1 == pid2


class TestRelatedTables:
    """Tests for tags, licenses, metrics, BOM, publications, contributors."""

    def test_insert_tags(self, db_path: Path) -> None:
        """Tags are inserted and duplicates are ignored."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_tags(conn, pid, ["a", "b", "a"])
        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT tag FROM tags WHERE project_id = ? ORDER BY tag", (pid,)
        ).fetchall()
        conn.close()
        assert [r[0] for r in rows] == ["a", "b"]

    def test_insert_license(self, db_path: Path) -> None:
        """License record is inserted correctly."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_license(conn, pid, "hardware", "MIT")
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT license_type, license_name FROM licenses WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hardware"
        assert row[1] == "MIT"

    def test_insert_metric_upsert(self, db_path: Path) -> None:
        """Metric upsert overwrites on conflict."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_metric(conn, pid, "stars", 10)
            insert_metric(conn, pid, "stars", 20)
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT metric_value FROM metrics"
            " WHERE project_id = ? AND metric_name = 'stars'",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 20

    def test_insert_bom_component(self, db_path: Path) -> None:
        """BOM component is inserted with all fields."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_bom_component(
                conn,
                pid,
                reference="R1",
                component_name="Resistor",
                quantity=10,
                unit_cost=0.05,
                manufacturer="Yageo",
                part_number="RC0805FR-074K7L",
            )
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT reference, quantity, unit_cost, part_number"
            " FROM bom_components WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "R1"
        assert row[1] == 10
        assert abs(row[2] - 0.05) < 1e-6
        assert row[3] == "RC0805FR-074K7L"

    def test_insert_bom_sanitizes_garbage_mpn(
        self, db_path: Path,
    ) -> None:
        """Garbage part_number values are converted to NULL."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            for garbage in [
                "", "?", "-", "eBay", "Custom", "$0.00",
                "https://lcsc.com/product/123",
                "N/A", "wamoyer.com",
            ]:
                insert_bom_component(
                    conn, pid,
                    component_name=f"Part for {garbage}",
                    part_number=garbage,
                )
        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT part_number FROM bom_components WHERE project_id = ?",
            (pid,),
        ).fetchall()
        conn.close()
        assert all(row[0] is None for row in rows)

    def test_insert_bom_preserves_valid_mpn(
        self, db_path: Path,
    ) -> None:
        """Valid part numbers pass through sanitization unchanged."""
        valid_mpns = [
            "LM7805", "ATmega328P", "WS2812B", "NRF24L01",
            "RC0805FR-074K7L", "10K",
        ]
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            for mpn in valid_mpns:
                insert_bom_component(
                    conn, pid, component_name="Part", part_number=mpn,
                )
        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT part_number FROM bom_components "
            "WHERE project_id = ? ORDER BY id",
            (pid,),
        ).fetchall()
        conn.close()
        assert [row[0] for row in rows] == valid_mpns

    def test_insert_publication(self, db_path: Path) -> None:
        """Publication is inserted with OpenAlex-like fields."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_publication(
                conn,
                pid,
                doi="10.1234/test",
                title="Test Paper",
                publication_year=2024,
                journal="Test Journal",
                cited_by_count=42,
                open_access=True,
            )
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT doi, cited_by_count, open_access"
            " FROM publications WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "10.1234/test"
        assert row[1] == 42
        assert row[2] == 1

    def test_insert_contributor(self, db_path: Path) -> None:
        """Contributor is inserted with name and permission."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_contributor(conn, pid, name="Alice", permission="admin")
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT name, permission FROM contributors WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "Alice"
        assert row[1] == "admin"

    def test_upsert_repo_metrics(self, db_path: Path) -> None:
        """Repo metrics are inserted and updated on conflict."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            upsert_repo_metrics(conn, pid, stars=100, forks=20, has_bom=True)
            upsert_repo_metrics(conn, pid, stars=150, forks=25, has_bom=False)
        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT stars, forks, has_bom FROM repo_metrics "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 150
        assert row[1] == 25
        assert row[2] == 0  # updated from True to False

    def test_insert_bom_file_path(self, db_path: Path) -> None:
        """BOM file paths are inserted and duplicates are ignored."""
        with transaction(db_path) as conn:
            pid = upsert_project(conn, source="t", source_id="1", name="P")
            insert_bom_file_path(conn, pid, "hardware/bom.csv")
            insert_bom_file_path(conn, pid, "hardware/bom.csv")  # dup
            insert_bom_file_path(conn, pid, "pcb/BOM_v2.xlsx")
        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT file_path FROM bom_file_paths "
            "WHERE project_id = ? ORDER BY file_path",
            (pid,),
        ).fetchall()
        conn.close()
        assert [r[0] for r in rows] == [
            "hardware/bom.csv",
            "pcb/BOM_v2.xlsx",
        ]


class TestSanitizePartNumber:
    """Tests for part number sanitization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, None),
            ("", None),
            ("  ", None),
            ("?", None),
            ("-", None),
            ("~", None),
            ("Custom", None),
            ("custom", None),
            ("eBay", None),
            ("AliExpress", None),
            ("N/A", None),
            ("n/a", None),
            ("null", None),
            ("none", None),
            ("TBD", None),
            ("$0.00", None),
            ("$1.23", None),
            ("https://lcsc.com/product/123", None),
            ("http://example.org/part", None),
            ("AliExpress: https://ali.com/item", None),
            ("wamoyer.com", None),
            ("shop.ebay.com/part", None),
            ("LM7805", "LM7805"),
            ("ATmega328P", "ATmega328P"),
            ("  WS2812B  ", "WS2812B"),
            ("RC0805FR-074K7L", "RC0805FR-074K7L"),
            ("10K", "10K"),
            ("NRF24L01", "NRF24L01"),
            ("1N4148", "1N4148"),
        ],
    )
    def test_sanitize(self, raw: str | None, expected: str | None) -> None:
        """Sanitize filters garbage and preserves valid MPNs."""
        assert sanitize_part_number(raw) == expected
