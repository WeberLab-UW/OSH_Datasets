"""Loader for Hardware.io project data (JSON) and BOM components (CSV).

Loads project metadata from ``hardwareIO_allProjects.json`` and, when
available, normalizes and loads BOM component data from
``hardwareio_bom.csv`` into the ``bom_components`` table.
"""

import contextlib
import sqlite3
from pathlib import Path

import orjson
import polars as pl

from osh_datasets.config import get_logger
from osh_datasets.db import (
    insert_bom_component,
    insert_bom_file_path,
    insert_license,
    insert_metric,
    transaction,
    upsert_project,
)
from osh_datasets.loaders.base import BaseLoader

logger = get_logger(__name__)

# Column name variants mapped to canonical BOM fields.
# Order matters: earlier columns are preferred in coalescing.
_REFERENCE_COLS = (
    "Designator", "Reference", "Ref", "RefDes", "References",
    "ref", "Designation", "Part/Designator", "Ref Name (REFDES)",
    "REFERENCE",
)
_NAME_COLS = (
    "Value", "Description", "Device", "Name", "Part", "Comment",
    "Component", "DESCRIPTION", "value", "value5", "VALUE",
)
_QTY_COLS = (
    "Qty", "Quantity", "Qnty", "Count", "QTY", "QTY:",
    "Quantity Per PCB",
)
_MFR_COLS = (
    "Manufacturer", "MF", "Vendor", "Manufacturer 1",
    "Manufacturer (AVL)",
)
_MPN_COLS = (
    "MPN", "Manufacturer Part", "PartNumber", "Manufacturer P/N",
    "mpn", "PARTNO", "Part Number", "Part No",
    "Manufacture Part Number", "Manufacturer Part Number 1",
    "PART NO AND DESCRIPTION",
)
_COST_COLS = (
    "Cost", "Price", "Unit price $", "Cost/Pcs", "Price/part",
    "Cost (Feb-16)", "Price (Ex. VAT)",
)


def _coalesce_cols(
    df: pl.DataFrame,
    candidates: tuple[str, ...],
    alias: str,
) -> pl.Expr:
    """Build a ``pl.coalesce`` expression for columns that exist.

    Args:
        df: Source dataframe (used to check column existence).
        candidates: Ordered column names to coalesce.
        alias: Output column alias.

    Returns:
        A polars expression producing the coalesced value.
    """
    present = [c for c in candidates if c in df.columns]
    if not present:
        return pl.lit(None).alias(alias)
    exprs = [
        pl.when(pl.col(c) != "").then(pl.col(c))
        for c in present
    ]
    return pl.coalesce(exprs).alias(alias)


def _safe_int_str(val: str | None) -> int | None:
    """Parse a string to int, returning None on failure.

    Args:
        val: String value to parse.

    Returns:
        Parsed integer or None.
    """
    if not val:
        return None
    # Strip whitespace and common formatting
    cleaned = val.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except (ValueError, OverflowError):
        return None


def _safe_float_str(val: str | None) -> float | None:
    """Parse a string to float, returning None on failure.

    Args:
        val: String value to parse.

    Returns:
        Parsed float or None.
    """
    if not val:
        return None
    cleaned = val.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (ValueError, OverflowError):
        return None


