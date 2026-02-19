# OSH_Datasets -- Data Processing TODO

## Source Summary

**Project/Registry sources** (standalone hardware projects):

| Source | Records | Primary Data | Key Strengths | Key Gaps |
|--------|---------|-------------|---------------|----------|
| Hackaday | 5,696 | Project registry | Tags, components, GitHub links (100%), engagement | No license info |
| OSHWA | 3,903 | Certification registry | 3 license types, country, certification date | No direct repo URLs (but 1,938 documentationUrls point to GitHub/GitLab) |
| OHR (GitLab) | 2,457 (1,265 hw) | Code repositories | Full repo metadata, stars, forks | No license field (need to parse repo), no author |
| Kitspace | 197 | PCB projects | Detailed BOM with retailers, gerber files, repo links (93%) | No license, no dates, no engagement |
| Hardware.io | 515 | Project registry | License, design files, BOM, GitHub (45%) | No tags/keywords, no description |
| OSF | 208 | Research projects | Contributors, files, downloads, subjects | License often empty, no external repo URLs |

**Publication sources** (academic papers about hardware -- OpenAlex provides bibliometric enrichment):

| Source | Records | Linked via | OpenAlex Coverage | Key Strengths | Key Gaps |
|--------|---------|-----------|-------------------|---------------|----------|
| OHX (HardwareX) | 572 | Paper title (DOI not in extract) | 638 HardwareX papers | Specs, BOM with costs, source repo URLs (63%) | No paper DOI in JSON extract, no dates |
| JOH | 29 | DOI | 27 of 29 matched (93%) | HW/SW/doc licenses, repo links (90%) | Very small |
| PLOS | 59 git / 40 DAS | DOI | 11 of 40 matched (28%) | Repo URLs, data availability statements | Very small, no project metadata |

**OpenAlex** (704 records) is NOT a standalone source -- it provides bibliometric metadata (DOI, citation counts, keywords, open access status, author affiliations) for the same papers in OHX (638), JOH (34), and PLOS (11). In the database, OpenAlex fields enrich the `publications` table rather than creating separate project records.

## Data Gaps to Address

### High Priority -- Needed for Unified Database

- [ ] **OHX + OpenAlex: Join by paper title** -- OHX JSON extract lacks the paper's own DOI. Match OHX records to OpenAlex HardwareX records by normalized title to link bibliometric data (citations, keywords, OA status) with hardware data (BOM, specs, repo URLs).
- [ ] **JOH + OpenAlex: Join by DOI** -- 93% already match. Enrich JOH records with OpenAlex citation counts, keywords, open access status.
- [ ] **OSHWA: Extract repository URLs** -- `documentationUrl` contains GitHub/GitLab URLs for 1,938 of 3,053 cleaned records. Parse these to populate `repo_url`.
- [ ] **OHR: Map classifier results** -- Join `ohr_classifier/final_classifications.csv` with OHR data to tag hardware vs. non-hardware and include `hw_score`.
- [ ] **Hackaday: Normalize timestamps** -- `created` and `updated` are Unix epoch integers; convert to ISO 8601.
- [ ] **All sources: Normalize license names** -- License strings vary wildly (e.g., "CERN", "CERN-OHL-S-2.0", "Creative Commons Attribution-ShareAlike license"). Build a license normalization lookup.

### Medium Priority -- Improves Completeness

- [ ] **OHX: Extract paper DOIs from full XML** -- The `ohx-allPubs.xml` (53MB) likely contains the paper DOI; the JSON extract only has OSF/reference DOIs. Extracting paper DOIs would enable direct DOI-based joining with OpenAlex.
- [ ] **OHR: Extract license info** -- License data exists in repo files (LICENSE, README) but isn't in the CSV. Could scrape from GitLab API or README content.
- [ ] **Kitspace: Scrape creation dates** -- Not captured in current scrape; may be available from repository metadata via GitHub API.
- [ ] **Kitspace: Extract license from repos** -- Repository links point to GitHub; could fetch license via GitHub API.
- [ ] **OSF: Re-scrape with license focus** -- Many license fields are empty `{}`; may need different API endpoint or fallback.
- [ ] **Hardware.io: Scrape descriptions and tags** -- Not captured in current scrape.
- [ ] **OHR: Extract author/maintainer** -- Available via GitLab API `creator_id` -> user lookup.
- [ ] **PLOS: Expand OpenAlex matching** -- Only 11 of 40 PLOS papers matched; investigate remaining 29 (may need title-based matching or broader DOI normalization).

### Low Priority -- Nice to Have

- [ ] **Hackaday: Parse `components` field** -- Currently stored as string arrays; normalize into structured BOM format.
- [ ] **Cross-source deduplication** -- Projects may appear in multiple sources (e.g., a project on Hackaday AND Kitspace AND OSHWA). Identify overlaps via repo URLs, project names, or DOIs.
- [ ] **OHX: Parse full XML for richer metadata** -- Current JSON extract is a subset; full XML has abstracts, figures, full text.

## Data Processing Steps (for Database Loading)

### Per-Source Cleaning Needed

1. **Hackaday**: Convert epoch timestamps, parse `tags` and `components` from string to lists, extract GitHub owner/repo from `github_links`
2. **OSHWA**: Parse `additionalType`, `projectKeywords`, `citations`, `previousVersions` from string to lists, normalize license names, extract repo URLs from `documentationUrl`
3. **OHR**: Join with classifier output, filter to hardware projects, normalize `topics` from string to list
4. **Kitspace**: Flatten `scraped_data` wrapper, handle `error` field (skip errored records), normalize BOM structure
5. **Hardware.io**: Parse `statistics` dict, normalize `design_files` array, handle null `bill_of_materials` and `total_cost`
6. **OHX + OpenAlex (HardwareX)**: Join by normalized paper title. From OHX: extract `specifications_table` fields, normalize BOM, parse `repository_references` and `Source file repository`. From OpenAlex: extract DOI, citation count, keywords, open access, author affiliations.
7. **JOH + OpenAlex**: Join by DOI. From JOH: parse `Repository Links` and `Other Links` free-text into structured URLs, normalize licenses. From OpenAlex: citation count, keywords, open access.
8. **PLOS + OpenAlex**: Join by DOI where possible. Merge `plos_gitLinks.csv` and `plos_das.csv` on DOI, extract platform info.
9. **OSF**: Extract from nested `license`, `metrics`, `contributors`, `subjects` dicts; handle empty license objects

### Database Schema Notes

- Publication sources (OHX, JOH, PLOS) produce records in BOTH `projects` (hardware details, BOM, repo links) AND `publications` (DOI, citations, journal, open access)
- OpenAlex fields go into the `publications` table, not `projects`
- A project from OHX that also has an OSF link creates entries in `projects` + `publications` + potentially a cross-reference to the OSF project record
