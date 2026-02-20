"""Extract article metadata from the HardwareX full XML dump.

Parses ``ohx-allPubs.xml`` to extract paper titles, specifications tables,
bill of materials, and repository references for each article.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import orjson

from osh_datasets.config import DATA_DIR, get_logger
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_SPECS_KEYWORDS = frozenset(
    ["hardware name", "subject area", "hardware type", "cost", "license"]
)
_BOM_INDICATORS = frozenset(
    [
        "designator",
        "component",
        "part",
        "number",
        "quantity",
        "cost",
        "price",
        "total",
        "source",
        "supplier",
        "material",
    ]
)
_DESIGN_FILE_INDICATORS = frozenset(
    ["design file name", "file type", "location of the file"]
)
_PLATFORMS = ("github", "gitlab", "zenodo")


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _iter_text(elem: ET.Element) -> str:
    """Join all text content from an element and its children."""
    return " ".join(t.strip() for t in elem.itertext() if t.strip())


def _cell_value_with_links(cell: ET.Element) -> str:
    """Extract cell text and append any ext-link hrefs not in the text."""
    value = _clean_text(_iter_text(cell))
    for link in cell.findall(".//ext-link"):
        href = link.get("{http://www.w3.org/1999/xlink}href") or link.get("href", "")
        if href and href not in value:
            value += f" [{href}]"
    return value


def _parse_specs_table(table: ET.Element) -> dict[str, str]:
    """Parse a two-column specs table into key-value pairs."""
    specs: dict[str, str] = {}
    for row in table.findall(".//tr"):
        cells = row.findall(".//td") + row.findall(".//th")
        if len(cells) >= 2:
            key = _clean_text(_iter_text(cells[0]))
            value = _cell_value_with_links(cells[1])
            if key and value and "specifications table" not in key.lower():
                specs[key] = value
    return specs


def _extract_specs(article: ET.Element) -> dict[str, str]:
    """Find and parse the specifications table in an article."""
    # Strategy 1: section titled "specifications table"
    for sec in article.findall(".//sec"):
        title_el = sec.find(".//title")
        if title_el is not None:
            title_text = (title_el.text or "").lower()
            if "specifications table" in title_text:
                tbl = sec.find(".//table")
                if tbl is not None:
                    specs = _parse_specs_table(tbl)
                    if specs:
                        return specs

    # Strategy 2: table with specs-like headers
    for tbl in article.findall(".//table"):
        for row in tbl.findall(".//tr"):
            cells = row.findall(".//td") + row.findall(".//th")
            if cells:
                first = _iter_text(cells[0]).lower()
                if any(kw in first for kw in _SPECS_KEYWORDS):
                    specs = _parse_specs_table(tbl)
                    if specs:
                        return specs
    return {}


def _is_total_row(item: dict[str, str]) -> bool:
    """Check if a BOM row is a total/summary row."""
    for value in item.values():
        if value.lower() in ("total", "grand total", "subtotal"):
            return True
    return False


def _parse_bom_table(table: ET.Element) -> list[dict[str, str]]:
    """Parse a BOM table into a list of component dicts."""
    headers: list[str] = []
    header_row = table.find(".//thead//tr") or table.find(".//tr")
    if header_row is not None:
        for cell in header_row.findall(".//th") + header_row.findall(".//td"):
            headers.append(_clean_text(_iter_text(cell)))

    tbody = table.find(".//tbody")
    rows = tbody.findall(".//tr") if tbody is not None else table.findall(".//tr")[1:]

    bom: list[dict[str, str]] = []
    for row in rows:
        cells = row.findall(".//td") + row.findall(".//th")
        if not cells:
            continue
        item: dict[str, str] = {}
        for i, cell in enumerate(cells):
            header = headers[i] if i < len(headers) else f"column_{i}"
            item[header] = _cell_value_with_links(cell)
        if any(v.strip() for v in item.values()) and not _is_total_row(item):
            bom.append(item)
    return bom


def _is_valid_bom(bom: list[dict[str, str]]) -> bool:
    """Check that a table looks like a BOM, not a design-files table."""
    if not bom:
        return False
    headers = [h.lower() for h in bom[0]]
    design_hits = sum(1 for h in headers for d in _DESIGN_FILE_INDICATORS if d in h)
    if design_hits > 0:
        return False
    bom_hits = sum(1 for h in headers for b in _BOM_INDICATORS if b in h)
    return bom_hits >= 2


def _extract_bom(article: ET.Element) -> list[dict[str, str]]:
    """Find and parse the bill of materials table."""
    for sec in article.findall(".//sec"):
        title_el = sec.find(".//title")
        if title_el is not None:
            title_text = (title_el.text or "").lower()
            if "bill of materials" in title_text:
                tbl = sec.find(".//table")
                if tbl is not None:
                    bom = _parse_bom_table(tbl)
                    if bom:
                        return bom
    return []


def _extract_repo_refs(
    article: ET.Element,
) -> list[dict[str, str | None]]:
    """Extract repository references (GitHub, GitLab, Zenodo)."""
    refs: list[dict[str, str | None]] = []
    seen: set[str] = set()

    for link in article.findall(".//ext-link"):
        href = (
            link.get("{http://www.w3.org/1999/xlink}href")
            or link.get("href")
            or ""
        )
        link_text = _clean_text("".join(link.itertext()))
        for platform in _PLATFORMS:
            if (
                (platform in href.lower() or platform in link_text.lower())
                and href
                and href not in seen
            ):
                refs.append(
                    {
                        "platform": platform,
                        "link": href,
                        "link_text": link_text,
                    }
                )
                seen.add(href)
    return refs


class OhxScraper(BaseScraper):
    """Parse the HardwareX XML dump into structured JSON.

    Reads ``data/ohx-allPubs.xml`` and extracts per-article metadata.
    Output: ``data/raw/ohx/ohx_articles.json``
    """

    source_name = "ohx"

    def scrape(self, xml_path: Path | None = None) -> Path:
        """Parse the XML file and write structured output.

        Args:
            xml_path: Override path to the XML file.

        Returns:
            Path to the output JSON file.
        """
        if xml_path is None:
            xml_path = DATA_DIR / "ohx-allPubs.xml"

        if not xml_path.exists():
            logger.warning("OHX XML not found at %s", xml_path)
            out = self.output_dir / "ohx_articles.json"
            out.write_bytes(orjson.dumps([]))
            return out

        tree = ET.parse(str(xml_path))  # noqa: S314
        root = tree.getroot()

        articles: list[dict[str, object]] = []
        for article_el in root.findall(".//article"):
            title_el = article_el.find(".//article-title")
            title = _clean_text(title_el.text or "") if title_el is not None else ""

            articles.append(
                {
                    "paper_title": title,
                    "specifications_table": _extract_specs(article_el),
                    "bill_of_materials": _extract_bom(article_el),
                    "repository_references": _extract_repo_refs(article_el),
                }
            )

        logger.info("Extracted %d articles from XML", len(articles))

        out = self.output_dir / "ohx_articles.json"
        out.write_bytes(orjson.dumps(articles, option=orjson.OPT_INDENT_2))
        return out
