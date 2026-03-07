"""Tests for BOM component normalization enrichment."""

from pathlib import Path

import pytest

from osh_datasets.db import init_db, open_connection
from osh_datasets.enrichment.bom_normalize import (
    canonicalize_manufacturer,
    classify_component,
    enrich_bom_components,
    extract_value,
    normalize_footprint,
)

# ── classify_component ───────────────────────────────────────────


class TestClassifyByRefdes:
    """Reference designator classification (highest priority)."""

    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            ("R1", "resistor"),
            ("R12", "resistor"),
            ("r3", "resistor"),
            ("C5", "capacitor"),
            ("c22", "capacitor"),
            ("L1", "inductor"),
            ("D4", "diode"),
            ("Q1", "transistor"),
            ("U3", "ic"),
            ("u1", "ic"),
            ("J2", "connector"),
            ("P1", "connector"),
            ("F1", "fuse"),
            ("Y1", "crystal"),
            ("X1", "crystal"),
            ("K1", "relay"),
            ("SW1", "switch"),
            ("BT1", "battery"),
            ("TP3", "test_point"),
            ("FB1", "ferrite_bead"),
            ("DS1", "led"),
        ],
    )
    def test_single_designator(self, ref: str, expected: str) -> None:
        """Single reference designators map to correct categories."""
        assert classify_component(ref, None, None) == expected

    def test_comma_separated_designators(self) -> None:
        """First designator in comma-separated list is used."""
        assert classify_component("R1, R2, R3", None, None) == "resistor"

    def test_two_letter_prefix_priority(self) -> None:
        """Two-letter prefixes take precedence over single-letter."""
        assert classify_component("SW1", None, None) == "switch"
        assert classify_component("BT1", None, None) == "battery"

    def test_none_reference(self) -> None:
        """None reference falls through to name/footprint."""
        assert classify_component(None, None, None) is None

    def test_empty_reference(self) -> None:
        """Empty reference falls through."""
        assert classify_component("", None, None) is None

    def test_non_standard_reference(self) -> None:
        """Non-standard reference like G*** returns None."""
        assert classify_component("G***", None, None) is None


