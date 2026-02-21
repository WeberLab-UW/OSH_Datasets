"""Tests for eBay Browse API scraper and pricing enrichment."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest

from osh_datasets.db import (
    init_db,
    insert_bom_component,
    open_connection,
    transaction,
    upsert_project,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with component_normalized column."""
    path = tmp_path / "test.db"
    init_db(path)
    conn = open_connection(path)
    try:
        conn.execute(
            "ALTER TABLE bom_components "
            "ADD COLUMN component_normalized TEXT"
        )
        conn.commit()
    except Exception:
        pass
    conn.close()
    return path


class TestEbayAuth:
    """Tests for eBay OAuth2 token exchange."""

    def test_get_token_success(self) -> None:
        """Token exchange returns access_token on 200."""
        from osh_datasets.scrapers.ebay import _get_token

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "v^1.1#test_token",
            "expires_in": 7200,
            "token_type": "Application Access Token",
        }

        with patch(
            "osh_datasets.scrapers.ebay.requests.post",
            return_value=mock_resp,
        ):
            token = _get_token("app_id", "app_secret")

        assert token == "v^1.1#test_token"

    def test_get_token_failure(self) -> None:
        """Token exchange raises on non-200."""
        from osh_datasets.scrapers.ebay import _get_token

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch(
            "osh_datasets.scrapers.ebay.requests.post",
            return_value=mock_resp,
        ), pytest.raises(RuntimeError, match="401"):
            _get_token("bad_id", "bad_secret")


class TestEbayBrowse:
    """Tests for eBay Browse API search."""

    def test_search_browse_success(self) -> None:
        """Browse API returns item summaries."""
        from osh_datasets.scrapers.ebay import _search_browse

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 2,
            "itemSummaries": [
                {
                    "itemId": "v1|123",
                    "title": "10K Ohm Resistor Pack",
                    "price": {"value": "3.99", "currency": "USD"},
                    "condition": "New",
                    "seller": {"username": "electronics_store"},
                },
                {
                    "itemId": "v1|456",
                    "title": "10K Resistor 100pcs",
                    "price": {"value": "2.50", "currency": "USD"},
                    "condition": "New",
                    "seller": {"username": "parts_depot"},
                },
            ],
        }

        with patch(
            "osh_datasets.scrapers.ebay.requests.get",
            return_value=mock_resp,
        ):
            items = _search_browse("token", "10K resistor")

        assert len(items) == 2
        assert items[0]["itemId"] == "v1|123"

    def test_search_browse_no_results(self) -> None:
        """Browse API 204 returns empty list."""
        from osh_datasets.scrapers.ebay import _search_browse

        mock_resp = MagicMock()
        mock_resp.status_code = 204

        with patch(
            "osh_datasets.scrapers.ebay.requests.get",
            return_value=mock_resp,
        ):
            items = _search_browse("token", "nonexistent_part_xyz")

        assert items == []

    def test_search_browse_error(self) -> None:
        """Browse API error returns empty list."""
        from osh_datasets.scrapers.ebay import _search_browse

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"

        with patch(
            "osh_datasets.scrapers.ebay.requests.get",
            return_value=mock_resp,
        ):
            items = _search_browse("token", "LM7805")

        assert items == []


