"""Extract paper DOIs from the OHX full XML and backfill publications table.

The OHX JSON extract lacks paper DOIs (only has OSF/reference DOIs).
The full XML (``ohx-allPubs.xml``) contains the actual HardwareX DOIs.
This script matches OHX projects to XML articles by token-based title
similarity and updates the ``publications`` table with the recovered DOIs.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from osh_datasets.config import DATA_DIR, DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase alphanumeric tokens."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def parse_xml_dois(xml_path: Path) -> dict[str, str]:
    """Parse DOI and title from each article in the OHX XML.

    Args:
        xml_path: Path to ``ohx-allPubs.xml``.

    Returns:
        Mapping from DOI to article title.
    """
    articles: dict[str, str] = {}
    current_doi: str | None = None
    current_title: str | None = None

    context = ET.iterparse(str(xml_path), events=["end"])
    for _, elem in context:
        if elem.tag == "article-id" and elem.get("pub-id-type") == "doi":
            current_doi = (elem.text or "").strip()
        elif elem.tag == "article-title":
            current_title = "".join(elem.itertext()).strip()
        elif elem.tag == "article":
            if current_doi and current_title:
                articles[current_doi] = current_title
            current_doi = None
            current_title = None
            elem.clear()

    return articles


def backfill_dois(
    db_path: Path = DB_PATH,
    xml_path: Path | None = None,
    threshold: float = 0.3,
) -> int:
    """Match OHX publications to XML articles and fill in DOIs.

    Args:
        db_path: Path to the SQLite database.
        xml_path: Path to the OHX XML file. Defaults to
            ``DATA_DIR / "ohx-allPubs.xml"``.
        threshold: Minimum Jaccard similarity for a match.

    Returns:
        Number of DOIs backfilled.
    """
    if xml_path is None:
        xml_path = DATA_DIR / "ohx-allPubs.xml"

    if not xml_path.exists():
        logger.warning("OHX XML not found at %s, skipping", xml_path)
        return 0

    xml_articles = parse_xml_dois(xml_path)
    logger.info("Parsed %d articles from XML", len(xml_articles))

    conn = open_connection(db_path)

    # Find OHX publications without DOIs
    missing = conn.execute(
        "SELECT p.id, pr.name "
        "FROM publications p "
        "JOIN projects pr ON p.project_id = pr.id "
        "WHERE pr.source = 'ohx' AND (p.doi IS NULL OR p.doi = '')"
    ).fetchall()

    if not missing:
        logger.info("All OHX publications already have DOIs")
        conn.close()
        return 0

    logger.info("%d OHX publications lack DOIs, attempting fuzzy match", len(missing))

    # Collect already-used DOIs
    used_dois: set[str] = {
        row[0]
        for row in conn.execute(
            "SELECT doi FROM publications WHERE doi IS NOT NULL AND doi != ''"
        ).fetchall()
    }

    # Pre-tokenize XML titles
    xml_tokens = {doi: (title, _tokenize(title)) for doi, title in xml_articles.items()}

    filled = 0
    for pub_id, name in missing:
        ohx_tok = _tokenize(name)
        best_score = 0.0
        best_doi: str | None = None

        for doi, (_, tok) in xml_tokens.items():
            if doi in used_dois:
                continue
            score = _jaccard(ohx_tok, tok)
            if score > best_score:
                best_score = score
                best_doi = doi

        if best_score >= threshold and best_doi is not None:
            conn.execute(
                "UPDATE publications SET doi = ? WHERE id = ?",
                (best_doi, pub_id),
            )
            used_dois.add(best_doi)
            filled += 1
            logger.debug("Matched [%.2f]: '%s' -> %s", best_score, name[:50], best_doi)

    conn.commit()
    conn.close()
    logger.info("Backfilled %d DOIs from XML", filled)
    return filled


if __name__ == "__main__":
    count = backfill_dois()
    print(f"Backfilled {count} DOIs.")
