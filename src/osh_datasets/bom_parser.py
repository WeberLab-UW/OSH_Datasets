"""Shared BOM column mapping and file parsing utilities.

Provides canonical column-name tuples for coalescing variant BOM column
names (from different EDA tools) into a unified schema, and parsers for
CSV, TSV, Excel (.xlsx/.xls/.ods), and XML BOM formats.

All column-name matching is case-insensitive: DataFrame columns are
lowercased before coalescing, and all canonical tuples store lowercase
entries.
"""

from __future__ import annotations

import io
from pathlib import Path

import polars as pl
from lxml import etree

from osh_datasets.config import get_logger

logger = get_logger(__name__)

# ── Canonical column-name variants (all lowercase) ────────────────────
# Order matters: earlier columns are preferred in coalescing.

REFERENCE_COLS: tuple[str, ...] = (
    "designator", "reference", "ref", "refdes", "references",
    "designation", "part/designator", "ref name (refdes)",
    "refs", "reference(s)", "designators",
    "reference designator", "reference designators",
    "ref des", "parts", "line-note", "line note",
)

NAME_COLS: tuple[str, ...] = (
    "value", "description", "device", "name", "part", "comment",
    "component", "value5",
    "part description", "part name", "cmp name",
    "libpart", "libref", "comments", "descr",
    "designitemid", "parttype",
)

QTY_COLS: tuple[str, ...] = (
    "qty", "quantity", "qnty", "count", "qty:",
    "quantity per pcb", "num used",
    "build quantity", "order qty", "order qty.",
)

MFR_COLS: tuple[str, ...] = (
    "manufacturer", "mf", "vendor", "manufacturer 1",
    "manufacturer (avl)", "supplier",
    "manufacturer name", "manufacturers name",
    "mfr.", "mfg", "supplier name",
)

MPN_COLS: tuple[str, ...] = (
    "mpn", "manufacturer part", "partnumber", "manufacturer p/n",
    "partno", "part number", "part no",
    "manufacture part number", "manufacturer part number 1",
    "part no and description", "man. p/n", "sup. p/n",
    "manufacturer part number",
    "manufacturers part number",
    "manufacturer's part number",
    "mfr. no", "mfr. no.",
    "manf part #", "mfg part #",
    "digi-key part number", "digikey",
    "mouser part number", "mouser",
    "lcsc", "lcsc part #", "lcsc part number",
    "supplier pn", "supplier part number", "supplier p/n",
    "part no.", "p/n", "spn",
)

COST_COLS: tuple[str, ...] = (
    "cost", "price", "unit price $", "cost/pcs", "price/part",
    "cost (feb-16)", "price (ex. vat)",
    "unit price", "unit cost", "extended price",
    "total cost", "price each",
)

FOOTPRINT_COLS: tuple[str, ...] = (
    "footprint", "package", "pattern", "case/package",
    "case", "pcb footprint", "footprint lib",
)


def coalesce_cols(
    df: pl.DataFrame,
    candidates: tuple[str, ...],
    alias: str,
) -> pl.Expr:
    """Build a ``pl.coalesce`` expression for columns that exist.

    Column matching is case-insensitive: candidates and DataFrame
    columns are compared in lowercase.

    Args:
        df: Source dataframe (used to check column existence).
        candidates: Ordered column names to coalesce (lowercase).
        alias: Output column alias.

    Returns:
        A polars expression producing the coalesced value.
    """
    col_lower = {c.strip().lower(): c for c in df.columns}
    present = [col_lower[c] for c in candidates if c in col_lower]
    if not present:
        return pl.lit(None).alias(alias)
    exprs = [
        pl.when(pl.col(c) != "").then(pl.col(c))
        for c in present
    ]
    return pl.coalesce(exprs).alias(alias)


def safe_int_str(val: str | None) -> int | None:
    """Parse a string to int, returning None on failure.

    Args:
        val: String value to parse.

    Returns:
        Parsed integer or None.
    """
    if not val:
        return None
    cleaned = val.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except (ValueError, OverflowError):
        return None


def safe_float_str(val: str | None) -> float | None:
    """Parse a string to float, returning None on failure.

    Args:
        val: String value to parse.

    Returns:
        Parsed float or None.
    """
    if not val:
        return None
    cleaned = (
        val.strip()
        .replace(",", "")
        .replace("$", "")
        .replace(" ", "")
    )
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (ValueError, OverflowError):
        return None


