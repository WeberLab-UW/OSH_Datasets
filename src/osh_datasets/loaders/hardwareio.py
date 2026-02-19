"""Loader for Hardware.io project data (JSON)."""

import contextlib
from pathlib import Path

import orjson

from osh_datasets.db import (
    insert_license,
    insert_metric,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


class HardwareioLoader(BaseLoader):
    """Load Hardware.io projects from ``data/hardwareIO_allProjects.json``."""

    source_name = "hardwareio"

    def load(self, db_path: Path) -> int:
        """Read Hardware.io JSON and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        json_path = self.data_dir / "hardwareIO_allProjects.json"
        with open(json_path, "rb") as fh:
            items: list[dict[str, object]] = orjson.loads(fh.read())

        count = 0

        with transaction(db_path) as conn:
            for item in items:
                name = str(item.get("project_name") or "").strip()
                if not name:
                    continue

                github = item.get("github") or ""
                github_url = str(github).strip() if github else None

                project_id = upsert_project(
                    conn,
                    source="hardwareio",
                    source_id=str(item.get("project_url", name)),
                    name=name,
                    url=str(item.get("project_url") or "") or None,
                    repo_url=github_url or None,
                    documentation_url=str(item.get("homepage") or "") or None,
                    author=str(item.get("project_author") or "") or None,
                    created_at=str(item.get("created") or "") or None,
                    updated_at=str(item.get("updated") or "") or None,
                )

                lic = item.get("license")
                if lic and str(lic).strip():
                    insert_license(conn, project_id, "hardware", str(lic).strip())

                stats = item.get("statistics")
                if isinstance(stats, dict):
                    for metric_name, key in [
                        ("likes", "likes"),
                        ("collects", "collects"),
                        ("comments", "comments"),
                        ("downloads", "downloads"),
                    ]:
                        val = stats.get(key)
                        if val is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                insert_metric(conn, project_id, metric_name, int(val))

                views = item.get("views")
                if views is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        insert_metric(
                            conn, project_id, "views", int(str(views))
                        )

                count += 1

        return count
