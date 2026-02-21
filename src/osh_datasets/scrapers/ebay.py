"""Fetch component pricing from the eBay Browse API.

Uses the eBay Browse API to search for active listings by MPN or
component name. Optionally resolves MPNs to ePIDs via the Catalog API
for higher-precision results.

Requires ``EBAY_CLIENT_ID`` and ``EBAY_CLIENT_SECRET`` in ``.env``.
"""

import time
from datetime import UTC, datetime
from pathlib import Path

import orjson
import requests

from osh_datasets.config import DB_PATH, get_logger, require_env
from osh_datasets.db import open_connection, sanitize_part_number
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_CATALOG_URL = (
    "https://api.ebay.com/commerce/catalog/v1_beta/product_summary/search"
)
_SCOPE = "https://api.ebay.com/oauth/api_scope"

# eBay category IDs for electronic components
_ELECTRONICS_CATEGORY = "175673"

# Daily call limits: Browse 5k, Catalog 10k
_MAX_BROWSE_CALLS = 4500  # Leave headroom
_BROWSE_LIMIT = 10  # Items per search (keep responses small)


def _get_token(client_id: str, client_secret: str) -> str:
    """Exchange client credentials for an eBay OAuth2 application token.

    Args:
        client_id: eBay application client ID.
        client_secret: eBay application client secret.

    Returns:
        Bearer access token string.

    Raises:
        RuntimeError: If token exchange fails.
    """
    import base64

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data=f"grant_type=client_credentials&scope={_SCOPE}",
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"eBay token exchange failed: {resp.status_code} {resp.text}"
        )
    token_data: dict[str, object] = resp.json()
    token = token_data.get("access_token")
    if not isinstance(token, str):
        raise RuntimeError("No access_token in eBay response")
    return token


def _search_browse(
    token: str,
    query: str,
    category_id: str | None = _ELECTRONICS_CATEGORY,
    limit: int = _BROWSE_LIMIT,
) -> list[dict[str, object]]:
    """Search eBay Browse API for active listings.

    Args:
        token: Bearer access token.
        query: Search keywords (MPN or component name).
        category_id: Optional eBay category filter.
        limit: Max results per query.

    Returns:
        List of item summary dicts from the response.
    """
    params: dict[str, str] = {
        "q": query,
        "limit": str(limit),
        "filter": "buyingOptions:{FIXED_PRICE},"
                  "conditionIds:{1000|1500|1750|2000|2500}",
    }
    if category_id:
        params["category_ids"] = category_id

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(
            _BROWSE_URL, params=params, headers=headers, timeout=30,
        )
        if resp.status_code == 204:
            return []
        if resp.status_code != 200:
            logger.warning(
                "eBay Browse HTTP %d for %r: %s",
                resp.status_code, query, resp.text[:200],
            )
            return []

        data: dict[str, object] = resp.json()
        items = data.get("itemSummaries")
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
        return []
    except requests.RequestException as exc:
        logger.error("eBay Browse request failed for %r: %s", query, exc)
        return []


def _extract_prices(
    items: list[dict[str, object]],
    search_term: str,
) -> list[dict[str, object]]:
    """Extract pricing records from eBay Browse API item summaries.

    Args:
        items: List of item summary dicts from Browse API.
        search_term: Original search query for reference.

    Returns:
        List of price record dicts with keys: search_term, mpn,
        title, seller, unit_price, currency, condition, listing_url,
        price_date.
    """
    prices: list[dict[str, object]] = []
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    for item in items:
        price_obj = item.get("price")
        if not isinstance(price_obj, dict):
            continue

        value_str = price_obj.get("value")
        currency = price_obj.get("currency", "USD")
        if not isinstance(value_str, str):
            continue

        try:
            unit_price = float(value_str)
        except ValueError:
            continue

        title = item.get("title", "")
        item_id = item.get("itemId", "")
        seller_info = item.get("seller")
        seller = ""
        if isinstance(seller_info, dict):
            seller = str(seller_info.get("username", ""))

        condition = item.get("condition", "")

        prices.append({
            "search_term": search_term,
            "mpn": "",
            "title": str(title),
            "seller": seller,
            "unit_price": unit_price,
            "currency": str(currency),
            "condition": str(condition),
            "item_id": str(item_id),
            "price_date": today,
        })

    return prices


