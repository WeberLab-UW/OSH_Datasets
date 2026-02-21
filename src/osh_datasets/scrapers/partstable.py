"""Fetch component pricing from the PartsTable MCP API.

Calls the PartsTable MCP HTTP endpoint directly via JSON-RPC 2.0
to search parts, get price history, and normalize part numbers.
No authentication required.
"""

import time
from pathlib import Path

import orjson
import requests

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_MCP_URL = "https://mcp.partstable.com/mcp"
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _mcp_call(
    method: str,
    params: dict[str, object],
    request_id: int = 1,
) -> dict[str, object] | None:
    """Send a JSON-RPC 2.0 request to the PartsTable MCP endpoint.

    Handles SSE (text/event-stream) responses by extracting the JSON
    payload from the ``data:`` line following an ``event: message`` line.

    Args:
        method: MCP method name (e.g. ``"tools/call"``).
        params: Method parameters.
        request_id: JSON-RPC request identifier.

    Returns:
        Parsed response dict, or None on failure.
    """
    payload = orjson.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    })
    try:
        resp = requests.post(
            _MCP_URL, data=payload, headers=_HEADERS, timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(
                "PartsTable HTTP %d: %s", resp.status_code, resp.text[:200],
            )
            return None

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse_response(resp.text)
        parsed: dict[str, object] = orjson.loads(resp.content)
        return parsed
    except requests.RequestException as exc:
        logger.error("PartsTable request failed: %s", exc)
        return None


def _parse_sse_response(text: str) -> dict[str, object] | None:
    """Extract JSON-RPC payload from an SSE text/event-stream response.

    Args:
        text: Raw SSE response body.

    Returns:
        Parsed JSON-RPC response dict, or None if no data found.
    """
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                parsed: dict[str, object] = orjson.loads(line[6:])
                return parsed
            except orjson.JSONDecodeError:
                continue
    return None


def _call_tool(
    tool_name: str,
    arguments: dict[str, object],
    request_id: int = 1,
) -> dict[str, object] | None:
    """Call a named tool on the PartsTable MCP server.

    Args:
        tool_name: Tool name (e.g. ``"search-parts"``).
        arguments: Tool arguments dict.
        request_id: JSON-RPC request identifier.

    Returns:
        Tool result dict, or None on failure.
    """
    return _mcp_call(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        request_id=request_id,
    )


def search_parts(part_number: str) -> dict[str, object] | None:
    """Search for parts by part number or MPN.

    Args:
        part_number: Manufacturer part number or search term.

    Returns:
        Search results dict, or None on failure.
    """
    return _call_tool("search-parts", {"partNumber": part_number})


def get_price_history(part_number: str) -> dict[str, object] | None:
    """Get historical pricing data for a specific part number.

    Args:
        part_number: Manufacturer part number.

    Returns:
        Price history dict, or None on failure.
    """
    return _call_tool("get-price-history", {"partNumber": part_number})


def normalize_pn(part_number: str) -> dict[str, object] | None:
    """Normalize a part number via PartsTable.

    Args:
        part_number: Raw part number string.

    Returns:
        Normalization result dict, or None on failure.
    """
    return _call_tool("normalize-pn", {"partNumber": part_number})


def _extract_content(
    response: dict[str, object],
) -> list[dict[str, object]]:
    """Extract content items from an MCP tool response.

    Args:
        response: Raw JSON-RPC response.

    Returns:
        List of content dicts from the tool result.
    """
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    content = result.get("content")
    if not isinstance(content, list):
        return []
    return [c for c in content if isinstance(c, dict)]


def get_unique_search_terms(
    db_path: Path = DB_PATH,
) -> list[dict[str, object]]:
    """Get deduplicated component search terms for PartsTable pricing.

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
            AND cp.price_source = 'partstable'
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

        if mpn and str(mpn).strip():
            search = str(mpn).strip()
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


class PartsTableScraper(BaseScraper):
    """Fetch component pricing via the PartsTable MCP API.

    Reads distinct component names/MPNs from the database, queries
    PartsTable for pricing and price history, and writes results to JSON.

    No authentication required.
    Output: ``data/raw/partstable/partstable_prices.json``
    """

    source_name = "partstable"

    def scrape(self) -> Path:
        """Query PartsTable for component pricing.

        Returns:
            Path to the output JSON file.
        """
        terms = get_unique_search_terms()
        if not terms:
            logger.warning("No components to price, skipping")
            out = self.output_dir / "partstable_prices.json"
            out.write_bytes(orjson.dumps([]))
            return out

        total_components = sum(
            len(t["bom_component_ids"])
            for t in terms
            if isinstance(t["bom_component_ids"], list)
        )
        logger.info(
            "Querying PartsTable: %d unique terms covering %d components",
            len(terms), total_components,
        )
        all_results: list[dict[str, object]] = []

        for i, term_info in enumerate(terms):
            search = str(term_info["search_term"])
            bom_ids = term_info["bom_component_ids"]
            if not isinstance(bom_ids, list) or not bom_ids:
                continue

            logger.info(
                "[%d/%d] Querying: %s (%d components)",
                i + 1, len(terms), search, len(bom_ids),
            )

            response = search_parts(search)
            if response is None:
                continue

            content = _extract_content(response)
            price_history: list[dict[str, object]] | None = None

            # If we got an MPN match, also fetch price history
            if term_info["has_mpn"]:
                history = get_price_history(search)
                if history is not None:
                    price_history = _extract_content(history)

            # Fan out result to all bom_component_ids sharing this term
            for bom_id in bom_ids:
                all_results.append({
                    "bom_component_id": bom_id,
                    "search_term": search,
                    "search_results": content,
                    "price_history": price_history,
                })

            time.sleep(0.5)

        logger.info(
            "Fetched %d results from PartsTable", len(all_results),
        )

        out = self.output_dir / "partstable_prices.json"
        out.write_bytes(
            orjson.dumps(all_results, option=orjson.OPT_INDENT_2)
        )
        return out
