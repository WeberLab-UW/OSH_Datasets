"""Integration tests for data loaders using real data files."""

from pathlib import Path

import pytest

from osh_datasets.config import DATA_DIR
from osh_datasets.db import init_db, open_connection


def _skip_if_missing(path: Path) -> None:
    """Skip the test if the required data file does not exist."""
    if not path.exists():
        pytest.skip(f"Data file not found: {path}")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database and return its path."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


def _count_projects(db_path: Path, source: str) -> int:
    """Count projects for a given source."""
    conn = open_connection(db_path)
    row = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE source = ?", (source,)
    ).fetchone()
    conn.close()
    assert row is not None
    return int(row[0])


class TestHackadayLoader:
    """Test Hackaday loader with real data."""

    def test_loads_projects(self, db_path: Path) -> None:
        """Hackaday loader inserts expected number of projects."""
        data_file = DATA_DIR / "cleaned" / "hackaday" / "hackaday_cleaned.csv"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.hackaday import HackadayLoader

        count = HackadayLoader().run(db_path)
        assert count > 5000
        assert _count_projects(db_path, "hackaday") == count

    def test_has_tags(self, db_path: Path) -> None:
        """At least some projects have tags."""
        data_file = DATA_DIR / "cleaned" / "hackaday" / "hackaday_cleaned.csv"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.hackaday import HackadayLoader

        HackadayLoader().run(db_path)

        conn = open_connection(db_path)
        row = conn.execute("SELECT COUNT(*) FROM tags").fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 0

    def test_has_components(self, db_path: Path) -> None:
        """Hackaday projects with components populate bom_components."""
        data_file = DATA_DIR / "cleaned" / "hackaday" / "hackaday_cleaned.csv"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.hackaday import HackadayLoader

        HackadayLoader().run(db_path)

        conn = open_connection(db_path)
        row = conn.execute("SELECT COUNT(*) FROM bom_components").fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 1000


class TestOshwaLoader:
    """Test OSHWA loader with real data."""

    def test_loads_projects(self, db_path: Path) -> None:
        """OSHWA loader inserts expected number of projects."""
        data_file = DATA_DIR / "cleaned" / "oshwa" / "oshwa_cleaned.csv"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.oshwa import OshwaLoader

        count = OshwaLoader().run(db_path)
        assert count > 3000
        assert _count_projects(db_path, "oshwa") == count

    def test_has_licenses(self, db_path: Path) -> None:
        """OSHWA projects should have license records."""
        data_file = DATA_DIR / "cleaned" / "oshwa" / "oshwa_cleaned.csv"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.oshwa import OshwaLoader

        OshwaLoader().run(db_path)

        conn = open_connection(db_path)
        row = conn.execute("SELECT COUNT(*) FROM licenses").fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 0


class TestKitspaceLoader:
    """Test Kitspace loader with real data."""

    def test_loads_projects(self, db_path: Path) -> None:
        """Kitspace loader inserts projects."""
        data_file = DATA_DIR / "kitspace_results.json"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.kitspace import KitspaceLoader

        count = KitspaceLoader().run(db_path)
        assert count > 100

    def test_has_bom(self, db_path: Path) -> None:
        """Kitspace projects should have BOM components."""
        data_file = DATA_DIR / "kitspace_results.json"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.kitspace import KitspaceLoader

        KitspaceLoader().run(db_path)

        conn = open_connection(db_path)
        row = conn.execute("SELECT COUNT(*) FROM bom_components").fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 0


class TestOhxLoader:
    """Test OHX loader with real data."""

    def test_loads_projects(self, db_path: Path) -> None:
        """OHX loader inserts projects."""
        data_file = DATA_DIR / "ohx_allPubs_extract.json"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.ohx import OhxLoader

        count = OhxLoader().run(db_path)
        assert count > 500

    def test_has_publications(self, db_path: Path) -> None:
        """OHX projects should have linked publications."""
        data_file = DATA_DIR / "ohx_allPubs_extract.json"
        _skip_if_missing(data_file)

        from osh_datasets.loaders.ohx import OhxLoader

        OhxLoader().run(db_path)

        conn = open_connection(db_path)
        row = conn.execute("SELECT COUNT(*) FROM publications").fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 0