def infer_quantity(
    reference: str | None,
    quantity_raw: str | None,
) -> int | None:
    """Infer component quantity from raw value or reference designators.

    Falls back to counting comma-separated designators in the reference
    field when the quantity column is missing or unparseable.

    Args:
        reference: Reference designator string (may be comma-separated).
        quantity_raw: Raw quantity string from the BOM.

    Returns:
        Inferred quantity, or None if indeterminate.
    """
    qty = safe_int_str(quantity_raw)
    if qty is not None:
        return qty
    if reference and "," in reference:
        parts = [r.strip() for r in reference.split(",") if r.strip()]
        if parts:
            return len(parts)
    if reference and reference.strip():
        return 1
    return None


# ── File parsers ───────────────────────────────────────────────────────

_TABULAR_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ods",
})

_SUPPORTED_EXTENSIONS = _TABULAR_EXTENSIONS | {".xml"}

# Paths containing these substrings are false positives (not real BOMs).
_FALSE_POSITIVE_PATTERNS: tuple[str, ...] = (
    "node_modules/",
    "/vendor/",
    "/test/fixtures/",
    "Design Data/GOST/",
    ".github/",
)


def _is_false_positive(file_path: str) -> bool:
    """Check whether a file path is a known false positive.

    Args:
        file_path: Relative path within the repository.

    Returns:
        True if the path matches a known non-BOM pattern.
    """
    return any(pat in file_path for pat in _FALSE_POSITIVE_PATTERNS)


def _decode_bytes(data: bytes) -> str:
    """Decode file bytes to string, handling UTF-16 and UTF-8-BOM.

    Args:
        data: Raw file bytes.

    Returns:
        Decoded text.
    """
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16-le", errors="replace")
    if data[:2] == b"\xfe\xff":
        return data.decode("utf-16-be", errors="replace")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace")
    return data.decode("utf-8", errors="replace")


def _detect_separator(header_line: str) -> str:
    """Detect the column separator from a header line.

    Args:
        header_line: First data line of a CSV-like file.

    Returns:
        Detected separator character.
    """
    tabs = header_line.count("\t")
    semis = header_line.count(";")
    commas = header_line.count(",")
    if tabs > commas and tabs > semis:
        return "\t"
    if semis > commas:
        return ";"
    return ","


_KICAD_CSV_PREAMBLE = frozenset({
    "source:", "date:", "tool:", "generator:",
})


def _read_csv_with_comments(
    data: bytes,
    sep: str | None = None,
) -> pl.DataFrame:
    """Read CSV/TSV data, skipping comment and preamble lines.

    Strips lines starting with ``#``, KiCad CSV preamble lines
    (``Source:``, ``Date:``, ``Tool:``, ``Generator:``), and leading
    lines that don't contain the separator.

    Handles UTF-16 and UTF-8-BOM encoded files. If *sep* is None,
    auto-detects the separator from the header line.

    Args:
        data: Raw file bytes.
        sep: Column separator, or None to auto-detect.

    Returns:
        Parsed DataFrame.
    """
    text = _decode_bytes(data)
    lines = text.splitlines(keepends=True)
    # Strip comment lines
    lines = [ln for ln in lines if not ln.lstrip().startswith("#")]
    # Strip KiCad CSV preamble lines
    while lines:
        first_field = lines[0].split(",")[0].strip().strip('"').lower()
        if first_field in _KICAD_CSV_PREAMBLE or not first_field:
            lines.pop(0)
        else:
            break
    if not lines:
        return pl.DataFrame()
    if sep is None:
        sep = _detect_separator(lines[0])
    # Skip leading preamble lines that lack the separator
    while lines and sep not in lines[0]:
        lines.pop(0)
    if not lines:
        return pl.DataFrame()
    return pl.read_csv(
        io.StringIO("".join(lines)),
        separator=sep,
        infer_schema_length=0,
        ignore_errors=True,
        truncate_ragged_lines=True,
    )


def _read_tabular(
    data: bytes,
    extension: str,
) -> pl.DataFrame | None:
    """Read tabular data into a polars DataFrame.

    Args:
        data: Raw file bytes.
        extension: Lowercase file extension (e.g. ".csv").

    Returns:
        DataFrame or None if parsing fails.
    """
    try:
        if extension in (".csv", ".txt"):
            return _read_csv_with_comments(data, sep=None)
        if extension == ".tsv":
            return _read_csv_with_comments(data, sep="\t")
        if extension == ".xlsx":
            return pl.read_excel(
                io.BytesIO(data),
                engine="openpyxl",
                infer_schema_length=0,
            )
        if extension in (".xls", ".ods"):
            return pl.read_excel(
                io.BytesIO(data),
                engine="calamine",
                infer_schema_length=0,
            )
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        logger.debug("Failed to parse %s file: %s", extension, exc)
        return None
    return None


# ── XML BOM parsers ────────────────────────────────────────────────────

def _text_or_none(el: etree._Element | None) -> str | None:
    """Extract stripped text from an element, or None.

    Args:
        el: lxml element or None.

    Returns:
        Stripped text content, or None if empty/missing.
    """
    if el is None:
        return None
    text = el.text
    if text is None:
        return None
    text = text.strip()
    return text if text else None


