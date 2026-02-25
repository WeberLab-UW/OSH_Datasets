#!/usr/bin/env bash
# Background loop for Gemini batch submission.
# Runs `submit` every 5 minutes until all chunks are processed,
# then exits. Self-terminating -- no cleanup needed.
#
# Usage:
#   nohup ./scripts/batch_cron.sh &
#   tail -f data/batch/batch_cron.log

set -euo pipefail

PROJECT_DIR="/Users/nicweber/Desktop/GitHub/OSH_Datasets"
LOG_FILE="$PROJECT_DIR/data/batch/batch_cron.log"
MERGED="$PROJECT_DIR/data/batch/gemini_batch_output.jsonl"
INTERVAL=300  # 5 minutes

cd "$PROJECT_DIR"

# Load GEMINI_API_KEY from .env
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Batch loop started (interval: ${INTERVAL}s)" >> "$LOG_FILE"

while true; do
    # If merged output exists, all chunks are done
    if [[ -f "$MERGED" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') All chunks complete. Exiting." >> "$LOG_FILE"
        exit 0
    fi

    echo "$(date '+%Y-%m-%d %H:%M:%S') Running submit..." >> "$LOG_FILE"
    uv run python -m osh_datasets.enrichment.llm_readme_eval submit >> "$LOG_FILE" 2>&1
    echo "$(date '+%Y-%m-%d %H:%M:%S') Sleeping ${INTERVAL}s" >> "$LOG_FILE"
    echo "---" >> "$LOG_FILE"
    sleep "$INTERVAL"
done