class TestMendeleyLoader:
    """Tests for Mendeley Data loader."""

    def test_loads_from_scraped_json(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Mendeley loader parses OAI-PMH records into projects."""
        import orjson

        from osh_datasets.loaders.mendeley import MendeleyLoader

        raw_dir = tmp_path / "raw" / "mendeley"
        raw_dir.mkdir(parents=True)
        records = [
            {
                "oai_identifier": "oai:data.mendeley.com/abc123def.2",
                "dataset_id": "",
                "datestamp": "2024-01-15T10:00:00Z",
                "doi": "",
                "title": "Test Dataset",
                "creator": ["Alice", "Bob"],
                "description": "A test dataset for OSH",
                "subject": ["hardware", "sensors"],
                "publisher": "Mendeley Data",
                "date": "2024-01-15T10:00:00Z",
                "type": "Dataset",
                "format": [],
                "rights": "CC BY 4.0",
                "mendeley_url": "",
            }
        ]
        (raw_dir / "mendeley_datasets.json").write_bytes(
            orjson.dumps(records)
        )

        loader = MendeleyLoader(data_dir=tmp_path)
        count = loader.load(db_path)
        assert count == 1

        conn = open_connection(db_path)

        # Project created with derived fields
        row = conn.execute(
            "SELECT name, author, url FROM projects "
            "WHERE source = 'mendeley'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Test Dataset"
        assert row[1] == "Alice; Bob"
        assert "abc123def" in str(row[2])

        # License
        lic = conn.execute(
            "SELECT license_name FROM licenses WHERE project_id = 1"
        ).fetchone()
        assert lic is not None
        assert "CC BY" in str(lic[0])

        # Tags
        tags = conn.execute(
            "SELECT tag FROM tags WHERE project_id = 1 ORDER BY tag"
        ).fetchall()
        assert [t[0] for t in tags] == ["hardware", "sensors"]

        # Publication with derived DOI
        pub = conn.execute(
            "SELECT doi FROM publications WHERE project_id = 1"
        ).fetchone()
        assert pub is not None
        assert pub[0] == "10.17632/abc123def"

        conn.close()

    def test_skips_missing_json(self, db_path: Path, tmp_path: Path) -> None:
        """Returns 0 when no JSON file exists."""
        from osh_datasets.loaders.mendeley import MendeleyLoader

        loader = MendeleyLoader(data_dir=tmp_path)
        assert loader.load(db_path) == 0


class TestHardwareioBomLoader:
    """Tests for Hardware.io BOM normalization and loading."""

    def test_normalizes_variant_columns(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """BOM columns from different EDA tools are coalesced."""
        from osh_datasets.db import transaction, upsert_project
        from osh_datasets.loaders.hardwareio import load_hardwareio_bom

        # Insert a project to match against
        with transaction(db_path) as conn:
            upsert_project(
                conn,
                source="hardwareio",
                source_id="test-proj",
                name="Test Board",
            )

        # Write a BOM CSV with KiCad-style columns
        csv = tmp_path / "bom.csv"
        csv.write_text(
            "project_name,Designator,Value,Qty,Package,Manufacturer,MPN\n"
            "Test Board,R1,10k,2,0805,Yageo,RC0805\n"
            "Test Board,C1,100nF,1,0402,Murata,GRM155\n"
        )

        count = load_hardwareio_bom(db_path, csv)
        assert count == 2

        conn = open_connection(db_path)
        rows = conn.execute(
            "SELECT reference, component_name, quantity, "
            "manufacturer, part_number "
            "FROM bom_components ORDER BY reference"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == "C1"
        assert rows[0][1] == "100nF"
        assert rows[0][2] == 1
        assert rows[0][3] == "Murata"
        assert rows[0][4] == "GRM155"
        assert rows[1][0] == "R1"
        assert rows[1][1] == "10k"
        assert rows[1][2] == 2

    def test_coalesces_eagle_columns(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Eagle-style column names are coalesced correctly."""
        from osh_datasets.db import transaction, upsert_project
        from osh_datasets.loaders.hardwareio import load_hardwareio_bom

        with transaction(db_path) as conn:
            upsert_project(
                conn,
                source="hardwareio",
                source_id="eagle-proj",
                name="Eagle Board",
            )

        csv = tmp_path / "bom.csv"
        csv.write_text(
            "project_name,Part,Description,Quantity,MF,"
            "Manufacturer Part\n"
            "Eagle Board,U1,MCU,1,STMicro,STM32F103\n"
        )

        count = load_hardwareio_bom(db_path, csv)
        assert count == 1

        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT reference, component_name, quantity, "
            "manufacturer, part_number FROM bom_components"
        ).fetchone()
        conn.close()

        assert row is not None
        # Part goes to component_name (Name variants)
        # Description also maps to component_name but Part is
        # lower priority; Description wins via coalesce order
        assert row[1] == "MCU"  # Description > Part
        assert row[2] == 1
        assert row[3] == "STMicro"
        assert row[4] == "STM32F103"

    def test_skips_unmatched_projects(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Rows for unknown projects are skipped."""
        from osh_datasets.loaders.hardwareio import load_hardwareio_bom

        csv = tmp_path / "bom.csv"
        csv.write_text(
            "project_name,Value,Qty\n"
            "NonexistentProject,10k,1\n"
        )

        count = load_hardwareio_bom(db_path, csv)
        assert count == 0

    def test_handles_missing_csv(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Returns 0 when BOM CSV does not exist."""
        from osh_datasets.loaders.hardwareio import load_hardwareio_bom

        missing = tmp_path / "no_such_file.csv"
        count = load_hardwareio_bom(db_path, missing)
        assert count == 0

    def test_parses_quantity_with_formatting(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Quantities with commas and decimals are parsed."""
        from osh_datasets.db import transaction, upsert_project
        from osh_datasets.loaders.hardwareio import load_hardwareio_bom

        with transaction(db_path) as conn:
            upsert_project(
                conn,
                source="hardwareio",
                source_id="qty-proj",
                name="Qty Test",
            )

        csv = tmp_path / "bom.csv"
        csv.write_text(
            "project_name,Reference,Value,Qty,Cost\n"
            "Qty Test,R1,10k,\"1,000\",$2.50\n"
        )

        count = load_hardwareio_bom(db_path, csv)
        assert count == 1

        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT quantity, unit_cost FROM bom_components"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 1000
        assert abs(row[1] - 2.50) < 0.01


class TestAllLoadersSmoke:
    """Smoke test: run all loaders together."""

    def test_load_all(self, db_path: Path) -> None:
        """All loaders run without errors and produce records."""
        from osh_datasets.load_all import load_all

        results = load_all(db_path)
        assert sum(results.values()) > 0
        for source, count in results.items():
            assert count >= 0, f"{source} returned negative count"
