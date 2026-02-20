"""Normalize license strings to canonical SPDX identifiers.

Maps the 200+ raw license name variants found across OSHWA, Hardware.io,
OHX, and JOH into a small set of standard identifiers.  The original
``license_name`` is preserved; a new ``license_normalized`` column is
populated with the canonical form.
"""

import re
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)

# ------------------------------------------------------------------
# Normalization rules: ordered list of (compiled regex, canonical name).
# First match wins, so more specific patterns go before generic ones.
# ------------------------------------------------------------------

_RULES: list[tuple[re.Pattern[str], str]] = []


def _r(pattern: str, canonical: str) -> None:
    """Register a case-insensitive regex rule."""
    _RULES.append((re.compile(pattern, re.IGNORECASE), canonical))


# --- Special / skip values ---
_r(r"^no software$", "No-Software")
_r(r"^other$", "Other")
_r(r"^null$", "Other")
_r(r"^various$", "Other")
_r(r"^imported", "Other")
_r(r"mendeley", "Other")

# --- CC0 ---
_r(r"cc.?0|cc zero|public.?domain|creative commons.{0,5}zero", "CC0-1.0")

# --- CC BY-NC-ND ---
_r(r"cc.?by.?nc.?nd.?4", "CC-BY-NC-ND-4.0")
_r(r"cc.?by.?nc.?nd", "CC-BY-NC-ND-4.0")

# --- CC BY-NC-SA ---
_r(r"cc.?by.?nc.?sa.?4|noncommercial.?sharealike.?4", "CC-BY-NC-SA-4.0")
_r(r"cc.?by.?nc.?sa|noncommercial.?sharealike", "CC-BY-NC-SA-4.0")

# --- CC BY-NC ---
_r(r"cc.?by.?nc.?4", "CC-BY-NC-4.0")
_r(r"cc.?by.?nc.?3", "CC-BY-NC-3.0")
_r(r"cc.?by.?nc", "CC-BY-NC-4.0")

# --- CC BY-SA (must come after BY-NC-SA) ---
_r(r"cc.?by.?sa.?4|attribution.?sharealike.?4|share.?alike.?4", "CC-BY-SA-4.0")
_r(r"cc.?by.?sa.?3|attribution.?sharealike.?3", "CC-BY-SA-3.0")
_r(r"cc.?by.?sa|attribution.?sharealike|share.?alike", "CC-BY-SA-4.0")

# --- CC BY (must come after all BY-* variants) ---
_r(r"cc.?by.?4|attribution.?4\.0", "CC-BY-4.0")
_r(r"cc.?by.?3|attribution.?3\.0", "CC-BY-3.0")
_r(r"cc.?by.?2", "CC-BY-2.0")
_r(r"cc.?by|creative commons.{0,5}attribution", "CC-BY-4.0")

# --- CERN OHL variants (specific before generic) ---
_r(r"cern.?ohl.?s.?2|cern.{0,30}strongly.?reciprocal", "CERN-OHL-S-2.0")
_r(r"cern.?ohl.?w.?2|cern.{0,30}weakly.?reciprocal", "CERN-OHL-W-2.0")
_r(r"cern.?ohl.?p.?2|cern.{0,30}permissive", "CERN-OHL-P-2.0")
_r(r"cern.?ohl.?s", "CERN-OHL-S-2.0")
_r(r"cern.?ohl.?w", "CERN-OHL-W-2.0")
_r(r"cern.?ohl.?p", "CERN-OHL-P-2.0")
_r(r"cern.?ohl.?1\.2|cern.?ohl.?v\.?1", "CERN-OHL-1.2")
_r(r"cern.?ohl.?v?2|cern.{0,20}version.?2", "CERN-OHL-S-2.0")
_r(r"cern", "CERN-OHL")

# --- TAPR ---
_r(r"tapr", "TAPR-OHL")

# --- Solderpad ---
_r(r"solderpad.{0,10}2\.1|shl.?2\.1", "Solderpad-2.1")
_r(r"solderpad|shl.?2", "Solderpad-2.0")