class TestClassifyByName:
    """Component name keyword classification (medium priority)."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("10k resistor", "resistor"),
            ("100nf capacitor", "capacitor"),
            ("led red", "led"),
            ("rgb led", "led"),
            ("schottky diode", "diode"),
            ("push button", "switch"),
            ("pin header", "connector"),
            ("arduino uno", "ic"),
            ("esp8266", "ic"),
            ("atmega328p", "ic"),
            ("nrf24l01", "ic"),
            ("m3 bolt", "mechanical"),
            ("3d printed parts", "mechanical"),
            ("jumper wires", "wire"),
            ("buzzer", "sensor"),
            ("battery", "battery"),
            ("ldo", "voltage_regulator"),
            ("mosfet", "transistor"),
            ("ferrite bead", "ferrite_bead"),
        ],
    )
    def test_name_keywords(self, name: str, expected: str) -> None:
        """Name keywords map to correct categories."""
        assert classify_component(None, name, None) == expected

    def test_value_only_resistor(self) -> None:
        """Bare value like '10k' matches resistor pattern."""
        assert classify_component(None, "10k", None) == "resistor"

    def test_value_only_capacitor(self) -> None:
        """Bare capacitor value like '100nf' matches."""
        assert classify_component(None, "100nf", None) == "capacitor"

    def test_refdes_overrides_name(self) -> None:
        """Reference designator takes priority over name."""
        assert classify_component("R1", "led", None) == "resistor"


class TestClassifyByFootprint:
    """Footprint hint classification (lowest priority)."""

    def test_resistor_smd_prefix(self) -> None:
        """EDA library prefix 'Resistor_SMD:' classifies."""
        result = classify_component(None, None, "Resistor_SMD:R_0603_1608Metric")
        assert result == "resistor"

    def test_sot23_transistor(self) -> None:
        """SOT-23 package suggests transistor."""
        assert classify_component(None, None, "SOT-23") == "transistor"

    def test_dip_ic(self) -> None:
        """DIP package suggests IC."""
        assert classify_component(None, None, "DIP-8") == "ic"


# ── canonicalize_manufacturer ────────────────────────────────────


class TestCanonicalizeManufacturer:
    """Manufacturer name canonicalization."""

    @pytest.mark.parametrize(
        ("raw", "expected_name", "expected_dist"),
        [
            ("Yageo", "Yageo", 0),
            ("YAGEO", "Yageo", 0),
            ("TI", "Texas Instruments", 0),
            ("ti", "Texas Instruments", 0),
            ("ST Micro", "STMicroelectronics", 0),
            ("Atmel", "Microchip Technology", 0),
            ("Linear Tech", "Analog Devices", 0),
            ("Maxim", "Analog Devices", 0),
            ("Cypress", "Infineon Technologies", 0),
            ("SAMSUNG(三星)", "Samsung Electro-Mechanics", 0),
            ("Murata Electronics", "Murata", 0),
        ],
    )
    def test_canonical_mapping(
        self, raw: str, expected_name: str, expected_dist: int
    ) -> None:
        """Known manufacturers map to canonical names."""
        name, is_dist = canonicalize_manufacturer(raw)
        assert name == expected_name
        assert is_dist == expected_dist

    @pytest.mark.parametrize(
        "raw",
        [
            "Digikey",
            "Mouser",
            "LCSC",
            "Amazon",
            "Farnell",
            "McMaster-Carr",
            "SparkFun",
            "Adafruit",
        ],
    )
    def test_distributors_flagged(self, raw: str) -> None:
        """Distributors are flagged with is_distributor=1."""
        _, is_dist = canonicalize_manufacturer(raw)
        assert is_dist == 1

    @pytest.mark.parametrize(
        "raw",
        ["Na", "na", "DNP", "none", "Generic", "", "  "],
    )
    def test_garbage_returns_none(self, raw: str) -> None:
        """Garbage values return (None, None)."""
        name, is_dist = canonicalize_manufacturer(raw)
        assert name is None
        assert is_dist is None

    def test_none_input(self) -> None:
        """None input returns (None, None)."""
        assert canonicalize_manufacturer(None) == (None, None)

    def test_unmapped_passthrough(self) -> None:
        """Unmapped values pass through title-cased."""
        name, is_dist = canonicalize_manufacturer("obscure mfr corp")
        assert name == "Obscure Mfr Corp"
        assert is_dist is None


# ── normalize_footprint ──────────────────────────────────────────


class TestNormalizeFootprint:
    """Footprint string normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected_code"),
        [
            ("0603", "0603"),
            ("0402", "0402"),
            ("0805", "0805"),
            ("1206", "1206"),
            ("R0603", "0603"),
            ("C0402", "0402"),
            ("603", "0603"),
            ("402", "0402"),
            ("805", "0805"),
        ],
    )
    def test_imperial_sizes(self, raw: str, expected_code: str) -> None:
        """Imperial size codes normalize correctly."""
        code, mount = normalize_footprint(raw)
        assert code == expected_code
        assert mount == "smd"

    def test_kicad_path(self) -> None:
        """Full KiCad library path extracts size code."""
        code, mount = normalize_footprint("Resistor_SMD:R_0603_1608Metric")
        assert code == "0603"
        assert mount == "smd"

    def test_kicad_with_handsolder(self) -> None:
        """KiCad path with HandSolder suffix strips cleanly."""
        code, mount = normalize_footprint("R_0402_1005Metric_Pad0.72x0.64mm_HandSolder")
        assert code == "0402"
        assert mount == "smd"

    def test_capacitor_smd_path(self) -> None:
        """Capacitor SMD library path works."""
        code, mount = normalize_footprint("Capacitor_SMD:C_0402_1005Metric")
        assert code == "0402"
        assert mount == "smd"

    @pytest.mark.parametrize(
        ("raw", "expected_code"),
        [
            ("SOT-23", "SOT-23"),
            ("SOT23", "SOT-23"),
            ("sot-23", "SOT-23"),
            ("SOT-23-5", "SOT-23-5"),
            ("SOT23-5", "SOT-23-5"),
            ("SOT-223", "SOT-223"),
            ("SOT223", "SOT-223"),
        ],
    )
    def test_sot_canonicalization(
        self, raw: str, expected_code: str,
    ) -> None:
        """SOT variants all canonicalize to hyphenated form."""
        code, mount = normalize_footprint(raw)
        assert code == expected_code
        assert mount == "smd"

    def test_named_package_dip(self) -> None:
        """DIP-8 recognized as THT."""
        code, mount = normalize_footprint("DIP-8")
        assert code == "DIP-8"
        assert mount == "tht"

    def test_named_package_dip_no_hyphen(self) -> None:
        """DIP8 normalizes to DIP-8."""
        code, mount = normalize_footprint("DIP8")
        assert code == "DIP-8"
        assert mount == "tht"

    def test_named_package_qfn(self) -> None:
        """QFN-32 recognized as SMD."""
        code, mount = normalize_footprint("QFN-32")
        assert code == "QFN-32"
        assert mount == "smd"

    def test_named_package_qfn_no_hyphen(self) -> None:
        """QFN32 normalizes to QFN-32."""
        code, mount = normalize_footprint("QFN32")
        assert code == "QFN-32"
        assert mount == "smd"

    def test_lqfp_preserved(self) -> None:
        """LQFP-64 doesn't get a spurious hyphen mid-prefix."""
        code, mount = normalize_footprint("LQFP-64")
        assert code == "LQFP-64"
        assert mount == "smd"

    def test_imperial_in_text(self) -> None:
        """Imperial code in descriptive text like '0603 (1608 metric)'."""
        code, mount = normalize_footprint("0603 (1608 metric)")
        assert code == "0603"
        assert mount == "smd"

    def test_none_input(self) -> None:
        """None input returns (None, None)."""
        assert normalize_footprint(None) == (None, None)

    def test_empty_string(self) -> None:
        """Empty string returns (None, None)."""
        assert normalize_footprint("") == (None, None)

    def test_unparseable(self) -> None:
        """Unparseable footprint returns (None, None)."""
        assert normalize_footprint("buzzardLabel") == (None, None)


