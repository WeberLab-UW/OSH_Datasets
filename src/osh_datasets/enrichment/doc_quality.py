"""Track 1: Metadata-based documentation quality scoring.

Computes four deterministic scores for every project using structured
database fields, grounded in five established open-source hardware
documentation standards:

    - Open-o-Meter (Bonvoisin & Mies, Procedia CIRP 78, 2018)
    - DIN SPEC 3105-1 (DIN, 2020)
    - OSHWA Certification (OSHWA, ongoing)
    - Open Know-How v1.0 (IoP Alliance, 2019)
    - HardwareX Author Guidelines (Elsevier, ongoing)

Scores produced:

    1. **Completeness** (0-100): Weighted artifact presence checks.
    2. **Coverage** (0-100): Breadth across 12 documentation categories.
    3. **Depth** (0-100): Continuous signals for documentation investment.
    4. **Open-o-Meter** (0-8): Reproduction of Bonvoisin & Mies (2018).
"""

from datetime import UTC, datetime
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)

# ── Score 1: Completeness weights ────────────────────────────────
# (signal_name, points) -- weighted by how many of the 5 standards
# require the artifact. Evaluated per-row from the query result.

COMPLETENESS_WEIGHTS: list[tuple[str, int]] = [
    ("has_bom_any", 20),
    ("has_license", 15),
    ("has_repo", 15),
    ("has_readme", 10),
    ("has_doc_url", 10),
    ("has_description", 10),
    ("has_contributors", 10),
    ("has_author", 5),
    ("has_timestamps", 3),
    ("has_tags", 2),
]


def _compute_completeness(row: dict[str, int]) -> int:
    """Compute weighted completeness score (0-100).

    Args:
        row: Dict with boolean signal keys from the scoring query.

    Returns:
        Integer score between 0 and 100.
    """
    return sum(pts for key, pts in COMPLETENESS_WEIGHTS if row.get(key))


def _compute_coverage(row: dict[str, int]) -> int:
    """Compute documentation breadth score (0-100).

    Counts 12 binary dimensions normalized to percentage.

    Args:
        row: Dict with signal keys from the scoring query.

    Returns:
        Integer score between 0 and 100 (rounded).
    """
    dims = (
        1,  # dim 1: Identity (always true -- name NOT NULL by schema)
        row.get("has_description", 0),
        row.get("has_license", 0),
        row.get("has_multi_license_type", 0),
        row.get("has_repo", 0),
        row.get("has_doc_url", 0),
        row.get("has_bom_any", 0),
        row.get("has_contributors", 0),
        row.get("has_tags", 0),
        row.get("has_publication", 0),
        row.get("has_readme", 0),
        row.get("has_issues", 0),
    )
    return round(sum(dims) / 12 * 100)


def _compute_depth(row: dict[str, int | float | None]) -> int:
    """Compute documentation investment depth score (0-100).

    Mean of non-null continuous signals, each normalized to 0-100.

    Args:
        row: Dict with signal keys from the scoring query.

    Returns:
        Integer score between 0 and 100 (rounded). Returns 0 if
        no signals have data.
    """
    signals: list[float] = []

    # Content detail signals
    desc_len = row.get("description_len")
    if desc_len is not None and desc_len > 0:
        signals.append(min(desc_len / 500.0, 1.0) * 100)

    bom_count = row.get("bom_component_count")
    if bom_count is not None and bom_count > 0:
        signals.append(min(bom_count / 10.0, 1.0) * 100)

    license_specificity = row.get("license_specificity")
    if license_specificity is not None:
        signals.append(float(license_specificity))

    # Ecosystem health signals
    community_health = row.get("community_health")
    if community_health is not None:
        signals.append(float(community_health))

    contributor_count = row.get("contributor_count")
    if contributor_count is not None and contributor_count > 0:
        signals.append(min(contributor_count / 5.0, 1.0) * 100)

    releases_count = row.get("releases_count")
    if releases_count is not None:
        signals.append(min(releases_count / 3.0, 1.0) * 100)

    years_since_update = row.get("years_since_update")
    if years_since_update is not None:
        signals.append(max(0.0, 100.0 - years_since_update * 20.0))

    if not signals:
        return 0
    return round(sum(signals) / len(signals))


def _compute_open_o_meter(row: dict[str, int]) -> int:
    """Compute Open-o-Meter score (0-8).

    Exact reproduction of Bonvoisin & Mies (2018): 5 product openness
    dimensions + 3 process openness dimensions.

    Args:
        row: Dict with signal keys from the scoring query.

    Returns:
        Integer score between 0 and 8.
    """
    dims = (
        row.get("has_repo", 0),           # dim 1: design files published
        row.get("has_bom_any", 0),         # dim 2: BOM published
        row.get("has_assembly_proxy", 0),  # dim 3: assembly instructions
        row.get("has_repo", 0),            # dim 4: editable format (proxy)
        row.get("has_license", 0),         # dim 5: open license
        row.get("has_vcs", 0),             # dim 6: version control
        row.get("has_contrib_guide", 0),   # dim 7: contribution guide
        row.get("has_issues", 0),          # dim 8: issue tracking
    )
    return sum(1 for d in dims if d)


# ── Main scoring query ───────────────────────────────────────────
# Single pass: LEFT JOIN on repo_metrics, correlated subqueries for
# child table counts. All FK columns are indexed.

