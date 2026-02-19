"""Loader for Journal of Open Hardware (JOH) CSV with OpenAlex enrichment."""

import contextlib
import csv
import re
from pathlib import Path

from osh_datasets.db import (
    insert_license,
    insert_publication,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader

_URL_RE = re.compile(r"https?://[^\s,;)]+")


def _extract_urls(text: str | None) -> list[str]:
    """Extract all URLs from a free-text field.

    Args:
        text: Free-text potentially containing embedded URLs.

    Returns:
        List of extracted URL strings.
    """
    if not text:
        return []
    return _URL_RE.findall(text)


def _first_repo_url(text: str | None) -> str | None:
    """Return the first GitHub/GitLab URL from free text, or None."""
    for url in _extract_urls(text):
        if "github.com" in url.lower() or "gitlab.com" in url.lower():
            return url
    return None


def _build_openalex_doi_index(
    csv_path: Path,
) -> dict[str, dict[str, str]]:
    """Index OpenAlex JOH records by normalized DOI.

    Args:
        csv_path: Path to ``openalex_metadata.csv``.

    Returns:
        Mapping from DOI to OpenAlex record dict.
    """
    index: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return index
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            loc = row.get("primary_location", "")
            if "journal of open hardware" not in loc.lower():
                continue
            doi_raw = row.get("doi", "")
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            if doi:
                index[doi] = row
    return index


class JohLoader(BaseLoader):
    """Load Journal of Open Hardware papers, enriched with OpenAlex data."""

    source_name = "joh"

    def load(self, db_path: Path) -> int:
        """Read JOH CSV and OpenAlex CSV, join by DOI, insert into DB.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        joh_path = (
            self.data_dir
            / "journal_of_open_hardware"
            / "journal_of_open_hardware_papers.csv"
        )
        oa_csv = (
            self.data_dir / "raw" / "scientific_literature" / "openalex_metadata.csv"
        )
        oa_index = _build_openalex_doi_index(oa_csv)

        count = 0

        with transaction(db_path) as conn, open(joh_path, newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                title = (row.get("Title") or "").strip()
                if not title:
                    continue

                doi = (row.get("DOI") or "").strip().lower()
                repo_links = row.get("Repository Links") or ""
                other_links = row.get("Other Links") or ""

                project_id = upsert_project(
                    conn,
                    source="joh",
                    source_id=doi or title,
                    name=title,
                    description=(row.get("Abstract Note") or "").strip() or None,
                    url=(row.get("Url") or "").strip() or None,
                    repo_url=_first_repo_url(repo_links + " " + other_links),
                    author=(row.get("Author") or "").strip() or None,
                    created_at=(row.get("Date") or "").strip() or None,
                )

                for ltype, col in [
                    ("hardware", "HW_License"),
                    ("software", "SW_License"),
                    ("documentation", "Documentation_License"),
                ]:
                    val = (row.get(col) or "").strip()
                    if val:
                        insert_license(conn, project_id, ltype, val)

                # Enrich with OpenAlex
                oa_row = oa_index.get(doi)
                cited_by: int | None = None
                pub_year: int | None = None
                open_access: bool | None = None

                if oa_row:
                    with contextlib.suppress(ValueError, TypeError):
                        cited_by = int(oa_row.get("cited_by_count", ""))
                    with contextlib.suppress(ValueError, TypeError):
                        pub_year = int(oa_row.get("publication_year", ""))
                    oa_str = oa_row.get("open_access", "")
                    open_access = "true" in oa_str.lower() if oa_str else None

                if not pub_year:
                    with contextlib.suppress(ValueError, TypeError):
                        pub_year = int(row.get("Publication Year", ""))

                insert_publication(
                    conn,
                    project_id,
                    doi=doi or None,
                    title=title,
                    publication_year=pub_year,
                    journal="Journal of Open Hardware",
                    cited_by_count=cited_by,
                    open_access=open_access,
                )

                count += 1

        return count
