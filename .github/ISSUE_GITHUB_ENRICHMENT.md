# GitHub Enrichment Pipeline: Setup and Execution

**Title:** Run GitHub enrichment pipeline to populate repo metrics and detect BOMs

**Labels:** enhancement, data-pipeline

---

## Summary

The GitHub enrichment pipeline is wired up and ready to run. It fetches comprehensive repository metadata from the GitHub API for all 8,000+ projects in our database that have GitHub repo URLs, and writes the results back into the `repo_metrics` and `bom_file_paths` tables.

## What it does

For each GitHub repository, the scraper hits 12 API endpoints and collects:

- **Repository metadata**: description, language, license, archived status, creation/update/push dates, size
- **Engagement metrics**: stars, forks, watchers, open issues, PRs, releases, branches, tags, contributor count
- **Community health**: GitHub community health percentage (0-100, based on README/LICENSE/CONTRIBUTING/CODE_OF_CONDUCT presence)
- **File tree scan**: full recursive file listing of the repo
- **BOM detection**: scans file tree for Bill of Materials files matching patterns like `bom.csv`, `bill_of_materials.*`, `parts_list.*`, `components.csv`, `*-bom.xml`
- **Topics/tags**: GitHub topic tags
- **Top contributors**: top 10 contributors by commit count

The enrichment module then matches each scraped repo back to existing projects in the database via `repo_url` and updates:
- `repo_metrics` table (one row per project)
- `bom_file_paths` table (one row per detected BOM file)
- `licenses` table (GitHub-detected software license)
- `tags` table (GitHub topics)
- `contributors` table (top 10 contributors)

## Prerequisites

1. **`GITHUB_TOKEN`** -- A GitHub personal access token (classic or fine-grained) with `public_repo` scope. Add to `.env`:
   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```

2. **Database must be populated** -- Run `uv run python -m osh_datasets.load_all` first so project records with GitHub repo URLs exist.

3. **Rate limits** -- GitHub API allows 5,000 requests/hour per token. At ~12 API calls per repo, a single token can process ~416 repos/hour. For 8,051 repos, expect ~19 hours with one token.

   To use multiple tokens for faster throughput, create a YAML file:
   ```yaml
   # github_tokens.yml
   - ghp_token_1
   - ghp_token_2
   - ghp_token_3
   ```
   And set `GITHUB_TOKEN` to any one of them (the `TokenManager` also accepts a `token_file` parameter).

## How to run

```bash
# Step 1: Scrape GitHub metadata
# (auto-generates data/raw/github/repos.txt from DB if it doesn't exist)
uv run python -m osh_datasets.scrape_all github

# Step 2: Enrich database with scraped data
uv run python -m osh_datasets.enrichment.github
```

Or, if you re-run the full pipeline, enrichment happens automatically at the end of `load_all`:
```bash
uv run python -m osh_datasets.load_all
```

## Output

After enrichment, you can query the new data:

```sql
-- Projects with BOMs detected
SELECT p.name, p.source, rm.stars, rm.has_bom
FROM projects p
JOIN repo_metrics rm ON rm.project_id = p.id
WHERE rm.has_bom = 1;

-- BOM file paths
SELECT p.name, bf.file_path
FROM bom_file_paths bf
JOIN projects p ON p.id = bf.project_id;

-- Most-starred OSH projects
SELECT p.name, p.source, rm.stars, rm.primary_language
FROM projects p
JOIN repo_metrics rm ON rm.project_id = p.id
ORDER BY rm.stars DESC
LIMIT 20;

-- Community health overview
SELECT p.source, AVG(rm.community_health) as avg_health, COUNT(*) as n
FROM projects p
JOIN repo_metrics rm ON rm.project_id = p.id
GROUP BY p.source
ORDER BY avg_health DESC;
```

## Files involved

- `src/osh_datasets/scrapers/github.py` -- Scraper with BOM detection and auto-URL generation
- `src/osh_datasets/enrichment/github.py` -- Enrichment module (JSON -> DB)
- `src/osh_datasets/db.py` -- Schema (`repo_metrics`, `bom_file_paths` tables)
- `src/osh_datasets/token_manager.py` -- Token rotation for rate limit management
- `tests/test_scrapers.py` -- BOM detection tests
- `tests/test_enrichment.py` -- Enrichment pipeline tests
- `tests/test_db.py` -- New table tests

## Estimated time

- Single token: ~19 hours
- 3 tokens: ~6-7 hours
- Can be interrupted and resumed (re-running skips repos already in `github_repos.json`)

## Checklist

- [ ] Add `GITHUB_TOKEN` to `.env`
- [ ] Verify database is populated (`uv run python -m osh_datasets.load_all`)
- [ ] Run `uv run python -m osh_datasets.scrape_all github`
- [ ] Run `uv run python -m osh_datasets.enrichment.github`
- [ ] Verify results: `SELECT COUNT(*) FROM repo_metrics`
- [ ] Verify BOM detection: `SELECT COUNT(*) FROM bom_file_paths`
