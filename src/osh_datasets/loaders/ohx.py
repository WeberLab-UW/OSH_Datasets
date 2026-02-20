"""Loader for OHX (HardwareX) publication data with OpenAlex enrichment."""

import contextlib
import csv
import re
from pathlib import Path

import orjson

from osh_datasets.db import (
    insert_bom_component,
    insert_license,
    insert_publication,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader

_COST_RE = re.compile(r"[\$,]")


def _safe_float(val: object) -> float | None:
    """Parse a currency string like '$10.79' to float."""
    if val is None:
        return None
    try:
        return float(_COST_RE.sub("", str(val).strip()))
    except (ValueError, TypeError):
        return None


def _safe_int(val: object) -> int | None:
    """Parse a string quantity to int."""
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _normalize_title(title: str) -> str:
    """Lowercase, strip whitespace and punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def _build_openalex_index(csv_path: Path) -> dict[str, dict[str, object]]:
    """Index OpenAlex HardwareX records by normalized title.

    Args:
        csv_path: Path to ``openalex_metadata.csv``.

    Returns:
        Mapping from normalized title to OpenAlex record dict.
    """
    index: dict[str, dict[str, object]] = {}
    if not csv_path.exists():
        return index
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            loc = row.get("primary_location", "")
            if "hardwarex" not in loc.lower() and "hardware-x" not in loc.lower():
                continue
            title = row.get("display_name") or row.get("title") or ""
            norm = _normalize_title(title)
            if norm:
                index[norm] = row
    return index


class OhxLoader(BaseLoader):
    """Load OHX publications, enriched with OpenAlex bibliometric data.

    OHX provides hardware project details (specs, BOM, repo links).
    OpenAlex provides bibliometric enrichment (DOI, citations, OA status).
    They are joined by normalized paper title.
    """

    source_name = "ohx"

    def load(self, db_path: Path) -> int:
        """Read OHX JSON and OpenAlex CSV, join by title, insert into DB.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            Number of projects loaded.
        """
        ohx_path = self.data_dir / "cleaned" / "ohx_allPubs_extract.json"
        with open(ohx_path, "rb") as fh:
            ohx_items: list[dict[str, object]] = orjson.loads(fh.read())

        oa_csv = (
            self.data_dir / "raw" / "scientific_literature" / "openalex_metadata.csv"
        )
        oa_index = _build_openalex_index(oa_csv)

        count = 0
        matched = 0

        with transaction(db_path) as conn:
            for item in ohx_items:
                title = str(item.get("paper_title") or "").strip()
                if not title:
                    continue

                specs = item.get("specifications_table")
                if not isinstance(specs, dict):
                    specs = {}

                repo_url = str(specs.get("Source file repository") or "").strip()
                hw_name = specs.get("Hardware name")
                display_name = str(hw_name).strip() if hw_name else title
                lic = specs.get("Open source license")

                project_id = upsert_project(
                    conn,
                    source="ohx",
                    source_id=_normalize_title(title),
                    name=display_name,
                    url=None,
                    repo_url=repo_url or None,
                    category=str(specs.get("Hardware type") or "") or None,
                )

                if lic and str(lic).strip():
                    insert_license(conn, project_id, "hardware", str(lic).strip())

                bom = item.get("bill_of_materials")
                if isinstance(bom, list):
                    for comp in bom:
                        if not isinstance(comp, dict):
                            continue
                        insert_bom_component(
                            conn,
                            project_id,
                            reference=comp.get("Designator"),
                            component_name=comp.get("Component"),
                            quantity=_safe_int(comp.get("Qty")),
                            unit_cost=_safe_float(comp.get("Unit cost")),
                            manufacturer=comp.get("Source of materials"),
                        )

                # Join with OpenAlex by title
                norm_title = _normalize_title(title)
                oa_row = oa_index.get(norm_title)
                doi: str | None = None
                cited_by: int | None = None
                pub_year: int | None = None
                open_access: bool | None = None

                if oa_row:
                    matched += 1
                    doi_raw = str(oa_row.get("doi") or "")
                    if doi_raw.startswith("https://doi.org/"):
                        doi = doi_raw[16:]
                    elif doi_raw:
                        doi = doi_raw
                    with contextlib.suppress(ValueError, TypeError):
                        cited_by = int(str(oa_row.get("cited_by_count", "")))
                    with contextlib.suppress(ValueError, TypeError):
                        pub_year = int(str(oa_row.get("publication_year", "")))
                    oa_str = str(oa_row.get("open_access") or "")
                    open_access = "true" in oa_str.lower() if oa_str else None

                insert_publication(
                    conn,
                    project_id,
                    doi=doi,
                    title=title,
                    publication_year=pub_year,
                    journal="HardwareX",
                    cited_by_count=cited_by,
                    open_access=open_access,
                )

                count += 1

        from osh_datasets.config import get_logger

        get_logger(__name__).info(
            "OHX: %d/%d matched to OpenAlex by title", matched, count
        )
        return count
