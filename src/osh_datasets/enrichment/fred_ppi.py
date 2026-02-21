"""Adjust current component prices to historical equivalents using FRED PPI.

Uses the Producer Price Index for Semiconductor and Other Electronic
Component Manufacturing (series PCU33443344) from the Federal Reserve
Economic Data (FRED) API to deflate current prices to the year a
project was created.

Requires a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
Set ``FRED_API_KEY`` in ``.env`` to enable. If not set, this module
logs a warning and returns 0 (non-fatal).
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import requests

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_PPI_SERIES = "PCU33443344"


def _fetch_ppi_series(api_key: str) -> dict[str, float]:
    """Fetch annual PPI observations from FRED.

    Args:
        api_key: FRED API key.

    Returns:
        Mapping from year (int as str) to PPI value.
    """
    params = {
        "series_id": _PPI_SERIES,
        "api_key": api_key,
        "file_type": "json",
        "frequency": "a",
        "observation_start": "2000-01-01",
    }
    resp = requests.get(_FRED_BASE, params=params, timeout=30)
    resp.raise_for_status()

    data: dict[str, object] = resp.json()
    observations = data.get("observations")
    if not isinstance(observations, list):
        return {}

    ppi: dict[str, float] = {}
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        date_str = obs.get("date")
        value_str = obs.get("value")
        if not isinstance(date_str, str) or not isinstance(value_str, str):
            continue
        if value_str == ".":
            continue
        try:
            year = date_str[:4]
            ppi[year] = float(value_str)
        except ValueError:
            continue

    return ppi


def estimate_historical_price(
    current_price: float,
    current_year: str,
    target_year: str,
    ppi_series: dict[str, float],
) -> float | None:
    """Adjust a current price to a historical year using PPI ratio.

    Args:
        current_price: Price in today's dollars.
        current_year: Year the price was fetched (e.g. ``"2026"``).
        target_year: Year to adjust to (e.g. ``"2018"``).
        ppi_series: Year-to-PPI mapping from :func:`_fetch_ppi_series`.

    Returns:
        Estimated historical price, or None if PPI data missing.
    """
    ppi_now = ppi_series.get(current_year)
    ppi_then = ppi_series.get(target_year)
    if ppi_now is None or ppi_then is None or ppi_now == 0:
        return None
    return current_price * (ppi_then / ppi_now)


def add_historical_prices(db_path: Path = DB_PATH) -> int:
    """Add PPI-adjusted historical prices for components with project dates.

    For each component_price record, looks up the parent project's
    ``created_at`` year and computes an adjusted price. Stores the
    result as a new record with ``price_source = 'fred_ppi_adjusted'``
    and ``distributor = 'historical_estimate'``.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Number of historical price estimates added.
    """
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logger.warning(
            "FRED_API_KEY not set; skipping historical price adjustment"
        )
        return 0

    logger.info("Fetching PPI series %s from FRED", _PPI_SERIES)
    ppi = _fetch_ppi_series(api_key)
    if not ppi:
        logger.warning("No PPI data returned from FRED")
        return 0

    current_year = datetime.now(tz=UTC).strftime("%Y")
    logger.info(
        "PPI data: %d years (%s to %s)",
        len(ppi), min(ppi), max(ppi),
    )

    conn = open_connection(db_path)

    # Get current prices joined with project creation year
    rows = conn.execute(
        """\
        SELECT cp.bom_component_id, cp.matched_mpn, cp.unit_price,
               cp.currency, p.created_at, cp.price_source
        FROM component_prices cp
        JOIN bom_components bc ON bc.id = cp.bom_component_id
        JOIN projects p ON p.id = bc.project_id
        WHERE cp.price_source != 'fred_ppi_adjusted'
          AND cp.quantity_break = 1
          AND p.created_at IS NOT NULL
          AND cp.unit_price IS NOT NULL
        """
    ).fetchall()

    count = 0
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    for row in rows:
        bom_id: int = row[0]
        matched_mpn: str | None = row[1]
        current_price: float = row[2]
        currency: str = row[3]
        created_at: str = row[4]

        target_year = created_at[:4]
        if not target_year.isdigit():
            continue

        historical = estimate_historical_price(
            current_price, current_year, target_year, ppi,
        )
        if historical is None:
            continue

        # Store as a separate record with distinct source
        conn.execute(
            """\
            INSERT INTO component_prices
                (bom_component_id, matched_mpn, distributor, unit_price,
                 currency, quantity_break, price_date, price_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bom_component_id, distributor, quantity_break)
            DO UPDATE SET
                matched_mpn  = excluded.matched_mpn,
                unit_price   = excluded.unit_price,
                price_date   = excluded.price_date,
                price_source = excluded.price_source
            """,
            (
                bom_id, matched_mpn, "historical_estimate",
                round(historical, 4), currency, 1,
                today, "fred_ppi_adjusted",
            ),
        )
        count += 1

    conn.commit()
    conn.close()

    logger.info("Added %d PPI-adjusted historical price estimates", count)
    return count


if __name__ == "__main__":
    result = add_historical_prices()
    print(f"Added {result} historical price estimates.")
