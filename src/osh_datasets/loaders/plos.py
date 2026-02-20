"""Loader for PLOS article data (git links + data availability statements)."""

import contextlib
import csv
from pathlib import Path

from osh_datasets.db import (
    insert_publication,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader


def _build_openalex_doi_index(
    csv_path: Path,
) -> dict[str, dict[str, str]]:
    """Index OpenAlex PLOS records by normalized DOI.

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
            if "plos" not in loc.lower():
                continue
            doi_raw = row.get("doi", "")
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            if doi:
                index[doi] = row
    return index


class PlosLoader(BaseLoader):
    """Load PLOS article data from ``data/plos/plos_gitLinks.csv``.

    Each record represents a PLOS paper with a linked repository URL.
    Enriched with OpenAlex data where DOIs match.
    """

    source_name = "plos"

    def load(self, db_path: Path) -> int:
        """Read PLOS CSV and insert into database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        git_path = self.data_dir / "plos" / "plos_gitLinks.csv"
        das_path = self.data_dir / "plos" / "plos_das.csv"
        oa_csv = (
            self.data_dir / "raw" / "scientific_literature" / "openalex_metadata.csv"
        )
        oa_index = _build_openalex_doi_index(oa_csv)

        # Build DAS lookup by DOI
        das_lookup: dict[str, str] = {}
        if das_path.exists():
            with open(das_path, newline="") as fh:
                for row in csv.DictReader(fh):
                    doi = (row.get("DOI") or "").strip().lower()
                    das = (row.get("Data_Availability_Statement") or "").strip()
                    if doi and das:
                        das_lookup[doi] = das

        seen: set[str] = set()

        with transaction(db_path) as conn, open(git_path, newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                doi = (row.get("DOI") or "").strip().lower()
                repo_url = (row.get("Repository_URL") or "").strip()
                if not doi or not repo_url:
                    continue

                # Use DOI as project name since PLOS doesn't have titles
                display_name = doi

                # Try OpenAlex for a title
                oa_row = oa_index.get(doi)
                if oa_row:
                    oa_title = oa_row.get("display_name") or oa_row.get("title")
                    if oa_title:
                        display_name = str(oa_title).strip()

                project_id = upsert_project(
                    conn,
                    source="plos",
                    source_id=doi,
                    name=display_name,
                    description=das_lookup.get(doi),
                    repo_url=repo_url,
                )
                seen.add(doi)

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

                insert_publication(
                    conn,
                    project_id,
                    doi=doi,
                    title=display_name,
                    publication_year=pub_year,
                    journal="PLOS",
                    cited_by_count=cited_by,
                    open_access=open_access,
                )

        return len(seen)
