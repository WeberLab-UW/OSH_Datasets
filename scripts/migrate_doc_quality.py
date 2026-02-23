"""One-time migration: create doc quality, README, tree, and LLM tables.

Creates four new tables for the documentation quality scoring system:
  - doc_quality_scores: Track 1 metadata-based scores
  - readme_contents: Raw README text for LLM evaluation
  - repo_file_trees: Repository file tree entries
  - llm_evaluations: Track 2 LLM evaluation results

Safe to run multiple times -- uses CREATE TABLE IF NOT EXISTS.

Usage: uv run python scripts/migrate_doc_quality.py
"""

import sqlite3
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger

logger = get_logger(__name__)

_NEW_TABLES_SQL = """\
CREATE TABLE IF NOT EXISTS doc_quality_scores (
    id                  INTEGER PRIMARY KEY,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    completeness_score  INTEGER NOT NULL,
    coverage_score      INTEGER NOT NULL,
    depth_score         INTEGER NOT NULL,
    open_o_meter_score  INTEGER NOT NULL,
    scored_at           TEXT    NOT NULL,
    UNIQUE(project_id)
);

CREATE TABLE IF NOT EXISTS readme_contents (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    repo_url    TEXT    NOT NULL,
    content     TEXT,
    size_bytes  INTEGER,
    fetched_at  TEXT    NOT NULL,
    UNIQUE(project_id)
);

CREATE TABLE IF NOT EXISTS repo_file_trees (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    file_path   TEXT    NOT NULL,
    file_type   TEXT    NOT NULL,
    size_bytes  INTEGER,
    UNIQUE(project_id, file_path)
);

CREATE TABLE IF NOT EXISTS llm_evaluations (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    prompt_version  TEXT    NOT NULL,
    model_id        TEXT    NOT NULL,
    raw_response    TEXT    NOT NULL,
    project_type    TEXT,
    structure_quality TEXT,
    doc_location    TEXT,
    license_present INTEGER,
    license_type    TEXT,
    license_name    TEXT,
    contributing_present INTEGER,
    contributing_level   INTEGER,
    bom_present     INTEGER,
    bom_completeness TEXT,
    bom_component_count INTEGER,
    assembly_present INTEGER,
    assembly_detail  TEXT,
    assembly_step_count INTEGER,
    hw_design_present INTEGER,
    hw_editable_source INTEGER,
    mech_design_present INTEGER,
    mech_editable_source INTEGER,
    sw_fw_present   INTEGER,
    sw_fw_type      TEXT,
    sw_fw_doc_level TEXT,
    testing_present INTEGER,
    testing_detail  TEXT,
    cost_mentioned  INTEGER,
    suppliers_referenced INTEGER,
    part_numbers_present INTEGER,
    maturity_stage  TEXT,
    hw_license_name  TEXT,
    sw_license_name  TEXT,
    doc_license_name TEXT,
    evaluated_at    TEXT    NOT NULL,
    UNIQUE(project_id, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_dqs_project ON doc_quality_scores(project_id);
CREATE INDEX IF NOT EXISTS idx_readme_project ON readme_contents(project_id);
CREATE INDEX IF NOT EXISTS idx_rft_project ON repo_file_trees(project_id);
CREATE INDEX IF NOT EXISTS idx_llm_project ON llm_evaluations(project_id);
"""


def migrate(db_path: Path = DB_PATH) -> None:
    """Create documentation quality tables on existing database.

    Args:
        db_path: Path to the SQLite database.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Check which tables already exist
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    new_tables = {
        "doc_quality_scores",
        "readme_contents",
        "repo_file_trees",
        "llm_evaluations",
    }
    to_create = new_tables - existing
    if not to_create:
        logger.info("All doc quality tables already exist")
        conn.close()
        return

    conn.executescript(_NEW_TABLES_SQL)
    conn.commit()

    created = new_tables & {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    logger.info("Created tables: %s", ", ".join(sorted(created & to_create)))

    conn.close()


if __name__ == "__main__":
    migrate()
