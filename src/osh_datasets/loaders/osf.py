"""Loader for OSF (Open Science Framework) project data (JSON)."""

import contextlib
from pathlib import Path

import orjson

from osh_datasets.db import (
    insert_contributor,
    insert_license,
    insert_metric,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


class OsfLoader(BaseLoader):
    """Load OSF projects from ``data/osf/osf_comprehensive_metadata_dataset.json``."""

    source_name = "osf"

    def load(self, db_path: Path) -> int:
        """Read OSF JSON and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        json_path = self.data_dir / "osf" / "osf_comprehensive_metadata_dataset.json"
        with open(json_path, "rb") as fh:
            items: list[dict[str, object]] = orjson.loads(fh.read())

        count = 0

        with transaction(db_path) as conn:
            for item in items:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue

                subjects = item.get("subjects")
                category_parts: list[str] = []
                if isinstance(subjects, list):
                    for s in subjects:
                        if isinstance(s, dict) and s.get("text"):
                            category_parts.append(str(s["text"]))
                category = "; ".join(category_parts) if category_parts else None

                project_id = upsert_project(
                    conn,
                    source="osf",
                    source_id=str(item.get("project_id", "")),
                    name=title,
                    description=str(item.get("description") or "") or None,
                    url=str(item.get("url") or "") or None,
                    category=category,
                    created_at=str(item.get("created") or "") or None,
                    updated_at=str(item.get("modified") or "") or None,
                )

                tags_raw = item.get("tags")
                if isinstance(tags_raw, list):
                    insert_tags(
                        conn,
                        project_id,
                        [str(t) for t in tags_raw if t],
                    )

                lic = item.get("license")
                if isinstance(lic, dict) and lic.get("name"):
                    insert_license(conn, project_id, "hardware", str(lic["name"]))

                metrics = item.get("metrics")
                if isinstance(metrics, dict):
                    for metric_name, key in [
                        ("downloads", "total_downloads"),
                        ("activity_logs", "activity_logs"),
                        ("file_count", "file_count"),
                    ]:
                        val = metrics.get(key)
                        if val is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                insert_metric(conn, project_id, metric_name, int(val))

                contribs = item.get("contributors")
                if isinstance(contribs, list):
                    for c in contribs:
                        if not isinstance(c, dict):
                            continue
                        cname = str(c.get("name") or "").strip()
                        if cname:
                            insert_contributor(
                                conn,
                                project_id,
                                name=cname,
                                permission=str(c.get("permission") or "") or None,
                            )

                count += 1

        return count
