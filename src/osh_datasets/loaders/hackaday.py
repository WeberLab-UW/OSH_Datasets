"""Loader for Hackaday cleaned CSV data."""

import ast
import contextlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from osh_datasets.db import (
    insert_metric,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


def _epoch_to_iso(epoch_val: object) -> str | None:
    """Convert a Unix epoch (int/float/str) to ISO 8601, or return None."""
    if epoch_val is None:
        return None
    try:
        ts = float(str(epoch_val))
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (ValueError, OSError):
        return None


def _parse_string_list(raw: str | None) -> list[str]:
    """Parse a Python-literal list stored as a string."""
    if not raw or raw.strip() in ("", "[]"):
        return []
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    return []


class HackadayLoader(BaseLoader):
    """Load Hackaday projects from ``data/cleaned/hackaday/hackaday_cleaned.csv``."""

    source_name = "hackaday"

    def load(self, db_path: Path) -> int:
        """Read Hackaday CSV and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        csv_path = self.data_dir / "cleaned" / "hackaday" / "hackaday_cleaned.csv"
        df = pl.read_csv(csv_path, infer_schema_length=1000, null_values=[""])
        count = 0

        with transaction(db_path) as conn:
            for row in df.iter_rows(named=True):
                project_id = upsert_project(
                    conn,
                    source="hackaday",
                    source_id=str(row.get("id", row.get("projectId", ""))),
                    name=row.get("title") or "",
                    description=row.get("description"),
                    url=row.get("url"),
                    repo_url=row.get("github_links"),
                    author=row.get("userName"),
                    created_at=_epoch_to_iso(row.get("created")),
                    updated_at=_epoch_to_iso(row.get("updated")),
                )

                tags = _parse_string_list(row.get("tags"))
                if tags:
                    insert_tags(conn, project_id, tags)

                for metric_name, col in [
                    ("views", "viewsCount"),
                    ("likes", "likesCount"),
                    ("followers", "followersCount"),
                ]:
                    val = row.get(col)
                    if val is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            insert_metric(conn, project_id, metric_name, int(val))

                count += 1

        return count