# ── extract_value ────────────────────────────────────────────────


class TestExtractValue:
    """Electrical value extraction."""

    @pytest.mark.parametrize(
        ("text", "category", "expected_val", "expected_unit"),
        [
            ("10kohm", "resistor", 10_000.0, "ohm"),
            ("4.7kohm", "resistor", 4_700.0, "ohm"),
            ("220ohm", "resistor", 220.0, "ohm"),
            ("1mohm", "resistor", 0.001, "ohm"),
            ("100nf", "capacitor", 1e-7, "F"),
            ("10uf", "capacitor", 1e-5, "F"),
            ("22pf", "capacitor", 2.2e-11, "F"),
            ("4.7uf", "capacitor", 4.7e-6, "F"),
            ("1mh", "inductor", 0.001, "H"),
            ("10uh", "inductor", 1e-5, "H"),
            ("100nh", "inductor", 1e-7, "H"),
        ],
    )
    def test_standard_notation(
        self,
        text: str,
        category: str,
        expected_val: float,
        expected_unit: str,
    ) -> None:
        """Standard notation values parse correctly."""
        val, unit = extract_value(text, category)
        assert unit == expected_unit
        assert val is not None
        assert abs(val - expected_val) < expected_val * 1e-6

    @pytest.mark.parametrize(
        ("text", "expected_val", "expected_unit"),
        [
            ("4k7", 4_700.0, "ohm"),
            ("2k2", 2_200.0, "ohm"),
            ("1k5", 1_500.0, "ohm"),
            ("4r7", 4.7, "ohm"),
            ("0r1", 0.1, "ohm"),
        ],
    )
    def test_r_notation(
        self,
        text: str,
        expected_val: float,
        expected_unit: str,
    ) -> None:
        """R-notation values parse correctly."""
        val, unit = extract_value(text, "resistor")
        assert unit == expected_unit
        assert val is not None
        assert abs(val - expected_val) < max(expected_val * 1e-6, 1e-9)

    def test_bare_multiplier_resistor(self) -> None:
        """Bare '10k' with resistor category -> 10000 ohm."""
        val, unit = extract_value("10k", "resistor")
        assert val == 10_000.0
        assert unit == "ohm"

    def test_bare_multiplier_non_resistor(self) -> None:
        """Bare '10k' without resistor category returns None."""
        val, unit = extract_value("10k", None)
        assert val is None
        assert unit is None

    def test_none_input(self) -> None:
        """None input returns (None, None)."""
        assert extract_value(None, None) == (None, None)

    def test_empty_string(self) -> None:
        """Empty string returns (None, None)."""
        assert extract_value("", None) == (None, None)

    def test_non_value_text(self) -> None:
        """Non-value text like 'arduino uno' returns None."""
        assert extract_value("arduino uno", "ic") == (None, None)


