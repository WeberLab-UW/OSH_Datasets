# OSH_Datasets -- Data Processing TODO

## Source Summary

**Project/Registry sources** (standalone hardware projects):

| Source | Records | Primary Data | Key Strengths | Key Gaps |
|--------|---------|-------------|---------------|----------|
| Hackaday | 5,697 | Project registry | Tags, components, GitHub links (100%), engagement | No license info |
| OSHWA | 3,052 | Certification registry | 3 license types, country, certification date | repo URLs extracted from documentationUrl (68%) |
| OHR (GitLab) | 247 | Code repositories (hw-classified) | Full repo metadata, stars, forks, hw_score | No license field (need to parse repo), no author |
| Kitspace | 186 | PCB projects | Detailed BOM with retailers, repo links (99%) | No license, no dates, no engagement |
| Hardware.io | 515 | Project registry | License, design files, GitHub (45%) | No tags/keywords, no description |
| OSF | 208 | Research projects | Contributors, files, downloads, subjects | License often empty, no external repo URLs |

**Publication sources** (academic papers about hardware -- OpenAlex provides bibliometric enrichment):

| Source | Records | Linked via | OpenAlex Coverage | Key Strengths | Key Gaps |
|--------|---------|-----------|-------------------|---------------|----------|
| OHX (HardwareX) | 567 | Paper title + XML DOI backfill | 529 matched by title + 7 by XML | Specs, BOM with costs, source repo URLs (63%) | 31 pubs still lack DOIs |
| JOH | 29 | DOI | 19 with citation counts | HW/SW/doc licenses, repo links (79%) | Very small |
| PLOS | 19 | DOI | 9 in OpenAlex (CSV has bad fields) | Repo URLs, data availability statements | Very small, OpenAlex CSV corrupted |

**OpenAlex** provides bibliometric metadata (DOI, citation counts, open access status) for the same papers in OHX, JOH, and PLOS. In the database, OpenAlex fields enrich the `publications` table rather than creating separate project records.

## Completed

- [x] **OHX + OpenAlex: Join by paper title** -- 529/567 matched. Normalized title matching in `loaders/ohx.py`.
- [x] **JOH + OpenAlex: Join by DOI** -- 19/29 with citation counts. Implemented in `loaders/joh.py`.
- [x] **OSHWA: Extract repository URLs** -- 2,063/3,052 have repo_url (68%). Regex extraction in `loaders/oshwa.py`.
- [x] **OHR: Map classifier results** -- Joined with `final_classifications.csv`, filtered to hardware-only (247 projects). In `loaders/ohr.py`.
- [x] **Hackaday: Normalize timestamps** -- Unix epoch converted to ISO 8601 in `loaders/hackaday.py`.
- [x] **License normalization** -- 202 raw strings mapped to 42 SPDX-style categories via regex rules. `license_normalizer.py` adds `license_normalized` column.
- [x] **OHX: Extract paper DOIs from XML** -- Parsed `ohx-allPubs.xml` (572 articles). 7 additional DOIs backfilled via fuzzy title matching. `enrich_ohx_dois.py`.
- [x] **Cross-source deduplication** -- 304 cross-references found: 134 OHX-OSF (via OSF links), 170 repo URL matches (117 Hackaday-OSHWA, 15 Hackaday-Kitspace, etc.). Stored in `cross_references` table. `dedup.py`.
- [x] **All per-source data cleaning** -- 9 loaders handle all parsing, normalization, and insertion.

## Remaining Data Gaps

### Medium Priority -- Requires API Calls / New Scraping

- [ ] **OHR: Extract license info** -- License data exists in repo files (LICENSE, README) but isn't in the CSV. Could scrape from GitLab API or README content.
- [ ] **Kitspace: Scrape creation dates** -- Not captured in current scrape; may be available from repository metadata via GitHub API.
- [ ] **Kitspace: Extract license from repos** -- Repository links point to GitHub; could fetch license via GitHub API.
- [ ] **OSF: Re-scrape with license focus** -- Many license fields are empty `{}`; may need different API endpoint or fallback.
- [ ] **Hardware.io: Scrape descriptions and tags** -- Not captured in current scrape.
- [ ] **OHR: Extract author/maintainer** -- Available via GitLab API `creator_id` -> user lookup.
- [ ] **PLOS: Re-fetch OpenAlex data** -- Current CSV has corrupted fields (e.g., `cited_by_count = "pdf"`). Need fresh export from OpenAlex API for the 19 PLOS DOIs.

### Low Priority -- Nice to Have

- [ ] **Hackaday: Parse `components` field** -- Currently stored as string arrays; normalize into structured BOM format.
- [ ] **OHX: Parse full XML for richer metadata** -- Current JSON extract is a subset; full XML has abstracts, figures, full text. 31 OHX pubs still lack DOIs (short project names prevent fuzzy matching).

## Database Summary

Built and verified at `data/osh_datasets.db`:

| Table | Records |
|-------|---------|
| projects | 10,520 |
| tags | 50,066 |
| metrics | 21,031 |
| bom_components | 12,783 |
| licenses | 10,025 (normalized to 42 categories) |
| publications | 615 |
| contributors | 456 |
| cross_references | 304 |

**Field coverage:** 87% descriptions, 84% repo URLs, 88% authors, 88% dates, 29% country, 37% category.

**Cross-source overlaps:** 304 links across sources (134 OHX-OSF, 117 Hackaday-OSHWA, 15 Hackaday-Kitspace, 13 OSHWA-Kitspace, 10 Hackaday-Hardware.io, others).
