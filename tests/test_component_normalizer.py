"""Tests for the BOM component name normalizer."""

from pathlib import Path

import pytest

from osh_datasets.component_normalizer import normalize
from osh_datasets.db import (
    init_db,
    insert_bom_component,
    open_connection,
    transaction,
    upsert_project,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database and return its path."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestNormalize:
    """Unit tests for the normalize() pure function."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Tier 1: text cleanup
            ("  10K Resistor  ", "10k resistor"),
            ("", ""),
            ("LED  Red   5mm", "led red 5mm"),
            ("N/A", ""),
            ("null", ""),
            ("-", ""),
            ("PCB", "pcb"),
            ("TI TMP007", "ti tmp007"),
            # Tier 1: unicode replacement
            ("10\u00b5F", "10uf"),
            ("10k\u03a9", "10k"),
            ("100\u2013200ohm", "100-200ohm"),
            ("\u00b130%", "+-30%"),
            # Tier 2: resistance
            ("10kohm", "10k"),
            ("4.7kohm", "4.7k"),
            ("1mohm", "1m"),
            ("220R", "220ohm"),
            ("10 ohm", "10ohm"),
            ("100ohm", "100ohm"),
            # Tier 2: capacitance (explicit units)
            ("100nF", "100nf"),
            ("10uF", "10uf"),
            ("22pF", "22pf"),
            ("10 uF", "10uf"),
            # Tier 2: capacitance (bare suffix expansion)
            ("100n", "100nf"),
            ("10u", "10uf"),
            ("22p", "22pf"),
            ("100n capacitor", "100nf capacitor"),
            # Tier 2: inductance
            ("10 uh", "10uh"),
            ("100nh", "100nh"),
            ("1mh", "1mh"),
            # Tier 3: articles
            ("The Capacitor", "capacitor"),
            ("an led", "led"),
            ("a resistor", "resistor"),
            # Tier 3: abbreviation expansion
            ("res 10k", "resistor 10k"),
            ("cap 100nf", "capacitor 100nf"),
            ("ind 10uh", "inductor 10uh"),
            # No false positives on abbreviations inside words
            ("pressure sensor", "pressure sensor"),
            ("capacitive touch", "capacitive touch"),
            ("indirect", "indirect"),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        """Normalize produces expected output."""
        assert normalize(raw) == expected

    def test_bare_suffix_no_false_positive(self) -> None:
        """Bare n/p/u should not fire inside part numbers."""
        # SN74100N lowercased -- the n is not preceded by \b\d+
        assert normalize("SN74100N") == "sn74100n"
        # CPU -- u is not preceded by digits
        assert normalize("CPU") == "cpu"


class TestAddNormalizedColumn:
    """Integration tests for column creation and population."""

    def test_adds_column_and_normalizes(self, db_path: Path) -> None:
        """Column is created and rows are normalized."""
        from osh_datasets.component_normalizer import (
            add_component_normalized_column,
        )

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(conn, pid, component_name="10K Resistor")
            insert_bom_component(conn, pid, component_name="100nF")
            insert_bom_component(conn, pid, component_name=None)

        count = add_component_normalized_column(db_path)
        assert count == 3

        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT component_name, component_normalized "
            "FROM bom_components ORDER BY id"
        ).fetchall()
        conn.close()

        assert rows[0][1] == "10k resistor"
        assert rows[1][1] == "100nf"
        assert rows[2][1] == ""

    def test_idempotent(self, db_path: Path) -> None:
        """Calling twice does not error or double-add columns."""
        from osh_datasets.component_normalizer import (
            add_component_normalized_column,
        )

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(conn, pid, component_name="LED")

        add_component_normalized_column(db_path)
        count = add_component_normalized_column(db_path)
        assert count == 1

        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT component_normalized FROM bom_components"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "led"

    def test_index_created(self, db_path: Path) -> None:
        """Index on component_normalized is created."""
        from osh_datasets.component_normalizer import (
            add_component_normalized_column,
        )

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(conn, pid, component_name="LED")

        add_component_normalized_column(db_path)

        conn = open_connection(db_path)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'bom_components'"
        ).fetchall()
        conn.close()
        index_names = {r[0] for r in indexes}
        assert "idx_bom_comp_norm" in index_names
