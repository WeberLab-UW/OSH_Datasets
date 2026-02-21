"""Quick test of the OEMSecrets API against unpriced MPNs in the DB."""

import time
from pathlib import Path

import orjson
import requests

from osh_datasets.config import DB_PATH, require_env
from osh_datasets.db import open_connection

API_URL = "https://oemsecretsapi.com/partsearch"


def get_unpriced_mpns(db_path: Path, limit: int = 10) -> list[str]:
    """Fetch MPNs that have no pricing data yet.

    Args:
        db_path: Path to the SQLite database.
        limit: Max MPNs to return.

    Returns:
        List of part_number strings.
    """
    conn = open_connection(db_path)
    rows = conn.execute(
        """\
        SELECT DISTINCT bc.part_number
        FROM bom_components bc
        LEFT JOIN component_prices cp ON cp.bom_component_id = bc.id
        WHERE cp.id IS NULL
          AND bc.part_number IS NOT NULL
          AND LENGTH(bc.part_number) > 2
        ORDER BY bc.part_number
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def search_oemsecrets(
    api_key: str, mpn: str,
) -> dict[str, object]:
    """Query OEMSecrets for a single MPN.

    Args:
        api_key: OEMSecrets API key.
        mpn: Manufacturer part number to search.

    Returns:
        Parsed JSON response dict.
    """
    resp = requests.get(
        API_URL,
        params={
            "apiKey": api_key,
            "searchTerm": mpn,
            "currency": "USD",
        },
        timeout=30,
    )
    return resp.json()  # type: ignore[no-any-return]


def main() -> None:
    """Test OEMSecrets API with a sample of unpriced MPNs."""
    api_key = require_env("OEMSECRETS_API_KEY")
    mpns = get_unpriced_mpns(DB_PATH, limit=10)
    print(f"Testing {len(mpns)} unpriced MPNs against OEMSecrets API\n")

    # Dump first raw response to see structure
    first_result = search_oemsecrets(api_key, mpns[0])
    print("--- Raw response for first MPN ---")
    print(orjson.dumps(first_result, option=orjson.OPT_INDENT_2).decode()[:2000])
    print("---\n")

    hits = 0
    for i, mpn in enumerate(mpns):
        if i > 0:
            time.sleep(2)  # Respect rate limits
        result = search_oemsecrets(api_key, mpn)
        status = result.get("status", "?")
        parts_returned = result.get("parts_returned", 0)
        stock = result.get("stock", [])

        if parts_returned and isinstance(stock, list) and stock:
            hits += 1
            # Collect unique distributors with prices
            distributors: list[str] = []
            for item in stock[:5]:
                if not isinstance(item, dict):
                    continue
                dist = item.get("distributor", {})
                dist_name = (
                    dist.get("name", "?")
                    if isinstance(dist, dict) else "?"
                )
                qty = item.get("quantity_in_stock", 0)
                prices_obj = item.get("prices", {})
                usd = (
                    prices_obj.get("USD", [])
                    if isinstance(prices_obj, dict) else []
                )
                price_str = ""
                if isinstance(usd, list) and usd:
                    p = usd[0]
                    if isinstance(p, dict):
                        price_str = f"${p.get('price', '?')}"
                distributors.append(
                    f"{dist_name}({qty} stk, {price_str})"
                )
            print(
                f"  [HIT] {mpn}: {parts_returned} results "
                f"-- {', '.join(distributors)}"
            )
        else:
            print(f"  [MISS] {mpn}: status={status}")

    print(f"\nSummary: {hits}/{len(mpns)} MPNs found pricing data")


if __name__ == "__main__":
    main()
