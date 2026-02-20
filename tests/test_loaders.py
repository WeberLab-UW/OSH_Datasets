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


class TestAllLoadersSmoke:
    """Smoke test: run all loaders together."""

    def test_load_all(self, db_path: Path) -> None:
        """All loaders run without errors and produce records."""
        from osh_datasets.load_all import load_all

        results = load_all(db_path)
        assert sum(results.values()) > 0
        for source, count in results.items():
            assert count >= 0, f"{source} returned negative count"
