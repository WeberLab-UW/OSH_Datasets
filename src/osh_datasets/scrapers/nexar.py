"""Fetch component pricing from the Nexar (Octopart) GraphQL API.

Authenticates via OAuth2 client credentials, queries the supply scope
for part pricing by MPN or keyword, and writes results to JSON.
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

_TOKEN_URL = "https://identity.nexar.com/connect/token"
_GRAPHQL_URL = "https://api.nexar.com/graphql/"

# GraphQL query: batch search up to 20 MPNs via aliases.
# Each alias runs supSearchMpn independently.
_SINGLE_QUERY = """\
query SearchPart($q: String!) {
  supSearchMpn(q: $q, currency: "USD", country: "US", limit: 3) {
    hits
    results {
      part {
        mpn
        name
        manufacturer {
          name
        }
        medianPrice1000 {
          quantity
          price
          currency
        }
        sellers(authorizedOnly: false) {
          company {
            name
          }
          offers {
            prices {
              quantity
              price
              currency
            }
            inventoryLevel
          }
        }
        category {
          name
        }
      }
    }
  }
}
"""


def _get_token(client_id: str, client_secret: str) -> str:
    """Exchange client credentials for an OAuth2 access token.

    Args:
        client_id: Nexar application client ID.
        client_secret: Nexar application client secret.

    Returns:
        Bearer access token string.

    Raises:
        RuntimeError: If token exchange fails.
    """
    resp = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "supply.domain",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Nexar token exchange failed: {resp.status_code} {resp.text}"
        )
    token_data: dict[str, object] = resp.json()
    token = token_data.get("access_token")
    if not isinstance(token, str):
        raise RuntimeError("No access_token in Nexar response")
    return token


def _query_nexar(
    token: str,
    search_term: str,
) -> dict[str, object] | None:
    """Execute a single GraphQL query against Nexar.

    Args:
        token: Bearer access token.
        search_term: MPN or keyword to search.

    Returns:
        Parsed JSON response dict, or None on failure.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = orjson.dumps({
        "query": _SINGLE_QUERY,
        "variables": {"q": search_term},
    })
    try:
        resp = requests.post(
            _GRAPHQL_URL,
            data=payload,
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(
                "Nexar HTTP %d for %r: %s",
                resp.status_code, search_term, resp.text[:200],
            )
            return None
        body: dict[str, object] = resp.json()
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            msg = errors[0].get("message", "") if isinstance(errors[0], dict) else ""
            logger.error("Nexar API error: %s", msg)
            return None
        return body
    except requests.RequestException as exc:
        logger.error("Nexar request failed for %r: %s", search_term, exc)
        return None


def _extract_prices(
    response: dict[str, object],
    search_term: str,
) -> list[dict[str, object]]:
    """Extract pricing records from a Nexar GraphQL response.

    Args:
        response: Parsed GraphQL response.
        search_term: Original search term for reference.

    Returns:
        List of price record dicts with keys: search_term, mpn,
        manufacturer, distributor, unit_price, currency, quantity_break,
        category, price_date.
    """
    prices: list[dict[str, object]] = []
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    data = response.get("data")
    if not isinstance(data, dict):
        return prices

    search = data.get("supSearchMpn")
    if not isinstance(search, dict):
        return prices

    results = search.get("results")
    if not isinstance(results, list):
        return prices

    for result in results:
        if not isinstance(result, dict):
            continue
        part = result.get("part")
        if not isinstance(part, dict):
            continue

        mpn = part.get("mpn", "")
        mfr_data = part.get("manufacturer")
        manufacturer = ""
        if isinstance(mfr_data, dict):
            manufacturer = str(mfr_data.get("name", ""))

        cat_data = part.get("category")
        category = ""
        if isinstance(cat_data, dict):
            category = str(cat_data.get("name", ""))

        # Extract per-seller pricing (qty=1 break preferred)
        sellers = part.get("sellers")
        if isinstance(sellers, list):
            for seller in sellers:
                if not isinstance(seller, dict):
                    continue
                company = seller.get("company")
                distributor = ""
                if isinstance(company, dict):
                    distributor = str(company.get("name", ""))

                offers = seller.get("offers")
                if not isinstance(offers, list):
                    continue
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    offer_prices = offer.get("prices")
                    if not isinstance(offer_prices, list):
                        continue
                    for p in offer_prices:
                        if not isinstance(p, dict):
                            continue
                        prices.append({
                            "search_term": search_term,
                            "mpn": mpn,
                            "manufacturer": manufacturer,
                            "distributor": distributor,
                            "unit_price": p.get("price"),
                            "currency": p.get("currency", "USD"),
                            "quantity_break": p.get("quantity", 1),
                            "category": category,
                            "price_date": today,
                        })

        # Fallback: median price if no sellers
        if not prices:
            median = part.get("medianPrice1000")
            if isinstance(median, dict):
                prices.append({
                    "search_term": search_term,
                    "mpn": mpn,
                    "manufacturer": manufacturer,
                    "distributor": "median",
                    "unit_price": median.get("price"),
                    "currency": median.get("currency", "USD"),
                    "quantity_break": median.get("quantity", 1000),
                    "category": category,
                    "price_date": today,
                })

    return prices


def get_unique_search_terms(
    db_path: Path = DB_PATH,
) -> list[dict[str, object]]:
    """Get deduplicated component search terms mapped to bom_component IDs.

    Groups components by their search term (MPN or normalized name) so
    each unique term is queried only once. Results are ordered with MPN
    matches first, then by number of components sharing that term
    (descending) to maximize pricing coverage per API call.

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
        LEFT JOIN component_prices cp ON cp.bom_component_id = bc.id
        WHERE cp.id IS NULL
          AND (bc.part_number IS NOT NULL
               OR bc.component_name IS NOT NULL
               OR bc.component_normalized IS NOT NULL)
        ORDER BY bc.part_number IS NOT NULL DESC, bc.id
        """
    ).fetchall()
    conn.close()

    # Group bom_component_ids by unique search term
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

    # Sort: MPN first, then by coverage (most components sharing a term)
    terms = sorted(
        term_map.values(),
        key=lambda t: (
            not t["has_mpn"],
            -(len(t["bom_component_ids"])
              if isinstance(t["bom_component_ids"], list) else 0),
        ),
    )
    return terms


