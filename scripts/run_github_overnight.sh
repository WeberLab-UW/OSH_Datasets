#!/usr/bin/env bash
# Run the GitHub scraper in a loop, respecting rate limits.
# Each iteration scrapes until the 5000 req/hour budget is exhausted,
# then the scraper's built-in rate-limit handler waits for reset.
# After each run completes (budget spent), enrichment is run on
# whatever data has been collected so far, then the scraper restarts
# to pick up where it left off (JSONL resume).
#
# Usage: nohup bash scripts/run_github_overnight.sh &

set -euo pipefail
cd "$(dirname "$0")/.."

LOG="data/raw/github/overnight.log"
JSONL="data/raw/github/github_repos.jsonl"
mkdir -p data/raw/github

echo "=== GitHub overnight pipeline started at $(date) ===" >> "$LOG"

# With 8008 repos x 12 API calls each = ~96,096 calls needed.
# At 5000/hour, that's ~20 hours. We loop until all repos are done.
# The scraper's resume logic skips already-fetched repos automatically.

MAX_ITERATIONS=25  # Safety cap: 25 iterations x ~400 repos = 10,000 repos max

for i in $(seq 1 $MAX_ITERATIONS); do
    echo "" >> "$LOG"
    echo "--- Iteration $i started at $(date) ---" >> "$LOG"

    # Check how many repos are already done
    if [ -f "$JSONL" ]; then
        DONE=$(wc -l < "$JSONL" | tr -d ' ')
    else
        DONE=0
    fi
    echo "  Repos already in JSONL: $DONE" >> "$LOG"

    # If we've fetched all 8008, we're done
    if [ "$DONE" -ge 8008 ]; then
        echo "  All repos fetched. Exiting loop." >> "$LOG"
        break
    fi

    # Run scraper (it handles rate limit waits internally)
    echo "  Starting scraper..." >> "$LOG"
    uv run python -m osh_datasets.scrape_all github >> "$LOG" 2>&1 || true

    # Count results after this run
    if [ -f "$JSONL" ]; then
        NEW_DONE=$(wc -l < "$JSONL" | tr -d ' ')
    else
        NEW_DONE=0
    fi
    FETCHED_THIS_RUN=$((NEW_DONE - DONE))
    echo "  Fetched this run: $FETCHED_THIS_RUN (total: $NEW_DONE)" >> "$LOG"

    # Run enrichment on all collected data so far
    echo "  Running enrichment..." >> "$LOG"
    uv run python -m osh_datasets.enrichment.github >> "$LOG" 2>&1 || true

    # If nothing new was fetched, we're either done or stuck on rate limits.
    # Wait 10 minutes before retrying to let rate limits reset.
    if [ "$FETCHED_THIS_RUN" -eq 0 ]; then
        echo "  No new repos fetched. Waiting 10 minutes..." >> "$LOG"
        sleep 600
    fi
done

echo "" >> "$LOG"
echo "=== Pipeline finished at $(date) ===" >> "$LOG"

# Final enrichment pass
echo "Running final enrichment..." >> "$LOG"
uv run python -m osh_datasets.enrichment.github >> "$LOG" 2>&1 || true

# Report
if [ -f "$JSONL" ]; then
    TOTAL=$(wc -l < "$JSONL" | tr -d ' ')
else
    TOTAL=0
fi
echo "Final total: $TOTAL repos in JSONL" >> "$LOG"
echo "=== DONE ===" >> "$LOG"
