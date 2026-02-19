"""Loader for Kitspace project data (JSON)."""

from pathlib import Path

import orjson

from osh_datasets.db import (
    insert_bom_component,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


def _safe_int(val: object) -> int | None:
    """Convert to int or return None."""
    if val is None:
        return None
    try:
        return int(str(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val: object) -> float | None:
    """Convert to float or return None, stripping currency symbols."""
    if val is None:
        return None
    try:
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


class KitspaceLoader(BaseLoader):
    """Load Kitspace projects from ``data/kitspace_results.json``."""

    source_name = "kitspace"

    def load(self, db_path: Path) -> int:
        """Read Kitspace JSON and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        json_path = self.data_dir / "kitspace_results.json"
        with open(json_path, "rb") as fh:
            data = orjson.loads(fh.read())

        items: list[dict[str, object]] = data.get("scraped_data", [])
        count = 0

        with transaction(db_path) as conn:
            for item in items:
                if item.get("error"):
                    continue

                name = str(item.get("project_name") or "").strip()
                if not name:
                    continue

                project_id = upsert_project(
                    conn,
                    source="kitspace",
                    source_id=str(item.get("url", name)),
                    name=name,
                    description=str(item.get("description") or "") or None,
                    url=str(item.get("url", "")) or None,
                    repo_url=str(item.get("repository_link") or "") or None,
                )

                bom = item.get("bill_of_materials")
                if isinstance(bom, list):
                    for comp in bom:
                        if not isinstance(comp, dict):
                            continue
                        insert_bom_component(
                            conn,
                            project_id,
                            reference=comp.get("reference"),
                            component_name=comp.get("description"),
                            quantity=_safe_int(comp.get("quantity")),
                            manufacturer=comp.get("manufacturer"),
                            part_number=comp.get("mpn"),
                        )

                count += 1

        return count
