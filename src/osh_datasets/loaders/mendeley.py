"""Loader for Mendeley Data dataset metadata (JSON via OAI-PMH).

Reads ``data/raw/mendeley/mendeley_datasets.json`` (produced by
:class:`~osh_datasets.scrapers.mendeley.MendeleyScraper`) and loads
dataset metadata, licenses, tags, and publications into the database.
"""

import re
from pathlib import Path

import orjson

from osh_datasets.config import get_logger
from osh_datasets.db import (
    insert_license,
    insert_publication,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader

logger = get_logger(__name__)

_OAI_ID_RE = re.compile(
    r"data\.mendeley\.com[:/](?:datasets/)?([a-zA-Z0-9]+)"
)


def _extract_dataset_id(item: dict[str, object]) -> str:
    """Extract dataset ID from record, falling back to oai_identifier.

    Args:
        item: A single Mendeley record dict.

    Returns:
        Dataset ID string, or empty string if not found.
    """
    did = str(item.get("dataset_id") or "").strip()
    if did:
        return did
    oai_id = str(item.get("oai_identifier") or "")
    m = _OAI_ID_RE.search(oai_id)
    return m.group(1) if m else ""


class MendeleyLoader(BaseLoader):
    """Load Mendeley Data metadata into the database."""

    source_name = "mendeley"

    def load(self, db_path: Path) -> int:
        """Read Mendeley JSON and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        json_path = (
            self.data_dir / "raw" / "mendeley" / "mendeley_datasets.json"
        )
        if not json_path.exists():
            logger.info("No Mendeley data at %s, skipping", json_path)
            return 0

        with open(json_path, "rb") as fh:
            items: list[dict[str, object]] = orjson.loads(fh.read())

        if not items:
            return 0

        count = 0

        with transaction(db_path) as conn:
            for item in items:
                title = str(item.get("title") or "").strip()
                dataset_id = _extract_dataset_id(item)
                if not title or not dataset_id:
                    continue

                creators = item.get("creator")
                author = None
                if isinstance(creators, list) and creators:
                    author = "; ".join(str(c) for c in creators)

                mendeley_url = str(
                    item.get("mendeley_url") or ""
                ).strip()
                if not mendeley_url:
                    mendeley_url = (
                        f"https://data.mendeley.com/datasets/{dataset_id}"
                    )

                description = str(
                    item.get("description") or ""
                ).strip() or None
                date = str(item.get("date") or "").strip() or None

                doi = str(item.get("doi") or "").strip()
                if not doi:
                    doi = f"10.17632/{dataset_id}"

                project_id = upsert_project(
                    conn,
                    source="mendeley",
                    source_id=dataset_id,
                    name=title,
                    description=description,
                    url=mendeley_url,
                    author=author,
                    created_at=date,
                )

                # Rights -> license
                rights = str(item.get("rights") or "").strip()
                if rights:
                    insert_license(conn, project_id, "data", rights)

                # Subjects -> tags
                subjects = item.get("subject")
                if isinstance(subjects, list):
                    insert_tags(
                        conn,
                        project_id,
                        [str(s) for s in subjects if s],
                    )

                # Publication record with DOI
                if doi:
                    insert_publication(
                        conn,
                        project_id,
                        doi=doi,
                        title=title,
                    )

                count += 1

        logger.info("Loaded %d Mendeley datasets", count)
        return count
