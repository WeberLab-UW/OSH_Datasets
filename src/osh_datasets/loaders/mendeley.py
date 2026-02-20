"""Loader for Mendeley Data dataset metadata (JSON via OAI-PMH)."""

from pathlib import Path

import orjson

from osh_datasets.db import (
    insert_license,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


class MendeleyLoader(BaseLoader):
    """Load Mendeley Data metadata from ``data/raw/mendeley/mendeley_datasets.json``."""

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
            return 0

        with open(json_path, "rb") as fh:
            items: list[dict[str, object]] = orjson.loads(fh.read())

        count = 0

        with transaction(db_path) as conn:
            for item in items:
                title = str(item.get("title") or "").strip()
                dataset_id = str(item.get("dataset_id") or "").strip()
                if not title or not dataset_id:
                    continue

                creators = item.get("creator")
                author = None
                if isinstance(creators, list) and creators:
                    author = "; ".join(str(c) for c in creators)

                url = str(item.get("mendeley_url") or "") or None
                description = str(item.get("description") or "") or None
                date = str(item.get("date") or "") or None

                project_id = upsert_project(
                    conn,
                    source="mendeley",
                    source_id=dataset_id,
                    name=title,
                    description=description,
                    url=url,
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

                count += 1

        return count