def _parse_kicad_export_xml(root: etree._Element) -> pl.DataFrame | None:
    """Parse KiCad ``<export>`` format XML BOM.

    Extracts component data from direct child elements and from
    ``<fields><field name="...">`` entries (where KiCad stores
    custom fields like MPN and Manufacturer).

    Args:
        root: Parsed XML root element.

    Returns:
        DataFrame with BOM columns, or None.
    """
    comps = root.find("components")
    if comps is None:
        return None

    rows: list[dict[str, str | None]] = []
    for comp in comps.findall("comp"):
        row: dict[str, str | None] = {
            "Reference": comp.get("ref"),
            "Value": _text_or_none(comp.find("value")),
            "Footprint": _text_or_none(comp.find("footprint")),
        }
        # Direct children (older KiCad versions)
        for tag in ("manufacturer", "mpn"):
            val = _text_or_none(comp.find(tag))
            if val:
                row[tag.capitalize() if tag == "manufacturer" else "MPN"] = val

        # Custom fields (standard KiCad 5-8 pattern)
        fields_el = comp.find("fields")
        if fields_el is not None:
            for field in fields_el.findall("field"):
                name = (field.get("name") or "").strip()
                text = _text_or_none(field)
                if name and text:
                    row[name] = text

        rows.append(row)

    if not rows:
        return None
    return pl.DataFrame(rows)


def _parse_flat_xml(root: etree._Element) -> pl.DataFrame | None:
    """Parse flat ``<schematic><component>...</component>`` XML BOM.

    Structure: ``<schematic><component><Reference>C1</Reference>
    <Value>100nF</Value><Count>1</Count></component></schematic>``

    Args:
        root: Parsed XML root element.

    Returns:
        DataFrame with BOM columns, or None.
    """
    components = root.findall("component")
    if not components:
        return None

    rows: list[dict[str, str | None]] = []
    for comp in components:
        row: dict[str, str | None] = {}
        for child in comp:
            tag = str(child.tag)
            text = child.text
            if text is not None:
                row[tag] = text.strip()
        if row:
            rows.append(row)

    if not rows:
        return None
    return pl.DataFrame(rows)


def _parse_eagle_xml(root: etree._Element) -> pl.DataFrame | None:
    """Parse Eagle schematic XML into BOM data.

    Navigates to ``<drawing><schematic><parts><part>`` and extracts
    reference (``name``), value, device (footprint), and custom
    ``<attribute>`` elements for MPN/manufacturer.

    Args:
        root: Parsed XML root element with tag ``eagle``.

    Returns:
        DataFrame with BOM columns, or None.
    """
    # Try multiple paths for the parts list
    parts = root.findall(".//schematic/parts/part")
    if not parts:
        parts = root.findall(".//drawing/schematic/parts/part")
    if not parts:
        return None

    rows: list[dict[str, str | None]] = []
    for part in parts:
        name = part.get("name")
        value = part.get("value")
        device = part.get("device")
        if not name:
            continue

        row: dict[str, str | None] = {
            "Reference": name,
            "Value": value if value else None,
            "Footprint": device if device else None,
        }

        # Extract custom attributes (MPN, MANUFACTURER, etc.)
        for attr in part.findall("attribute"):
            attr_name = (attr.get("name") or "").strip()
            attr_val = (attr.get("value") or "").strip()
            if attr_name and attr_val:
                row[attr_name] = attr_val

        rows.append(row)

    if not rows:
        return None
    return pl.DataFrame(rows)


_SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"


def _parse_spreadsheetml(root: etree._Element) -> pl.DataFrame | None:
    """Parse XML Spreadsheet 2003 (SpreadsheetML) BOM.

    Used by Altium Designer and Autodesk Inventor. Structure:
    ``<Workbook><Worksheet><Table><Row><Cell><Data>``

    Args:
        root: Parsed XML root element.

    Returns:
        DataFrame with BOM columns, or None.
    """
    ns = {"ss": _SS_NS}

    # Find the first Worksheet's Table (try namespaced, then bare)
    table = root.find(".//ss:Worksheet/ss:Table", ns)
    if table is None:
        table = root.find(".//Worksheet/Table")
    if table is None:
        return None

    # Extract rows
    row_tag_ns = f"{{{_SS_NS}}}Row"
    cell_tag_ns = f"{{{_SS_NS}}}Cell"

    all_rows: list[list[str]] = []
    for row_el in table:
        tag = row_el.tag
        if tag != "Row" and tag != row_tag_ns:
            continue
        cells: list[str] = []
        for cell in row_el:
            cell_tag = cell.tag
            if cell_tag != "Cell" and cell_tag != cell_tag_ns:
                continue
            data_el = cell.find(f"{{{_SS_NS}}}Data")
            if data_el is None:
                data_el = cell.find("Data")
            text = data_el.text.strip() if data_el is not None and data_el.text else ""
            cells.append(text)
        if cells:
            all_rows.append(cells)

    if len(all_rows) < 2:
        return None

    headers = all_rows[0]
    data_rows = all_rows[1:]

    rows: list[dict[str, str | None]] = []
    for data_row in data_rows:
        row: dict[str, str | None] = {}
        for i, val in enumerate(data_row):
            if i < len(headers) and headers[i]:
                row[headers[i]] = val if val else None
        if row:
            rows.append(row)

    if not rows:
        return None
    return pl.DataFrame(rows)