def _build_name_lookup(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    """Build a project_name -> project_id lookup for hardwareio.

    Args:
        conn: Active database connection.

    Returns:
        Mapping of lowercased project names to project IDs.
    """
    rows = conn.execute(
        "SELECT id, name FROM projects WHERE source = 'hardwareio'"
    ).fetchall()
    return {str(r[1]).strip().lower(): int(r[0]) for r in rows}


def load_hardwareio_bom(
    db_path: Path,
    bom_csv: Path,
) -> int:
    """Normalize and load Hardware.io BOM components into the database.

    Reads the denormalized ``hardwareio_bom.csv`` (181 variant columns
    from different EDA tools), coalesces them into canonical fields
    (reference, component_name, quantity, unit_cost, manufacturer,
    part_number), matches rows to existing hardwareio projects by
    ``project_name``, and inserts into ``bom_components``.

    Args:
        db_path: Path to the SQLite database.
        bom_csv: Path to the BOM CSV file.

    Returns:
        Number of BOM components inserted.
    """
    if not bom_csv.exists():
        logger.info("No BOM CSV at %s, skipping", bom_csv)
        return 0

    df = pl.read_csv(str(bom_csv), infer_schema_length=0)
    if df.is_empty() or "project_name" not in df.columns:
        logger.warning("BOM CSV empty or missing project_name column")
        return 0

    # Coalesce variant columns into canonical schema
    normalized = df.select(
        pl.col("project_name"),
        _coalesce_cols(df, _REFERENCE_COLS, "reference"),
        _coalesce_cols(df, _NAME_COLS, "component_name"),
        _coalesce_cols(df, _QTY_COLS, "quantity_raw"),
        _coalesce_cols(df, _MFR_COLS, "manufacturer"),
        _coalesce_cols(df, _MPN_COLS, "part_number"),
        _coalesce_cols(df, _COST_COLS, "unit_cost_raw"),
    )

    # Drop rows where all BOM fields are null (no usable data)
    bom_fields = [
        "reference", "component_name", "quantity_raw",
        "manufacturer", "part_number", "unit_cost_raw",
    ]
    normalized = normalized.filter(
        pl.any_horizontal(pl.col(c).is_not_null() for c in bom_fields)
    )

    if normalized.is_empty():
        logger.info("No usable BOM data after normalization")
        return 0

    inserted = 0

    with transaction(db_path) as conn:
        name_to_id = _build_name_lookup(conn)

        for row in normalized.iter_rows(named=True):
            proj_name = str(row["project_name"] or "").strip().lower()
            project_id = name_to_id.get(proj_name)
            if project_id is None:
                continue

            insert_bom_component(
                conn,
                project_id,
                reference=row["reference"],
                component_name=row["component_name"],
                quantity=_safe_int_str(row["quantity_raw"]),
                unit_cost=_safe_float_str(row["unit_cost_raw"]),
                manufacturer=row["manufacturer"],
                part_number=row["part_number"],
            )
            inserted += 1

    logger.info(
        "Loaded %d BOM components from %d rows", inserted, normalized.height
    )
    return inserted


_BOM_FILE_PATTERN = (
    r"(?i)(bom|bill.of.materials|parts.?list|components)"
)


def _load_bom_file_paths(
    db_path: Path,
    design_csv: Path,
) -> int:
    """Record BOM file references from the design files listing.

    Scans ``hardwareio_design_files.csv`` for files matching BOM naming
    patterns and inserts them into the ``bom_file_paths`` table.

    Args:
        db_path: Path to the SQLite database.
        design_csv: Path to the design files CSV.

    Returns:
        Number of BOM file paths inserted.
    """
    if not design_csv.exists():
        return 0

    df = pl.read_csv(str(design_csv), infer_schema_length=0)
    if "file_name" not in df.columns or "project_name" not in df.columns:
        return 0

    bom_files = df.filter(
        pl.col("file_name").str.to_lowercase().str.contains(
            _BOM_FILE_PATTERN
        )
    )
    if bom_files.is_empty():
        return 0

    inserted = 0
    with transaction(db_path) as conn:
        name_to_id = _build_name_lookup(conn)
        for row in bom_files.iter_rows(named=True):
            proj_name = str(row["project_name"] or "").strip().lower()
            project_id = name_to_id.get(proj_name)
            if project_id is None:
                continue
            file_name = str(row["file_name"] or "").strip()
            if file_name:
                insert_bom_file_path(conn, project_id, file_name)
                inserted += 1

    return inserted


class HardwareioLoader(BaseLoader):
    """Load Hardware.io projects and BOM components."""

    source_name = "hardwareio"

    def load(self, db_path: Path) -> int:
        """Read Hardware.io JSON and BOM CSV, inserting into database.

        Loads project metadata first, then normalizes and loads BOM
        component data from ``hardwareio_bom.csv`` if the file exists.

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
                    documentation_url=str(
                        item.get("homepage") or ""
                    ) or None,
                    author=str(
                        item.get("project_author") or ""
                    ) or None,
                    created_at=str(item.get("created") or "") or None,
                    updated_at=str(item.get("updated") or "") or None,
                )

                lic = item.get("license")
                if lic and str(lic).strip():
                    insert_license(
                        conn, project_id, "hardware", str(lic).strip()
                    )

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
                            with contextlib.suppress(
                                ValueError, TypeError
                            ):
                                insert_metric(
                                    conn, project_id, metric_name, int(val)
                                )

                views = item.get("views")
                if views is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        insert_metric(
                            conn, project_id, "views", int(str(views))
                        )

                count += 1

        # Load BOM components if CSV exists
        bom_csv = (
            self.data_dir / "cleaned" / "hardwareio"
            / "hardwareio_bom.csv"
        )
        if bom_csv.exists():
            bom_count = load_hardwareio_bom(db_path, bom_csv)
            logger.info(
                "Loaded %d projects and %d BOM components",
                count,
                bom_count,
            )

        # Load BOM file paths from design files listing
        design_csv = (
            self.data_dir / "cleaned" / "hardwareio"
            / "hardwareio_design_files.csv"
        )
        if design_csv.exists():
            bom_paths = _load_bom_file_paths(db_path, design_csv)
            if bom_paths:
                logger.info(
                    "Recorded %d BOM file paths from design files",
                    bom_paths,
                )

        return count
