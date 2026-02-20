"""Unit tests for scrapers with mocked HTTP calls."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Return a temporary output directory."""
    d = tmp_path / "raw"
    d.mkdir()
    return d


# ---------------------------------------------------------------
# BaseScraper
# ---------------------------------------------------------------


class TestBaseScraper:
    """Test BaseScraper ABC interface."""

    def test_run_creates_directory(self, tmp_path: Path) -> None:
        """run() should create the output directory if missing."""
        from osh_datasets.scrapers.base import BaseScraper

        class StubScraper(BaseScraper):
            source_name = "stub"

            def scrape(self) -> Path:
                return self.output_dir / "out.json"

        out = tmp_path / "new_dir"
        scraper = StubScraper(output_dir=out)
        result = scraper.run()
        assert out.exists()
        assert result == out / "out.json"


# ---------------------------------------------------------------
# OSHWA
# ---------------------------------------------------------------


class TestOshwaScraper:
    """Test OSHWA scraper with mocked API responses."""

    @patch.dict("os.environ", {"OSHWA_API_TOKEN": "test-jwt"})
    @patch("osh_datasets.scrapers.oshwa.rate_limited_get")
    @patch("osh_datasets.scrapers.oshwa.build_session")
    def test_paginates_and_saves(
        self,
        mock_session: MagicMock,
        mock_get: MagicMock,
        output_dir: Path,
    ) -> None:
        """Should paginate until items are exhausted."""
        from osh_datasets.scrapers.oshwa import OshwaScraper

        page1 = MagicMock()
        page1.json.return_value = {
            "items": [{"oshwaUid": "US000001"}],
            "total": 1,
        }
        mock_get.return_value = page1

        scraper = OshwaScraper(output_dir=output_dir / "oshwa")
        result = scraper.run()

        assert result.exists()
        data = orjson.loads(result.read_bytes())
        assert len(data) == 1
        assert data[0]["oshwaUid"] == "US000001"


# ---------------------------------------------------------------
# OHR
# ---------------------------------------------------------------


class TestOhrScraper:
    """Test OHR scraper with mocked GitLab API."""

    @patch("osh_datasets.scrapers.ohr.rate_limited_get")
    @patch("osh_datasets.scrapers.ohr.build_session")
    def test_fetches_group_projects(
        self,
        mock_session: MagicMock,
        mock_get: MagicMock,
        output_dir: Path,
    ) -> None:
        """Should fetch paginated group projects."""
        from osh_datasets.scrapers.ohr import OhrScraper

        page1 = MagicMock()
        page1.json.return_value = [
            {
                "id": 1,
                "name": "test-project",
                "namespace": {"id": 10, "name": "ohwr"},
            }
        ]
        page2 = MagicMock()
        page2.json.return_value = []
        mock_get.side_effect = [page1, page2]

        scraper = OhrScraper(output_dir=output_dir / "ohr")
        result = scraper.run()

        assert result.exists()
        data = orjson.loads(result.read_bytes())
        assert len(data) == 1
        assert data[0]["name"] == "test-project"


# ---------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------


class TestOpenAlexScraper:
    """Test OpenAlex scraper with mocked API."""

    @patch("osh_datasets.scrapers.openalex.rate_limited_get")
    @patch("osh_datasets.scrapers.openalex.build_session")
    def test_fetches_dois(
        self,
        mock_session: MagicMock,
        mock_get: MagicMock,
        output_dir: Path,
    ) -> None:
        """Should fetch metadata for each DOI."""
        from osh_datasets.scrapers.openalex import OpenAlexScraper

        resp = MagicMock()
        resp.json.return_value = {
            "id": "W123",
            "doi": "10.1234/test",
            "cited_by_count": 5,
        }
        mock_get.return_value = resp

        out = output_dir / "openalex"
        out.mkdir()
        (out / "dois.txt").write_text("10.1234/test\n")

        scraper = OpenAlexScraper(output_dir=out)
        result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert len(data) == 1
        assert data[0]["cited_by_count"] == 5