def get_unique_search_terms(
    db_path: Path = DB_PATH,
) -> list[dict[str, object]]:
    """Get deduplicated component search terms for eBay pricing.

    Groups components by search term so each unique term is queried
    once. MPN matches come first, then sorted by coverage.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        List of dicts with keys: search_term, has_mpn, bom_component_ids.
    """
    conn = open_connection(db_path)
    rows = conn.execute(
        """\
        SELECT bc.id, bc.part_number, bc.component_normalized,
               bc.component_name
        FROM bom_components bc
        LEFT JOIN component_prices cp
            ON cp.bom_component_id = bc.id
            AND cp.price_source = 'ebay'
        WHERE cp.id IS NULL
          AND (bc.part_number IS NOT NULL
               OR bc.component_name IS NOT NULL
               OR bc.component_normalized IS NOT NULL)
        ORDER BY bc.part_number IS NOT NULL DESC, bc.id
        """
    ).fetchall()
    conn.close()

    term_map: dict[str, dict[str, object]] = {}
    for row in rows:
        bom_id: int = row[0]
        mpn = row[1]
        normalized = row[2]
        raw_name = row[3]

        # Validate MPN; fall through to name if garbage
        clean_mpn = sanitize_part_number(str(mpn)) if mpn else None
        if clean_mpn:
            search = clean_mpn
            has_mpn = True
        elif normalized and str(normalized).strip():
            search = str(normalized).strip()
            has_mpn = False
        elif raw_name and str(raw_name).strip():
            search = str(raw_name).strip()
            has_mpn = False
        else:
            continue

        key = search.lower()
        if key not in term_map:
            term_map[key] = {
                "search_term": search,
                "has_mpn": has_mpn,
                "bom_component_ids": [],
            }
        ids = term_map[key]["bom_component_ids"]
        if isinstance(ids, list):
            ids.append(bom_id)

    return sorted(
        term_map.values(),
        key=lambda t: (
            not t["has_mpn"],
            -(len(t["bom_component_ids"])
              if isinstance(t["bom_component_ids"], list) else 0),
        ),
    )


class EbayScraper(BaseScraper):
    """Fetch component pricing via the eBay Browse API.

    Reads deduplicated component MPNs/names from the database,
    queries eBay for active listing prices, and fans results out
    to all matching bom_component IDs.

    Requires ``EBAY_CLIENT_ID`` and ``EBAY_CLIENT_SECRET`` in ``.env``.
    Output: ``data/raw/ebay/ebay_prices.json``
    """

    source_name = "ebay"

    def scrape(self) -> Path:
        """Query eBay Browse API for component pricing.

        Returns:
            Path to the output JSON file.
        """
        client_id = require_env("EBAY_CLIENT_ID")
        client_secret = require_env("EBAY_CLIENT_SECRET")

        logger.info("Authenticating with eBay API")
        token = _get_token(client_id, client_secret)
        logger.info("eBay token acquired")

        terms = get_unique_search_terms()
        if not terms:
            logger.warning("No components to price via eBay, skipping")
            out = self.output_dir / "ebay_prices.json"
            out.write_bytes(orjson.dumps([]))
            return out

        capped = terms[:_MAX_BROWSE_CALLS]
        total_components = sum(
            len(t["bom_component_ids"])
            for t in capped
            if isinstance(t["bom_component_ids"], list)
        )
        logger.info(
            "Querying eBay: %d unique terms (of %d) covering %d components",
            len(capped), len(terms), total_components,
        )

        all_prices: list[dict[str, object]] = []
        for i, term_info in enumerate(capped):
            search = str(term_info["search_term"])
            bom_ids = term_info["bom_component_ids"]
            if not isinstance(bom_ids, list) or not bom_ids:
                continue

            if i > 0 and i % 500 == 0:
                logger.info(
                    "[%d/%d] Progress: %d prices so far",
                    i, len(capped), len(all_prices),
                )

            items = _search_browse(token, search)
            if not items:
                continue

            prices = _extract_prices(items, search)
            for bom_id in bom_ids:
                for p in prices:
                    record = dict(p)
                    record["bom_component_id"] = bom_id
                    all_prices.append(record)

            # Respect rate limits (~5 req/sec is safe)
            time.sleep(0.2)

        logger.info(
            "Fetched %d price records from eBay for %d queries",
            len(all_prices), len(capped),
        )

        out = self.output_dir / "ebay_prices.json"
        out.write_bytes(orjson.dumps(all_prices, option=orjson.OPT_INDENT_2))
        return out
