"""Loader for OHR (Open Hardware Repository) cleaned CSV data."""

import ast
import contextlib
from pathlib import Path

import polars as pl

from osh_datasets.db import (
    insert_metric,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


def _parse_string_list(raw: str | None) -> list[str]:
    """Parse a Python-literal list stored as a CSV string."""
    if not raw or raw.strip() in ("", "[]"):
        return []
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    return []


class OhrLoader(BaseLoader):
    """Load OHR projects from ``data/cleaned/ohr/ohr_cleaned.csv``.

    Optionally joins with classifier results to include only hardware
    projects and their hw_score.
    """

    source_name = "ohr"

    def __init__(
        self,
        data_dir: Path | None = None,
        hardware_only: bool = True,
    ) -> None:
        super().__init__(data_dir)
        self.hardware_only = hardware_only

    def load(self, db_path: Path) -> int:
        """Read OHR CSV, optionally filter by classifier, insert into DB.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        csv_path = self.data_dir / "cleaned" / "ohr" / "ohr_cleaned.csv"
        df = pl.read_csv(csv_path, infer_schema_length=1000, null_values=[""])

        classifications: dict[str, tuple[str, int]] = {}
        classifier_path = (
            self.data_dir.parent / "ohr_classifier" / "final_classifications.csv"
        )
        if classifier_path.exists():
            clf_df = pl.read_csv(classifier_path)
            for clf_row in clf_df.iter_rows(named=True):
                pid = str(clf_row.get("project_id", ""))
                classification = clf_row.get("classification", "")
                hw_score = int(clf_row.get("hw_score", 0))
                classifications[pid] = (classification, hw_score)

        count = 0
        with transaction(db_path) as conn:
            for row in df.iter_rows(named=True):
                pid = str(row.get("id", ""))

                if self.hardware_only and classifications:
                    clf, _ = classifications.get(pid, ("unknown", 0))
                    if clf not in ("hardware", "ambiguous"):
                        continue

                project_id = upsert_project(
                    conn,
                    source="ohr",
                    source_id=pid,
                    name=row.get("name") or "",
                    description=row.get("description"),
                    url=row.get("web_url"),
                    repo_url=row.get("http_url_to_repo"),
                    created_at=row.get("created_at"),
                    category="hardware" if pid in classifications else None,
                )

                topics = _parse_string_list(row.get("topics"))
                tag_list = _parse_string_list(row.get("tag_list"))
                all_tags = list(set(topics + tag_list))
                if all_tags:
                    insert_tags(conn, project_id, all_tags)

                for metric_name, col in [
                    ("stars", "star_count"),
                    ("forks", "forks_count"),
                ]:
                    val = row.get(col)
                    if val is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            insert_metric(conn, project_id, metric_name, int(val))

                if pid in classifications:
                    _, hw_score = classifications[pid]
                    insert_metric(conn, project_id, "hw_score", hw_score)

                count += 1

        return count