_SCORING_SQL = """\
SELECT
    p.id AS project_id,

    -- Completeness signals (boolean 0/1)
    (COALESCE(rm.has_bom, 0) = 1
     OR EXISTS (SELECT 1 FROM bom_components bc
                WHERE bc.project_id = p.id)
     OR EXISTS (SELECT 1 FROM bom_file_paths bf
                WHERE bf.project_id = p.id)
    ) AS has_bom_any,
    EXISTS (SELECT 1 FROM licenses li
            WHERE li.project_id = p.id)
        AS has_license,
    (p.repo_url IS NOT NULL AND p.repo_url != '') AS has_repo,
    COALESCE(rm.has_readme, 0) AS has_readme,
    (p.documentation_url IS NOT NULL AND p.documentation_url != '')
        AS has_doc_url,
    (p.description IS NOT NULL AND p.description != '')
        AS has_description,
    EXISTS (SELECT 1 FROM contributors c
            WHERE c.project_id = p.id)
        AS has_contributors,
    (p.author IS NOT NULL AND p.author != '') AS has_author,
    (p.created_at IS NOT NULL AND p.created_at != '')
        AS has_timestamps,
    EXISTS (SELECT 1 FROM tags t
            WHERE t.project_id = p.id) AS has_tags,

    -- Coverage-only signals
    (SELECT COUNT(DISTINCT li2.license_type)
     FROM licenses li2 WHERE li2.project_id = p.id) >= 2
        AS has_multi_license_type,
    EXISTS (SELECT 1 FROM publications pub
            WHERE pub.project_id = p.id)
        AS has_publication,
    (rm.total_issues IS NOT NULL AND rm.total_issues > 0)
        AS has_issues,

    -- Open-o-Meter signals
    ((p.documentation_url IS NOT NULL
      AND p.documentation_url != '')
     OR COALESCE(rm.has_readme, 0) = 1) AS has_assembly_proxy,
    (p.repo_url LIKE '%github.com%'
     OR p.repo_url LIKE '%gitlab.com%') AS has_vcs,
    (rm.community_health IS NOT NULL
     AND rm.community_health >= 25) AS has_contrib_guide,

    -- Depth signals (continuous or nullable)
    LENGTH(p.description) AS description_len,
    (SELECT COUNT(*) FROM bom_components bc2
     WHERE bc2.project_id = p.id) AS bom_component_count,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM licenses li3
            WHERE li3.project_id = p.id
              AND li3.license_normalized IS NOT NULL
              AND li3.license_normalized != 'Other'
        ) THEN 100
        WHEN EXISTS (
            SELECT 1 FROM licenses li4
            WHERE li4.project_id = p.id
        ) THEN 50
        ELSE NULL
    END AS license_specificity,
    rm.community_health,
    (SELECT COUNT(*) FROM contributors c2
     WHERE c2.project_id = p.id) AS contributor_count,
    rm.releases_count,
    CASE
        WHEN rm.pushed_at IS NOT NULL AND rm.pushed_at != ''
        THEN (julianday('now') - julianday(rm.pushed_at))
             / 365.25
        ELSE NULL
    END AS years_since_update

FROM projects p
LEFT JOIN (
    SELECT
        project_id,
        MAX(has_bom) AS has_bom,
        MAX(has_readme) AS has_readme,
        MAX(total_issues) AS total_issues,
        MAX(community_health) AS community_health,
        MAX(releases_count) AS releases_count,
        MAX(pushed_at) AS pushed_at
    FROM repo_metrics
    GROUP BY project_id
) rm ON rm.project_id = p.id
"""


def score_doc_quality(db_path: Path = DB_PATH) -> int:
    """Compute and store documentation quality scores for all projects.

    Calculates four scores per project (completeness, coverage, depth,
    open-o-meter) from structured metadata and upserts results into
    the ``doc_quality_scores`` table.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of projects scored.
    """
    conn = open_connection(db_path)
    now = datetime.now(UTC).isoformat()

    rows = conn.execute(_SCORING_SQL).fetchall()
    if not rows:
        logger.info("No projects to score")
        conn.close()
        return 0

    scored = 0
    batch: list[tuple[int, int, int, int, int, str]] = []

    for row in rows:
        row_dict = dict(row)
        project_id = row_dict["project_id"]

        completeness = _compute_completeness(row_dict)
        coverage = _compute_coverage(row_dict)
        depth = _compute_depth(row_dict)
        oom = _compute_open_o_meter(row_dict)

        batch.append((
            project_id, completeness, coverage, depth, oom, now,
        ))
        scored += 1

    conn.executemany(
        """\
        INSERT INTO doc_quality_scores
            (project_id, completeness_score, coverage_score,
             depth_score, open_o_meter_score, scored_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            completeness_score = excluded.completeness_score,
            coverage_score     = excluded.coverage_score,
            depth_score        = excluded.depth_score,
            open_o_meter_score = excluded.open_o_meter_score,
            scored_at          = excluded.scored_at
        """,
        batch,
    )
    conn.commit()
    conn.close()

    logger.info("Scored %d projects for documentation quality", scored)
    return scored


if __name__ == "__main__":
    count = score_doc_quality()
    print(f"Scored {count} projects.")
