"""End-to-end test of the GitHub scrape -> JSONL -> enrichment -> DB pipeline.

Fetches a small batch of real repos, writes JSONL incrementally,
runs enrichment into the database, and reports results.
"""

import time
from pathlib import Path

import orjson

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection
from osh_datasets.enrichment.github import enrich_from_github
from osh_datasets.scrapers.github import (
    GitHubScraper,
    _extract_owner_repo,
    generate_repo_urls,
)

logger = get_logger(__name__)

BATCH_SIZE = 20
OUTPUT_DIR = Path("data/raw/github")
JSONL_PATH = OUTPUT_DIR / "github_repos.jsonl"


def run_pipeline() -> None:
    """Run scrape + enrich on a small batch and report."""
    # --- Phase 1: Generate repo list ---
    all_urls = generate_repo_urls()
    repos = []
    for u in all_urls[:BATCH_SIZE]:
        parsed = _extract_owner_repo(u)
        if parsed:
            repos.append(parsed)

    print(f"\n{'='*60}")
    print(f"GITHUB PIPELINE TEST - {len(repos)} repos")
    print(f"{'='*60}\n")

    # Show what we're about to fetch
    for i, (owner, repo) in enumerate(repos):
        print(f"  {i+1:2d}. {owner}/{repo}")
    print()

    # --- Phase 2: Scrape to JSONL ---
    # Delete any existing JSONL to start fresh for this test
    if JSONL_PATH.exists():
        JSONL_PATH.unlink()

    print("--- SCRAPING ---")
    scraper = GitHubScraper(output_dir=OUTPUT_DIR)
    start = time.time()
    out_path = scraper.scrape_repos(repos, max_workers=3)
    elapsed = time.time() - start

    # Count lines in JSONL
    lines_written = 0
    if out_path.exists():
        with open(out_path, "rb") as f:
            for line in f:
                if line.strip():
                    lines_written += 1

    print(f"\nScrape complete in {elapsed:.1f}s")
    print(f"  Output: {out_path}")
    print(f"  File size: {out_path.stat().st_size:,} bytes")
    print(f"  Lines written: {lines_written}")

    if lines_written == 0:
        print("\nFAILED: No data written to JSONL. Aborting.")
        return

    # --- Phase 3: Verify JSONL content ---
    print("\n--- JSONL CONTENT CHECK ---")
    with open(out_path, "rb") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            record = orjson.loads(line)
            repo_info = record["repository"]
            metrics = record["metrics"]
            bom = record["bom"]
            print(
                f"  {repo_info['owner']}/{repo_info['name']}: "
                f"stars={metrics['stars']}, "
                f"forks={metrics['forks']}, "
                f"has_bom={bom['has_bom']}, "
                f"bom_files={len(bom['bom_files'])}"
            )

    # --- Phase 4: Run enrichment ---
    print("\n--- ENRICHMENT ---")
    enriched = enrich_from_github(DB_PATH, out_path)
    print(f"  Projects enriched: {enriched}/{lines_written}")

    # --- Phase 5: Verify DB ---
    print("\n--- DATABASE VERIFICATION ---")
    conn = open_connection(DB_PATH)

    # Check repo_metrics table
    row = conn.execute(
        "SELECT COUNT(*) FROM repo_metrics"
    ).fetchone()
    total_metrics = row[0] if row else 0

    # Check a specific enriched repo
    sample = conn.execute(
        "SELECT rm.stars, rm.forks, rm.has_bom, rm.primary_language, "
        "rm.community_health, rm.total_files "
        "FROM repo_metrics rm "
        "JOIN projects p ON p.id = rm.project_id "
        "ORDER BY rm.stars DESC LIMIT 5"
    ).fetchall()

    print(f"  Total repo_metrics rows: {total_metrics}")
    if sample:
        print("  Top repos by stars:")
        for r in sample:
            print(
                f"    stars={r[0]}, forks={r[1]}, "
                f"has_bom={bool(r[2])}, lang={r[3]}, "
                f"health={r[4]}, files={r[5]}"
            )

    # Check bom_file_paths
    bom_row = conn.execute(
        "SELECT COUNT(*) FROM bom_file_paths"
    ).fetchone()
    bom_count = bom_row[0] if bom_row else 0
    print(f"  Total bom_file_paths rows: {bom_count}")

    if bom_count > 0:
        bom_samples = conn.execute(
            "SELECT p.name, bf.file_path "
            "FROM bom_file_paths bf "
            "JOIN projects p ON p.id = bf.project_id "
            "LIMIT 5"
        ).fetchall()
        for b in bom_samples:
            print(f"    {b[0]}: {b[1]}")

    conn.close()

    # --- Report ---
    print(f"\n{'='*60}")
    print("REPORT")
    print(f"{'='*60}")
    print(f"  Repos attempted:  {len(repos)}")
    print(f"  JSONL lines:      {lines_written}")
    print(f"  Enriched in DB:   {enriched}")
    print(f"  Scrape time:      {elapsed:.1f}s")
    success_rate = (lines_written / len(repos) * 100) if repos else 0
    enrich_rate = (enriched / lines_written * 100) if lines_written else 0
    print(f"  Scrape success:   {success_rate:.0f}%")
    print(f"  Enrich match:     {enrich_rate:.0f}%")

    if lines_written == 0:
        print("\n  VERDICT: FAIL - scraper produced no data")
    elif enriched == 0:
        print("\n  VERDICT: PARTIAL - scraper works but enrichment "
              "found no matching projects in DB")
    else:
        print(f"\n  VERDICT: PASS - {enriched} projects enriched")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_pipeline()
