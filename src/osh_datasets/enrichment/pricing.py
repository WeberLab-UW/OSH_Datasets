"""Load pricing data from Nexar and PartsTable into component_prices.

Reads scraped JSON from each pricing scraper and upserts pricing records
into the database. For components that already have a ``unit_cost``
from the original source (e.g. OHX, Hardware.io), only the current
price is stored for comparison.
"""

from datetime import UTC, datetime
from pathlib import Path

import orjson

from osh_datasets.config import DB_PATH, RAW_DIR, get_logger
from osh_datasets.db import open_connection, upsert_component_price

logger = get_logger(__name__)

_NEXAR_JSON = RAW_DIR / "nexar" / "nexar_prices.json"
_PARTSTABLE_JSON = RAW_DIR / "partstable" / "partstable_prices.json"
_EBAY_JSON = RAW_DIR / "ebay" / "ebay_prices.json"


def enrich_from_nexar(
    db_path: Path = DB_PATH,
    json_path: Path | None = None,
) -> int:
    """Load Nexar pricing JSON into the component_prices table.

    Args:
        db_path: Path to the SQLite database.
        json_path: Path to scraped JSON file. Defaults to
            ``data/raw/nexar/nexar_prices.json``.

    Returns:
        Number of price records upserted.
    """
    if json_path is None:
        json_path = _NEXAR_JSON

    if not json_path.exists():
        logger.warning("No Nexar pricing file at %s", json_path)
        return 0

    with open(json_path, "rb") as fh:
        records: list[dict[str, object]] = orjson.loads(fh.read())

    if not records:
        logger.info("Nexar pricing file is empty")
        return 0

    conn = open_connection(db_path)
    count = 0

    for record in records:
        bom_id = record.get("bom_component_id")
        if not isinstance(bom_id, int):
            continue

        unit_price = record.get("unit_price")
        if unit_price is None:
            continue

        price_date = record.get("price_date")
        if not isinstance(price_date, str):
            continue

        distributor = str(record.get("distributor", ""))
        currency = str(record.get("currency", "USD"))
        mpn = record.get("mpn")
        matched_mpn = str(mpn) if mpn else None

        qty_break = record.get("quantity_break")
        quantity_break = int(str(qty_break)) if qty_break is not None else 1

        upsert_component_price(
            conn,
            bom_id,
            matched_mpn=matched_mpn,
            distributor=distributor,
            unit_price=float(str(unit_price)),
            currency=currency,
            quantity_break=quantity_break,
            price_date=price_date,
            price_source="nexar",
        )
        count += 1

    conn.commit()
    conn.close()

    logger.info("Upserted %d price records from Nexar", count)
    return count


def _parse_partstable_price(
    text: str,
) -> tuple[float, str] | None:
    """Extract a numeric price and currency from PartsTable text.

    Args:
        text: Price string like ``"$1.23"`` or ``"1.23 USD"``.

    Returns:
        Tuple of (price, currency) or None if unparseable.
    """
    text = text.strip()
    if not text:
        return None

    currency = "USD"
    if text.startswith("$"):
        text = text[1:]
    elif text.startswith("EUR") or text.startswith("eur"):
        currency = "EUR"
        text = text[3:].strip()

    try:
        return float(text.split()[0]), currency
    except (ValueError, IndexError):
        return None


def enrich_from_partstable(
    db_path: Path = DB_PATH,
    json_path: Path | None = None,
) -> int:
    """Load PartsTable pricing JSON into the component_prices table.

    Args:
        db_path: Path to the SQLite database.
        json_path: Path to scraped JSON file. Defaults to
            ``data/raw/partstable/partstable_prices.json``.

    Returns:
        Number of price records upserted.
    """
    if json_path is None:
        json_path = _PARTSTABLE_JSON

    if not json_path.exists():
        logger.warning("No PartsTable pricing file at %s", json_path)
        return 0

    with open(json_path, "rb") as fh:
        records: list[dict[str, object]] = orjson.loads(fh.read())

    if not records:
        logger.info("PartsTable pricing file is empty")
        return 0

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    conn = open_connection(db_path)
    count = 0

    for record in records:
        bom_id = record.get("bom_component_id")
        if not isinstance(bom_id, int):
            continue

        search_results = record.get("search_results")
        if not isinstance(search_results, list) or not search_results:
            continue

        # Extract pricing from the first content block
        for content in search_results:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if not isinstance(text, str):
                continue

            # Try to parse structured JSON from content text
            try:
                parsed: object = orjson.loads(text.encode())
            except (orjson.JSONDecodeError, ValueError):
                continue

            if not isinstance(parsed, dict):
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            count += _store_partstable_item(
                                conn, bom_id, item, today,
                            )
                continue

            count += _store_partstable_item(
                conn, bom_id, parsed, today,
            )

    conn.commit()
    conn.close()

    logger.info("Upserted %d price records from PartsTable", count)
    return count


