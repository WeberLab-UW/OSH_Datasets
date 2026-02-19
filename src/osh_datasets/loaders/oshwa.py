"""Loader for OSHWA cleaned CSV data."""

import ast
import re
from pathlib import Path

import polars as pl

from osh_datasets.db import (
    insert_license,
    insert_tags,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader

_GIT_HOST_RE = re.compile(r"github\.com|gitlab\.com|bitbucket\.org", re.IGNORECASE)


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


def _extract_repo_url(
    project_website: str | None,
    documentation_url: str | None,
) -> str | None:
    """Return the first URL that points to a known git host, or None."""
    for url in (documentation_url, project_website):
        if url and _GIT_HOST_RE.search(url):
            return url.strip()
    return None


class OshwaLoader(BaseLoader):
    """Load OSHWA projects from ``data/cleaned/oshwa/oshwa_cleaned.csv``."""

    source_name = "oshwa"

    def load(self, db_path: Path) -> int:
        """Read OSHWA CSV and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        csv_path = self.data_dir / "cleaned" / "oshwa" / "oshwa_cleaned.csv"
        df = pl.read_csv(csv_path, infer_schema_length=1000, null_values=[""])
        seen: set[str] = set()

        with transaction(db_path) as conn:
            for row in df.iter_rows(named=True):
                sid = row.get("oshwaUid") or ""
                pw = row.get("projectWebsite") or ""
                du = row.get("documentationUrl") or ""

                project_id = upsert_project(
                    conn,
                    source="oshwa",
                    source_id=sid,
                    name=row.get("projectName") or "",
                    description=row.get("projectDescription"),
                    url=pw or None,
                    repo_url=_extract_repo_url(pw, du),
                    documentation_url=du or None,
                    author=row.get("responsibleParty"),
                    country=row.get("country"),
                    category=row.get("primaryType"),
                    created_at=row.get("certificationDate"),
                )
                seen.add(sid)

                keywords = _parse_string_list(row.get("projectKeywords"))
                if keywords:
                    insert_tags(conn, project_id, keywords)

                for ltype, col in [
                    ("hardware", "hardwareLicense"),
                    ("software", "softwareLicense"),
                    ("documentation", "documentationLicense"),
                ]:
                    val = row.get(col)
                    if val and str(val).strip():
                        insert_license(conn, project_id, ltype, str(val).strip())

        return len(seen)
