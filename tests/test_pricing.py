"""Tests for BOM component pricing pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest

from osh_datasets.db import (
    init_db,
    insert_bom_component,
    open_connection,
    transaction,
    upsert_component_price,
    upsert_project,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database and return its path."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestComponentPricesTable:
    """Tests for the component_prices table and upsert helper."""

    def test_table_exists(self, db_path: Path) -> None:
        """component_prices table is created during init."""
        conn = open_connection(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "component_prices" in tables

    def test_upsert_inserts(self, db_path: Path) -> None:
        """New price record is inserted correctly."""
        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(
                conn, pid, component_name="10k Resistor",
            )

        conn = open_connection(db_path)
        bom_id = conn.execute(
            "SELECT id FROM bom_components LIMIT 1"
        ).fetchone()[0]

        upsert_component_price(
            conn, bom_id,
            matched_mpn="RC0805JR-0710KL",
            distributor="DigiKey",
            unit_price=0.10,
            currency="USD",
            quantity_break=1,
            price_date="2026-02-20",
            price_source="nexar",
        )
        conn.commit()

        row = conn.execute(
            "SELECT matched_mpn, distributor, unit_price, currency, "
            "quantity_break, price_source "
            "FROM component_prices WHERE bom_component_id = ?",
            (bom_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "RC0805JR-0710KL"
        assert row[1] == "DigiKey"
        assert abs(row[2] - 0.10) < 1e-6
        assert row[3] == "USD"
        assert row[4] == 1
        assert row[5] == "nexar"

    def test_upsert_updates_on_conflict(self, db_path: Path) -> None:
        """Duplicate (bom_component_id, distributor, qty) updates price."""
        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(conn, pid, component_name="LED")

        conn = open_connection(db_path)
        bom_id = conn.execute(
            "SELECT id FROM bom_components LIMIT 1"
        ).fetchone()[0]

        upsert_component_price(
            conn, bom_id,
            distributor="Mouser",
            unit_price=0.50,
            price_date="2026-01-01",
            price_source="nexar",
        )
        upsert_component_price(
            conn, bom_id,
            distributor="Mouser",
            unit_price=0.45,
            price_date="2026-02-01",
            price_source="nexar",
        )
        conn.commit()

        row = conn.execute(
            "SELECT unit_price, price_date FROM component_prices "
            "WHERE bom_component_id = ?",
            (bom_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert abs(row[0] - 0.45) < 1e-6
        assert row[1] == "2026-02-01"

    def test_index_exists(self, db_path: Path) -> None:
        """Index on bom_component_id is created."""
        conn = open_connection(db_path)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'component_prices'"
        ).fetchall()
        conn.close()
        names = {r[0] for r in indexes}
        assert "idx_comp_prices_bom" in names


class TestNexarScraper:
    """Tests for Nexar scraper helper functions."""

    def test_get_token_success(self) -> None:
        """Token exchange returns access_token on 200."""
        from osh_datasets.scrapers.nexar import _get_token

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "test_token_123",
            "expires_in": 86400,
        }

        with patch("osh_datasets.scrapers.nexar.requests.post",
                    return_value=mock_resp):
            token = _get_token("client_id", "client_secret")

        assert token == "test_token_123"

    def test_get_token_failure(self) -> None:
        """Token exchange raises on non-200."""
        from osh_datasets.scrapers.nexar import _get_token

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("osh_datasets.scrapers.nexar.requests.post",
                    return_value=mock_resp):
            with pytest.raises(RuntimeError, match="401"):
                _get_token("bad_id", "bad_secret")

    def test_extract_prices(self) -> None:
        """Prices are extracted from a valid Nexar response."""
        from osh_datasets.scrapers.nexar import _extract_prices

        response = {
            "data": {
                "supSearchMpn": {
                    "hits": 1,
                    "results": [
                        {
                            "part": {
                                "mpn": "RC0805JR-0710KL",
                                "name": "10k Resistor",
                                "manufacturer": {"name": "Yageo"},
                                "category": {"name": "Resistors"},
                                "medianPrice1000": {
                                    "quantity": 1000,
                                    "price": 0.003,
                                    "currency": "USD",
                                },
                                "sellers": [
                                    {
                                        "company": {"name": "DigiKey"},
                                        "offers": [
                                            {
                                                "prices": [
                                                    {
                                                        "quantity": 1,
                                                        "price": 0.10,
                                                        "currency": "USD",
                                                    },
                                                    {
                                                        "quantity": 100,
                                                        "price": 0.02,
                                                        "currency": "USD",
                                                    },
                                                ],
                                                "inventoryLevel": 50000,
                                            }
                                        ],
                                    }
                                ],
                            }
                        }
                    ],
                }
            }
        }

        prices = _extract_prices(response, "10k resistor")
        assert len(prices) == 2
        assert prices[0]["distributor"] == "DigiKey"
        assert prices[0]["unit_price"] == 0.10
        assert prices[0]["quantity_break"] == 1
        assert prices[1]["quantity_break"] == 100

    def test_extract_prices_empty_response(self) -> None:
        """Empty response returns no prices."""
        from osh_datasets.scrapers.nexar import _extract_prices

        prices = _extract_prices({}, "nothing")
        assert prices == []

    def test_extract_prices_no_sellers_uses_median(self) -> None:
        """Falls back to medianPrice1000 when no sellers."""
        from osh_datasets.scrapers.nexar import _extract_prices

        response = {
            "data": {
                "supSearchMpn": {
                    "hits": 1,
                    "results": [
                        {
                            "part": {
                                "mpn": "RARE-PART",
                                "name": "Rare",
                                "manufacturer": {"name": "Acme"},
                                "category": {"name": "ICs"},
                                "medianPrice1000": {
                                    "quantity": 1000,
                                    "price": 5.00,
                                    "currency": "USD",
                                },
                                "sellers": [],
                            }
                        }
                    ],
                }
            }
        }

        prices = _extract_prices(response, "RARE-PART")
        assert len(prices) == 1
        assert prices[0]["distributor"] == "median"
        assert prices[0]["unit_price"] == 5.00


class TestPartsTableScraper:
    """Tests for PartsTable scraper helper functions."""

    def test_mcp_call_success(self) -> None:
        """Successful MCP call parses SSE response."""
        from osh_datasets.scrapers.partstable import _mcp_call

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/event-stream"}
        mock_resp.text = (
            'event: message\n'
            'data: {"jsonrpc":"2.0","id":1,"result":{"content":[]}}\n'
        )

        with patch("osh_datasets.scrapers.partstable.requests.post",
                    return_value=mock_resp):
            result = _mcp_call("tools/call", {"name": "test"})

        assert result is not None
        assert result["jsonrpc"] == "2.0"

    def test_mcp_call_failure(self) -> None:
        """Failed MCP call returns None."""
        from osh_datasets.scrapers.partstable import _mcp_call

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("osh_datasets.scrapers.partstable.requests.post",
                    return_value=mock_resp):
            result = _mcp_call("tools/call", {"name": "test"})

        assert result is None

    def test_extract_content(self) -> None:
        """Content items are extracted from MCP response."""
        from osh_datasets.scrapers.partstable import _extract_content

        response: dict[str, object] = {
            "result": {
                "content": [
                    {"type": "text", "text": "data here"},
                ]
            }
        }
        content = _extract_content(response)
        assert len(content) == 1
        assert content[0]["text"] == "data here"

    def test_extract_content_empty(self) -> None:
        """Empty response returns empty list."""
        from osh_datasets.scrapers.partstable import _extract_content

        assert _extract_content({}) == []
        assert _extract_content({"result": {}}) == []


class TestPricingEnrichment:
    """Tests for the pricing enrichment loader."""

    def test_enrich_from_nexar(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Nexar prices are loaded into component_prices."""
        from osh_datasets.enrichment.pricing import enrich_from_nexar

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(conn, pid, component_name="LED")

        bom_id_conn = open_connection(db_path)
        bom_id = bom_id_conn.execute(
            "SELECT id FROM bom_components LIMIT 1"
        ).fetchone()[0]
        bom_id_conn.close()

        prices_json = [
            {
                "bom_component_id": bom_id,
                "search_term": "LED",
                "mpn": "OSRAM-LED-5MM",
                "distributor": "DigiKey",
                "unit_price": 0.25,
                "currency": "USD",
                "quantity_break": 1,
                "price_date": "2026-02-20",
            }
        ]
        json_path = tmp_path / "nexar_prices.json"
        json_path.write_bytes(orjson.dumps(prices_json))

        count = enrich_from_nexar(db_path, json_path)
        assert count == 1

        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT matched_mpn, unit_price, price_source "
            "FROM component_prices WHERE bom_component_id = ?",
            (bom_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "OSRAM-LED-5MM"
        assert abs(row[1] - 0.25) < 1e-6
        assert row[2] == "nexar"

    def test_enrich_from_nexar_missing_file(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Returns 0 when JSON file doesn't exist."""
        from osh_datasets.enrichment.pricing import enrich_from_nexar

        count = enrich_from_nexar(db_path, tmp_path / "nope.json")
        assert count == 0

    def test_enrich_from_nexar_empty_file(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Returns 0 for empty JSON array."""
        from osh_datasets.enrichment.pricing import enrich_from_nexar

        json_path = tmp_path / "empty.json"
        json_path.write_bytes(orjson.dumps([]))

        count = enrich_from_nexar(db_path, json_path)
        assert count == 0


class TestFredPpi:
    """Tests for FRED PPI historical price adjustment."""

    def test_estimate_historical_price(self) -> None:
        """PPI ratio adjusts price correctly."""
        from osh_datasets.enrichment.fred_ppi import (
            estimate_historical_price,
        )

        ppi = {"2018": 90.0, "2026": 120.0}
        result = estimate_historical_price(1.00, "2026", "2018", ppi)
        assert result is not None
        assert abs(result - 0.75) < 1e-6

    def test_estimate_missing_year(self) -> None:
        """Returns None when target year is missing from PPI."""
        from osh_datasets.enrichment.fred_ppi import (
            estimate_historical_price,
        )

        ppi = {"2026": 120.0}
        result = estimate_historical_price(1.00, "2026", "2010", ppi)
        assert result is None

    def test_add_historical_no_api_key(self, db_path: Path) -> None:
        """Returns 0 gracefully when FRED_API_KEY is not set."""
        from osh_datasets.enrichment.fred_ppi import add_historical_prices

        with patch.dict("os.environ", {}, clear=False):
            # Ensure FRED_API_KEY is not set
            import os
            os.environ.pop("FRED_API_KEY", None)
            count = add_historical_prices(db_path)

        assert count == 0

    def test_fetch_ppi_series(self) -> None:
        """PPI series is parsed from FRED JSON response."""
        from osh_datasets.enrichment.fred_ppi import _fetch_ppi_series

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "observations": [
                {"date": "2020-01-01", "value": "100.0"},
                {"date": "2021-01-01", "value": "105.5"},
                {"date": "2022-01-01", "value": "."},
                {"date": "2023-01-01", "value": "110.2"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("osh_datasets.enrichment.fred_ppi.requests.get",
                    return_value=mock_resp):
            ppi = _fetch_ppi_series("fake_key")

        assert ppi["2020"] == 100.0
        assert ppi["2021"] == 105.5
        assert "2022" not in ppi
        assert ppi["2023"] == 110.2