# ---------------------------------------------------------------
# OHX
# ---------------------------------------------------------------


class TestOhxScraper:
    """Test OHX XML parser."""

    def test_parses_xml(self, output_dir: Path, tmp_path: Path) -> None:
        """Should extract articles from minimal XML."""
        from osh_datasets.scrapers.ohx import OhxScraper

        xml_content = """<?xml version="1.0"?>
        <articles>
            <article>
                <article-title>Test Hardware</article-title>
            </article>
        </articles>"""
        xml_path = tmp_path / "test.xml"
        xml_path.write_text(xml_content)

        out = output_dir / "ohx"
        out.mkdir(parents=True, exist_ok=True)
        scraper = OhxScraper(output_dir=out)
        result = scraper.scrape(xml_path=xml_path)

        data = orjson.loads(result.read_bytes())
        assert len(data) == 1
        assert data[0]["paper_title"] == "Test Hardware"


# ---------------------------------------------------------------
# PLOS
# ---------------------------------------------------------------


class TestPlosScraper:
    """Test PLOS scraper with mocked HTTP."""

    @patch("osh_datasets.scrapers.plos.rate_limited_get")
    @patch("osh_datasets.scrapers.plos.build_session")
    def test_extracts_das_and_links(
        self,
        mock_session: MagicMock,
        mock_get: MagicMock,
        output_dir: Path,
    ) -> None:
        """Should extract DAS and git links from XML."""
        from osh_datasets.scrapers.plos import PlosScraper

        xml = """<?xml version="1.0"?>
        <article>
            <custom-meta id="data-availability">
                <meta-value>All data at https://github.com/test/repo</meta-value>
            </custom-meta>
        </article>"""
        resp = MagicMock()
        resp.text = xml
        mock_get.return_value = resp

        out = output_dir / "plos"
        out.mkdir()
        (out / "dois.txt").write_text("10.1371/journal.pone.0001\n")

        scraper = PlosScraper(output_dir=out)
        result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert len(data) == 1
        assert data[0]["data_availability_statement"] is not None
        assert len(data[0]["git_repo_links"]) == 1


# ---------------------------------------------------------------
# Hackaday
# ---------------------------------------------------------------


class TestHackadayClient:
    """Test Hackaday client key rotation."""

    def test_key_rotation(self) -> None:
        """Keys should rotate via round-robin."""
        from osh_datasets.scrapers.hackaday import HackadayClient

        client = HackadayClient(["key1", "key2", "key3"])
        keys = [client._next_key() for _ in range(6)]
        # Round-robin: index = (total_requests) % 3
        # total_requests goes 1,2,3,4,5,6 -> indices 1,2,0,1,2,0
        assert keys[0] == "key2"
        assert keys[1] == "key3"
        assert keys[2] == "key1"
        client.close()


# ---------------------------------------------------------------
# Hardware.io
# ---------------------------------------------------------------


class TestHardwareioScraper:
    """Test Hardware.io scraper output format."""

    def test_empty_input(self, output_dir: Path) -> None:
        """Should produce empty JSON when no project list exists."""
        from osh_datasets.scrapers.hardwareio import HardwareioScraper

        scraper = HardwareioScraper(output_dir=output_dir / "hardwareio")
        result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert data == []


# ---------------------------------------------------------------
# Kitspace
# ---------------------------------------------------------------


class TestKitspaceScraper:
    """Test Kitspace scraper output format."""

    def test_empty_when_no_urls(self, output_dir: Path) -> None:
        """Should handle missing URL list gracefully."""
        from osh_datasets.scrapers.kitspace import KitspaceScraper

        scraper = KitspaceScraper(output_dir=output_dir / "kitspace")
        # No URL file and no Selenium, should produce empty-ish output
        with patch(
            "osh_datasets.scrapers.kitspace._discover_urls_lightweight",
            return_value=[],
        ):
            result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert isinstance(data, list)


# ---------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------