# --- AGPL ---
_r(r"agpl|affero", "AGPL-3.0-or-later")

# --- LGPL ---
_r(r"lgpl.?3|lesser.{0,10}3", "LGPL-3.0-or-later")
_r(r"lgpl|lesser general", "LGPL-3.0-or-later")

# --- GPL (must come after AGPL/LGPL) ---
_r(r"gpl.?3\.0.?or.?later", "GPL-3.0-or-later")
_r(r"gpl.?3\.0.?only", "GPL-3.0-only")
_r(r"gpl.?v?3|gpl.?3|gnu.{0,30}3|general public license.{0,10}3", "GPL-3.0-or-later")
_r(r"gpl.?v?2|gpl.?2|gnu.{0,30}2|general public license.{0,10}2", "GPL-2.0-or-later")
_r(r"gpl|gnu general public", "GPL-3.0-or-later")

# --- Apache ---
_r(r"apache.?2", "Apache-2.0")
_r(r"apache", "Apache-2.0")

# --- BSD ---
_r(r"bsd.?3|bsd three|berkeley", "BSD-3-Clause")
_r(r"bsd.?2", "BSD-2-Clause")
_r(r"bsd", "BSD-3-Clause")

# --- MIT ---
_r(r"mit", "MIT")

# --- Mozilla ---
_r(r"mozilla|mpl", "MPL-2.0")

# --- Catch-all for Creative Commons URLs ---
_r(r"creativecommons\.org/licen[sc]es/by-sa", "CC-BY-SA-4.0")
_r(r"creativecommons\.org/licen[sc]es/by-nc", "CC-BY-NC-4.0")
_r(r"creativecommons\.org/licen[sc]es/by", "CC-BY-4.0")
_r(r"creative.?commons", "CC-BY-4.0")


def normalize(raw: str) -> str:
    """Map a raw license string to a canonical SPDX-style identifier.

    Args:
        raw: The original license name string.

    Returns:
        Canonical license identifier, or ``"Other"`` if unrecognized.
    """
    text = raw.strip()
    if not text:
        return "Other"

    # Detect compound licenses (multiple licenses in one string)
    separators = [";", " and ", " / ", ", "]
    for sep in separators:
        if sep in text.lower():
            parts = [
                p.strip()
                for p in re.split(re.escape(sep), text, flags=re.IGNORECASE)
                if p.strip()
            ]
            if len(parts) >= 2:
                normalized_parts = []
                for part in parts:
                    for pattern, canonical in _RULES:
                        if pattern.search(part):
                            if canonical not in normalized_parts:
                                normalized_parts.append(canonical)
                            break
                if len(normalized_parts) > 1:
                    return " + ".join(sorted(normalized_parts))
                if normalized_parts:
                    return normalized_parts[0]

    for pattern, canonical in _RULES:
        if pattern.search(text):
            return canonical

    return "Other"


def add_normalized_column(db_path: Path = DB_PATH) -> int:
    """Add ``license_normalized`` column and populate it.

    Safe to call multiple times -- drops and recreates the column.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of license rows normalized.
    """
    conn = open_connection(db_path)

    # Add column if it doesn't exist
    cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
    if "license_normalized" not in cols:
        conn.execute("ALTER TABLE licenses ADD COLUMN license_normalized TEXT")

    rows = conn.execute("SELECT id, license_name FROM licenses").fetchall()

    count = 0
    for row in rows:
        lid, raw = row[0], row[1]
        canonical = normalize(raw)
        conn.execute(
            "UPDATE licenses SET license_normalized = ? WHERE id = ?",
            (canonical, lid),
        )
        count += 1

    conn.commit()

    # Log summary
    stats = conn.execute(
        "SELECT license_normalized, COUNT(*) as cnt "
        "FROM licenses GROUP BY license_normalized ORDER BY cnt DESC"
    ).fetchall()
    logger.info("Normalized %d license rows into %d categories:", count, len(stats))
    for s in stats:
        logger.info("  %-25s %d", s[0], s[1])

    conn.close()
    return count


if __name__ == "__main__":
    count = add_normalized_column()
    print(f"Normalized {count} license rows.")