def _store_partstable_item(
    conn: object,
    bom_id: int,
    item: dict[str, object],
    today: str,
) -> int:
    """Store a single PartsTable result as a component price.

    Args:
        conn: Active database connection.
        bom_id: The bom_components.id.
        item: Parsed result dict from PartsTable.
        today: Current date string.

    Returns:
        1 if stored, 0 if skipped.
    """
    import sqlite3

    if not isinstance(conn, sqlite3.Connection):
        return 0

    price_val = item.get("price") or item.get("unitPrice")
    if price_val is None:
        return 0

    if isinstance(price_val, str):
        parsed_price = _parse_partstable_price(price_val)
        if parsed_price is None:
            return 0
        unit_price, currency = parsed_price
    elif isinstance(price_val, (int, float)):
        unit_price = float(price_val)
        currency = str(item.get("currency", "USD"))
    else:
        return 0

    mpn = item.get("mpn") or item.get("partNumber")
    matched_mpn = str(mpn) if mpn else None

    distributor = item.get("distributor") or item.get("vendor") or ""

    upsert_component_price(
        conn,
        bom_id,
        matched_mpn=matched_mpn,
        distributor=str(distributor),
        unit_price=unit_price,
        currency=currency,
        quantity_break=1,
        price_date=today,
        price_source="partstable",
    )
    return 1


def enrich_from_ebay(
    db_path: Path = DB_PATH,
    json_path: Path | None = None,
) -> int:
    """Load eBay pricing JSON into the component_prices table.

    Args:
        db_path: Path to the SQLite database.
        json_path: Path to scraped JSON file. Defaults to
            ``data/raw/ebay/ebay_prices.json``.

    Returns:
        Number of price records upserted.
    """
    if json_path is None:
        json_path = _EBAY_JSON

    if not json_path.exists():
        logger.warning("No eBay pricing file at %s", json_path)
        return 0

    with open(json_path, "rb") as fh:
        records: list[dict[str, object]] = orjson.loads(fh.read())

    if not records:
        logger.info("eBay pricing file is empty")
        return 0

    conn = open_connection(db_path)
    count = 0

    for record in records:
        bom_id = record.get("bom_component_id")
        if not isinstance(bom_id, int):
            continue

        unit_price = record.get("unit_price")
        if unit_price is None:
            continue

        price_date = record.get("price_date")
        if not isinstance(price_date, str):
            continue

        seller = str(record.get("seller", "ebay"))
        currency = str(record.get("currency", "USD"))
        mpn = record.get("mpn")
        matched_mpn = str(mpn) if mpn else None

        upsert_component_price(
            conn,
            bom_id,
            matched_mpn=matched_mpn,
            distributor=f"ebay:{seller}" if seller else "ebay",
            unit_price=float(str(unit_price)),
            currency=currency,
            quantity_break=1,
            price_date=price_date,
            price_source="ebay",
        )
        count += 1

    conn.commit()
    conn.close()

    logger.info("Upserted %d price records from eBay", count)
    return count


def enrich_pricing(db_path: Path = DB_PATH) -> int:
    """Run all pricing enrichment sources.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Total number of price records upserted across all sources.
    """
    total = 0
    total += enrich_from_nexar(db_path)
    total += enrich_from_partstable(db_path)
    total += enrich_from_ebay(db_path)
    logger.info("Total pricing enrichment: %d records", total)
    return total


if __name__ == "__main__":
    result = enrich_pricing()
    print(f"Upserted {result} price records.")