class TestGitHubHelpers:
    """Test GitHub URL parsing and BOM detection."""

    def test_extract_owner_repo(self) -> None:
        """Should parse owner/repo from various URL formats."""
        from osh_datasets.scrapers.github import _extract_owner_repo

        assert _extract_owner_repo("https://github.com/owner/repo") == (
            "owner",
            "repo",
        )
        assert _extract_owner_repo("https://github.com/owner/repo.git") == (
            "owner",
            "repo",
        )
        assert _extract_owner_repo("https://github.com/owner/repo/tree/main") == (
            "owner",
            "repo",
        )
        assert _extract_owner_repo("not-a-url") is None

    def test_is_bom_file(self) -> None:
        """Should detect BOM files from various naming patterns."""
        from osh_datasets.scrapers.github import _is_bom_file

        # Should match
        assert _is_bom_file("bom.csv")
        assert _is_bom_file("BOM.xlsx")
        assert _is_bom_file("hardware/bom.csv")
        assert _is_bom_file("pcb/BOM_v2.csv")
        assert _is_bom_file("bill_of_materials.csv")
        assert _is_bom_file("parts_list.csv")
        assert _is_bom_file("components.csv")
        assert _is_bom_file("board-bom.xml")

        # Should not match
        assert not _is_bom_file("README.md")
        assert not _is_bom_file("main.py")
        assert not _is_bom_file("bom.py")  # wrong extension
        assert not _is_bom_file("image.png")

    def test_detect_bom_files(self) -> None:
        """Should scan tree entries and return BOM file paths."""
        from osh_datasets.scrapers.github import _detect_bom_files

        entries = [
            {"path": "README.md", "type": "blob"},
            {"path": "hardware/bom.csv", "type": "blob"},
            {"path": "src/main.py", "type": "blob"},
            {"path": "docs/bill_of_materials.xlsx", "type": "blob"},
            {"path": "hardware", "type": "tree"},  # directories ignored
        ]
        result = _detect_bom_files(entries)
        assert result == ["docs/bill_of_materials.xlsx", "hardware/bom.csv"]


# ---------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------


class TestGitLabScraper:
    """Test GitLab scraper output format."""

    def test_empty_input(self, output_dir: Path) -> None:
        """Should produce empty JSON when no ID file exists."""
        from osh_datasets.scrapers.gitlab import GitLabScraper

        scraper = GitLabScraper(output_dir=output_dir / "gitlab")
        result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert data == []


# ---------------------------------------------------------------
# Mendeley
# ---------------------------------------------------------------


class TestMendeleyScraper:
    """Test Mendeley scraper output format."""

    def test_empty_when_no_urls(self, output_dir: Path) -> None:
        """Should produce empty JSON when no URL file exists."""
        from osh_datasets.scrapers.mendeley import MendeleyScraper

        scraper = MendeleyScraper(output_dir=output_dir / "mendeley")
        result = scraper.run()

        data = orjson.loads(result.read_bytes())
        assert data == []

    def test_extract_dataset_id(self) -> None:
        """Should parse dataset IDs from various URL formats."""
        from osh_datasets.scrapers.mendeley import _extract_dataset_id

        assert _extract_dataset_id(
            "https://data.mendeley.com/datasets/abc123"
        ) == "abc123"
        assert _extract_dataset_id(
            "https://doi.org/10.17632/xyz456.2"
        ) == "xyz456"
        assert _extract_dataset_id(
            "http://dx.doi.org/10.17632/def789.1"
        ) == "def789"
        assert _extract_dataset_id("not-a-url") is None


# ---------------------------------------------------------------
# scrape_all
# ---------------------------------------------------------------


class TestScrapeAll:
    """Test the scrape_all orchestrator."""

    @patch("osh_datasets.scrapers.ALL_SCRAPERS", [])
    def test_empty_scrapers(self) -> None:
        """Should return empty dict when no scrapers registered."""
        from osh_datasets.scrape_all import scrape_all

        results = scrape_all()
        assert results == {}