_MAX_NEXAR_QUERIES = 100  # Free tier: 100 queries/month


class NexarScraper(BaseScraper):
    """Fetch component pricing via the Nexar/Octopart API.

    Reads deduplicated component MPNs/names from the database,
    queries Nexar for pricing (capped at 100 queries for free tier),
    and fans results out to all matching bom_component IDs.

    Requires ``NEXAR_CLIENT_ID`` and ``NEXAR_CLIENT_SECRET`` in ``.env``.
    Output: ``data/raw/nexar/nexar_prices.json``
    """

    source_name = "nexar"

    def scrape(self) -> Path:
        """Query Nexar for component pricing.

        Returns:
            Path to the output JSON file.
        """
        client_id = require_env("NEXAR_CLIENT_ID")
        client_secret = require_env("NEXAR_CLIENT_SECRET")

        logger.info("Authenticating with Nexar API")
        token = _get_token(client_id, client_secret)
        logger.info("Nexar token acquired")

        terms = get_unique_search_terms()
        if not terms:
            logger.warning("No components to price, skipping")
            out = self.output_dir / "nexar_prices.json"
            out.write_bytes(orjson.dumps([]))
            return out

        capped = terms[:_MAX_NEXAR_QUERIES]
        total_components = sum(
            len(t["bom_component_ids"])
            for t in capped
            if isinstance(t["bom_component_ids"], list)
        )
        logger.info(
            "Querying Nexar: %d unique terms (of %d) covering %d components",
            len(capped), len(terms), total_components,
        )

        all_prices: list[dict[str, object]] = []
        consecutive_failures = 0
        for i, term_info in enumerate(capped):
            search = str(term_info["search_term"])
            bom_ids = term_info["bom_component_ids"]
            if not isinstance(bom_ids, list) or not bom_ids:
                continue

            logger.info(
                "[%d/%d] Querying: %s (%d components)",
                i + 1, len(capped), search, len(bom_ids),
            )

            response = _query_nexar(token, search)
            if response is None:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.error(
                        "Stopping after %d consecutive failures "
                        "(likely quota exhausted)",
                        consecutive_failures,
                    )
                    break
                continue
            consecutive_failures = 0

            prices = _extract_prices(response, search)
            # Fan out prices to every bom_component sharing this term
            for bom_id in bom_ids:
                for p in prices:
                    record = dict(p)
                    record["bom_component_id"] = bom_id
                    all_prices.append(record)

            # Respect rate limits
            time.sleep(1.0)

        logger.info(
            "Fetched %d price records for %d queries",
            len(all_prices), len(capped),
        )

        out = self.output_dir / "nexar_prices.json"
        out.write_bytes(orjson.dumps(all_prices, option=orjson.OPT_INDENT_2))
        return out
