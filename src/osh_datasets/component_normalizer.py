"""Normalize BOM component names to canonical forms.

Applies a three-tier pipeline: text cleanup, electronics unit
standardization, and common-name consolidation.  The original
``component_name`` is preserved; a new ``component_normalized``
column is populated with the canonical form.
"""

import re
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Tier 1: Unicode translation table (single-pass via str.translate)
# ------------------------------------------------------------------

_UNICODE_MAP: dict[int, str] = {
    0x00B5: "u",   # micro sign
    0x03BC: "u",   # Greek mu
    0x2126: "ohm", # Ohm sign
    0x03A9: "ohm", # Greek capital omega
    0x03C9: "ohm", # Greek small omega
    0x2013: "-",   # en-dash
    0x2014: "-",   # em-dash
    0x2018: "'",   # left single quote
    0x2019: "'",   # right single quote
    0x201C: '"',   # left double quote
    0x201D: '"',   # right double quote
    0x00B1: "+-",  # plus-minus
    0x00D7: "x",   # multiplication sign
    0x2032: "'",   # prime
    0x00B0: "deg", # degree sign
}

_UNICODE_TABLE = str.maketrans(_UNICODE_MAP)

_MULTI_SPACE = re.compile(r"\s+")

_NULL_VALUES = frozenset({"", "null", "none", "n/a", "na", "-", "--"})

# ------------------------------------------------------------------
# Tier 2: Electronics unit normalization (compiled regexes)
# ------------------------------------------------------------------

_UNIT_RULES: list[tuple[re.Pattern[str], str]] = [
    # Resistance: kohm/mohm -> k/m multiplier
    (re.compile(r"(\d+(?:\.\d+)?)\s*kohm"), r"\1k"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*mohm"), r"\1m"),
    # Resistance: plain ohm (collapse spacing)
    (re.compile(r"(\d+(?:\.\d+)?)\s*ohm"), r"\1ohm"),
    # Resistance: R notation (220r -> 220ohm)
    (re.compile(r"\b(\d+(?:\.\d+)?)r\b"), r"\1ohm"),
    # Capacitance: normalize spacing for explicit units
    (re.compile(r"(\d+(?:\.\d+)?)\s*uf\b"), r"\1uf"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*nf\b"), r"\1nf"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*pf\b"), r"\1pf"),
    # Capacitance: bare suffix -> full unit (guarded by \b)
    (re.compile(r"\b(\d+(?:\.\d+)?)u\b"), r"\1uf"),
    (re.compile(r"\b(\d+(?:\.\d+)?)n\b"), r"\1nf"),
    (re.compile(r"\b(\d+(?:\.\d+)?)p\b"), r"\1pf"),
    # Inductance: normalize spacing
    (re.compile(r"(\d+(?:\.\d+)?)\s*uh\b"), r"\1uh"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*mh\b"), r"\1mh"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*nh\b"), r"\1nh"),
]

# ------------------------------------------------------------------
# Tier 3: Common name consolidation
# ------------------------------------------------------------------

_LEADING_ARTICLE = re.compile(r"^(?:a|an|the)\s+")

_ABBREV_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bres\b"), "resistor"),
    (re.compile(r"\bcap\b"), "capacitor"),
    (re.compile(r"\bind\b"), "inductor"),
]


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def _clean_text(text: str) -> str:
    """Strip, collapse whitespace, replace unicode, lowercase.

    Args:
        text: Raw component name string.

    Returns:
        Cleaned lowercase string, or empty string for null-like values.
    """
    text = text.translate(_UNICODE_TABLE).strip()
    if text.lower() in _NULL_VALUES:
        return ""
    text = _MULTI_SPACE.sub(" ", text)
    return text.lower().strip()


def _normalize_units(text: str) -> str:
    """Standardize capacitance, resistance, and inductance notation.

    Args:
        text: Cleaned (lowercased) component name.

    Returns:
        String with standardized unit notation.
    """
    for pattern, replacement in _UNIT_RULES:
        text = pattern.sub(replacement, text)
    return text


def _consolidate_names(text: str) -> str:
    """Remove leading articles and expand common abbreviations.

    Args:
        text: Unit-normalized component name.

    Returns:
        Consolidated component name.
    """
    text = _LEADING_ARTICLE.sub("", text)
    for pattern, replacement in _ABBREV_RULES:
        text = pattern.sub(replacement, text)
    return text.strip()


def normalize(raw: str) -> str:
    """Normalize a raw BOM component name through the three-tier pipeline.

    Args:
        raw: The original component_name string.

    Returns:
        Normalized component name, or empty string if input was
        empty/null-like.
    """
    text = _clean_text(raw)
    if not text:
        return ""
    text = _normalize_units(text)
    text = _consolidate_names(text)
    return text


def add_component_normalized_column(db_path: Path = DB_PATH) -> int:
    """Add ``component_normalized`` column to ``bom_components`` and populate.

    Safe to call multiple times -- adds the column only if missing.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of component rows normalized.
    """
    conn = open_connection(db_path)

    # Add column if missing
    cols = {
        r[1]
        for r in conn.execute(
            "PRAGMA table_info(bom_components)"
        ).fetchall()
    }
    if "component_normalized" not in cols:
        conn.execute(
            "ALTER TABLE bom_components "
            "ADD COLUMN component_normalized TEXT"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_comp_norm "
        "ON bom_components(component_normalized)"
    )

    rows = conn.execute(
        "SELECT id, component_name FROM bom_components"
    ).fetchall()

    updates: list[tuple[str, int]] = []
    for row_id, raw in rows:
        canonical = normalize(str(raw)) if raw is not None else ""
        updates.append((canonical, row_id))

    conn.executemany(
        "UPDATE bom_components "
        "SET component_normalized = ? WHERE id = ?",
        updates,
    )
    conn.commit()

    count = len(updates)

    # Log summary
    distinct_raw = conn.execute(
        "SELECT COUNT(DISTINCT component_name) "
        "FROM bom_components "
        "WHERE component_name IS NOT NULL AND component_name != ''"
    ).fetchone()
    distinct_norm = conn.execute(
        "SELECT COUNT(DISTINCT component_normalized) "
        "FROM bom_components "
        "WHERE component_normalized IS NOT NULL "
        "AND component_normalized != ''"
    ).fetchone()
    empty = conn.execute(
        "SELECT COUNT(*) FROM bom_components "
        "WHERE component_normalized = '' "
        "OR component_normalized IS NULL"
    ).fetchone()

    logger.info(
        "Normalized %d component rows: "
        "%d distinct raw -> %d distinct normalized (%d empty/null)",
        count,
        distinct_raw[0] if distinct_raw else 0,
        distinct_norm[0] if distinct_norm else 0,
        empty[0] if empty else 0,
    )

    conn.close()
    return count


if __name__ == "__main__":
    result = add_component_normalized_column()
    print(f"Normalized {result} component rows.")