# ── Integration tests ────────────────────────────────────────────


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database with schema and test BOM data."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = open_connection(db_path)

    # Ensure component_normalized column exists
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bom_components)").fetchall()}
    if "component_normalized" not in cols:
        conn.execute("ALTER TABLE bom_components ADD COLUMN component_normalized TEXT")

    # Insert a test project
    conn.execute(
        "INSERT INTO projects "
        "(source, source_id, name, url) "
        "VALUES ('test', 'p1', 'Test Project', 'https://example.com')"
    )

    # Insert test BOM components
    test_data = [
        (1, "R1", "10kohm", "10kohm", "Yageo", None, "R_0603_1608Metric"),
        (1, "C2", "100nf", "100nf", "KEMET", None, "C_0402_1005Metric"),
        (1, "U1", "atmega328p", "atmega328p", "Atmel", "ATMEGA328P-AU", "TQFP-32"),
        (1, None, "m3 bolt", "m3 bolt", "McMaster-Carr", None, None),
        (1, "D1", "led", "led", "Na", None, None),
    ]
    conn.executemany(
        "INSERT INTO bom_components "
        "(project_id, reference, component_name, "
        "component_normalized, manufacturer, "
        "part_number, footprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        test_data,
    )
    conn.commit()
    conn.close()
    return db_path


class TestIntegration:
    """Integration tests with temporary database."""

    def test_adds_columns_and_populates(self, tmp_db: Path) -> None:
        """Enrichment adds columns and populates data."""
        count = enrich_bom_components(tmp_db)
        assert count == 5

        conn = open_connection(tmp_db)
        cols = {
            r[1] for r in conn.execute("PRAGMA table_info(bom_components)").fetchall()
        }
        assert "component_category" in cols
        assert "manufacturer_canonical" in cols
        assert "manufacturer_is_distributor" in cols
        assert "footprint_normalized" in cols
        assert "footprint_mount_type" in cols
        assert "value_numeric" in cols
        assert "value_unit" in cols

        # Check R1 was classified correctly
        row = conn.execute(
            "SELECT component_category, manufacturer_canonical, "
            "manufacturer_is_distributor, footprint_normalized, "
            "footprint_mount_type, value_numeric, value_unit "
            "FROM bom_components WHERE reference = 'R1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "resistor"
        assert row[1] == "Yageo"
        assert row[2] == 0
        assert row[3] == "0603"
        assert row[4] == "smd"
        assert row[5] == 10_000.0
        assert row[6] == "ohm"

        # Check U1 manufacturer canonicalization
        row = conn.execute(
            "SELECT manufacturer_canonical FROM bom_components WHERE reference = 'U1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Microchip Technology"

        # Check garbage manufacturer -> None
        row = conn.execute(
            "SELECT manufacturer_canonical, "
            "manufacturer_is_distributor "
            "FROM bom_components WHERE reference = 'D1'"
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None

        # Check distributor flagged
        row = conn.execute(
            "SELECT manufacturer_canonical, "
            "manufacturer_is_distributor "
            "FROM bom_components "
            "WHERE reference IS NULL AND "
            "component_name = 'm3 bolt'"
        ).fetchone()
        assert row is not None
        assert row[0] == "McMaster-Carr"
        assert row[1] == 1

        conn.close()

    def test_idempotent(self, tmp_db: Path) -> None:
        """Running enrichment twice produces identical results."""
        enrich_bom_components(tmp_db)
        conn = open_connection(tmp_db)
        first_run = conn.execute(
            "SELECT id, component_category, "
            "manufacturer_canonical, footprint_normalized, "
            "value_numeric, value_unit "
            "FROM bom_components ORDER BY id"
        ).fetchall()
        conn.close()

        enrich_bom_components(tmp_db)
        conn = open_connection(tmp_db)
        second_run = conn.execute(
            "SELECT id, component_category, "
            "manufacturer_canonical, footprint_normalized, "
            "value_numeric, value_unit "
            "FROM bom_components ORDER BY id"
        ).fetchall()
        conn.close()

        assert first_run == second_run

    def test_indexes_created(self, tmp_db: Path) -> None:
        """All expected indexes are created."""
        enrich_bom_components(tmp_db)
        conn = open_connection(tmp_db)
        indexes = {
            r[1] for r in conn.execute("PRAGMA index_list(bom_components)").fetchall()
        }
        assert "idx_bom_category" in indexes
        assert "idx_bom_mfr_canon" in indexes
        assert "idx_bom_fp_norm" in indexes
        assert "idx_bom_fp_mount" in indexes
        conn.close()