def _parse_xml_root(data: bytes) -> etree._Element | None:
    """Parse XML bytes into an lxml root element.

    Handles UTF-16 encoded files by falling back to decode + re-encode.

    Args:
        data: Raw XML file bytes.

    Returns:
        Parsed root element, or None on failure.
    """
    try:
        return etree.fromstring(data)
    except etree.XMLSyntaxError:
        pass

    # Try UTF-16 encoding
    try:
        text = data.decode("utf-16")
        return etree.fromstring(text.encode("utf-8"))
    except (UnicodeDecodeError, etree.XMLSyntaxError):
        logger.debug("Failed to parse XML BOM")
        return None


def _parse_xml_bom(data: bytes) -> pl.DataFrame | None:
    """Parse an XML BOM file into a DataFrame.

    Supports KiCad ``<export>``, flat ``<schematic><component>``,
    Eagle ``<eagle>``, and SpreadsheetML ``<Workbook>`` formats.

    Args:
        data: Raw XML file bytes.

    Returns:
        DataFrame or None if not a recognized BOM format.
    """
    root = _parse_xml_root(data)
    if root is None:
        return None

    tag = etree.QName(root.tag).localname if "}" in root.tag else root.tag

    if tag == "export":
        return _parse_kicad_export_xml(root)
    if tag == "schematic":
        return _parse_flat_xml(root)
    if tag == "eagle":
        return _parse_eagle_xml(root)
    if tag == "Workbook":
        return _parse_spreadsheetml(root)

    # Not a recognized BOM XML format
    logger.debug("Unrecognized XML root tag: %s", tag)
    return None


# ── Normalization ──────────────────────────────────────────────────────

def normalize_bom_df(df: pl.DataFrame) -> pl.DataFrame:
    """Coalesce variant columns into canonical BOM fields.

    Produces a DataFrame with columns: ``reference``,
    ``component_name``, ``quantity_raw``, ``manufacturer``,
    ``part_number``, ``unit_cost_raw``, ``footprint``.
    Rows where all fields are null are dropped.

    Column matching is case-insensitive.

    Args:
        df: Raw dataframe from a BOM file.

    Returns:
        Normalized dataframe with canonical columns.
    """
    normalized = df.select(
        coalesce_cols(df, REFERENCE_COLS, "reference"),
        coalesce_cols(df, NAME_COLS, "component_name"),
        coalesce_cols(df, QTY_COLS, "quantity_raw"),
        coalesce_cols(df, MFR_COLS, "manufacturer"),
        coalesce_cols(df, MPN_COLS, "part_number"),
        coalesce_cols(df, COST_COLS, "unit_cost_raw"),
        coalesce_cols(df, FOOTPRINT_COLS, "footprint"),
    )
    bom_fields = [
        "reference", "component_name", "quantity_raw",
        "manufacturer", "part_number", "unit_cost_raw",
    ]
    return normalized.filter(
        pl.any_horizontal(pl.col(c).is_not_null() for c in bom_fields)
    )


def parse_bom_file(
    data: bytes,
    file_path: str,
) -> pl.DataFrame | None:
    """Parse a BOM file into a normalized DataFrame.

    Supports CSV, TSV, TXT, XLSX, XLS, ODS, and XML formats.
    Returns None for false-positive paths (node_modules, GOST
    templates, etc.).

    Args:
        data: Raw file bytes.
        file_path: Original file path (used to determine extension).

    Returns:
        Normalized DataFrame or None if unsupported/unparseable.
    """
    if _is_false_positive(file_path):
        logger.debug("Skipping false positive: %s", file_path)
        return None

    ext = Path(file_path).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        logger.debug("Skipping unsupported BOM format: %s", ext)
        return None

    df = (
        _parse_xml_bom(data) if ext == ".xml"
        else _read_tabular(data, ext)
    )

    if df is None or df.is_empty():
        return None

    normalized = normalize_bom_df(df)
    if normalized.is_empty():
        return None

    return normalized