class TestEbayExtractPrices:
    """Tests for price extraction from Browse API results."""

    def test_extract_prices(self) -> None:
        """Prices extracted from item summaries."""
        from osh_datasets.scrapers.ebay import _extract_prices

        items: list[dict[str, object]] = [
            {
                "itemId": "v1|123",
                "title": "NRF24L01+ Module",
                "price": {"value": "1.99", "currency": "USD"},
                "condition": "New",
                "seller": {"username": "chip_shop"},
            },
            {
                "itemId": "v1|456",
                "title": "NRF24L01 Transceiver",
                "price": {"value": "3.50", "currency": "USD"},
                "condition": "New",
                "seller": {"username": "parts_usa"},
            },
        ]

        prices = _extract_prices(items, "NRF24L01")
        assert len(prices) == 2
        assert prices[0]["unit_price"] == 1.99
        assert prices[0]["seller"] == "chip_shop"
        assert prices[0]["search_term"] == "NRF24L01"
        assert prices[1]["unit_price"] == 3.50

    def test_extract_prices_no_price(self) -> None:
        """Items without price field are skipped."""
        from osh_datasets.scrapers.ebay import _extract_prices

        items: list[dict[str, object]] = [
            {"itemId": "v1|123", "title": "No Price Item"},
        ]
        assert _extract_prices(items, "test") == []

    def test_extract_prices_invalid_value(self) -> None:
        """Items with non-numeric price are skipped."""
        from osh_datasets.scrapers.ebay import _extract_prices

        items: list[dict[str, object]] = [
            {
                "itemId": "v1|123",
                "title": "Bad Price",
                "price": {"value": "N/A", "currency": "USD"},
            },
        ]
        assert _extract_prices(items, "test") == []

    def test_extract_prices_empty(self) -> None:
        """Empty items list returns empty prices."""
        from osh_datasets.scrapers.ebay import _extract_prices

        assert _extract_prices([], "test") == []


class TestEbayEnrichment:
    """Tests for eBay pricing enrichment loader."""

    def test_enrich_from_ebay(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """eBay prices are loaded into component_prices."""
        from osh_datasets.enrichment.pricing import enrich_from_ebay

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
                "mpn": "",
                "title": "Red LED 5mm Pack of 100",
                "seller": "led_store",
                "unit_price": 2.99,
                "currency": "USD",
                "condition": "New",
                "item_id": "v1|789",
                "price_date": "2026-02-20",
            },
        ]
        json_path = tmp_path / "ebay_prices.json"
        json_path.write_bytes(orjson.dumps(prices_json))

        count = enrich_from_ebay(db_path, json_path)
        assert count == 1

        conn = open_connection(db_path)
        row = conn.execute(
            "SELECT distributor, unit_price, price_source "
            "FROM component_prices WHERE bom_component_id = ?",
            (bom_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "ebay:led_store"
        assert abs(row[1] - 2.99) < 1e-6
        assert row[2] == "ebay"

    def test_enrich_from_ebay_missing_file(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Returns 0 when JSON file doesn't exist."""
        from osh_datasets.enrichment.pricing import enrich_from_ebay

        count = enrich_from_ebay(db_path, tmp_path / "nope.json")
        assert count == 0

    def test_enrich_from_ebay_empty_file(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Returns 0 for empty JSON array."""
        from osh_datasets.enrichment.pricing import enrich_from_ebay

        json_path = tmp_path / "empty.json"
        json_path.write_bytes(orjson.dumps([]))

        count = enrich_from_ebay(db_path, json_path)
        assert count == 0


class TestEbayGetUniqueSearchTerms:
    """Tests for search term deduplication."""

    def test_deduplication(self, db_path: Path) -> None:
        """Components sharing an MPN are grouped."""
        from osh_datasets.scrapers.ebay import get_unique_search_terms

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(
                conn, pid, component_name="LED", part_number="WS2812B",
            )
            insert_bom_component(
                conn, pid, component_name="LED Strip", part_number="WS2812B",
            )
            insert_bom_component(
                conn, pid, component_name="Resistor 10K",
            )

        terms = get_unique_search_terms(db_path)
        term_dict = {str(t["search_term"]).lower(): t for t in terms}

        assert "ws2812b" in term_dict
        ws_ids = term_dict["ws2812b"]["bom_component_ids"]
        assert isinstance(ws_ids, list)
        assert len(ws_ids) == 2

    def test_mpn_first_ordering(self, db_path: Path) -> None:
        """MPN-bearing terms sort before name-only terms."""
        from osh_datasets.scrapers.ebay import get_unique_search_terms

        with transaction(db_path) as conn:
            pid = upsert_project(
                conn, source="t", source_id="1", name="P",
            )
            insert_bom_component(
                conn, pid, component_name="Generic Cap",
            )
            insert_bom_component(
                conn, pid, component_name="IC", part_number="ATmega328P",
            )

        terms = get_unique_search_terms(db_path)
        assert len(terms) == 2
        assert terms[0]["has_mpn"] is True
        assert str(terms[0]["search_term"]) == "ATmega328P"
