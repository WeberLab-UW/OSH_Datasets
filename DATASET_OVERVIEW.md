# OSH Datasets -- Data Overview

A unified SQLite database of **10,698 open-source hardware projects** aggregated from 10 platforms, enriched
with GitHub repository metrics, BOM component data, and two-track documentation quality scoring.

## Sources (10 platforms, 10,698 projects)

| Source | Records | What it captures |
|---|---|---|
| hackaday | 5,697 | Hackaday.io project pages (descriptions, tags, engagement metrics) |
| oshwa | 3,052 | OSHWA-certified hardware (country, category, hardware/software/doc licenses) |
| ohx | 567 | HardwareX journal publications (DOIs, BOM data from supplementary files) |
| hardwareio | 515 | Hardware.io open hardware directory listings |
| ohr | 247 | Open Hardware Repository projects (CERN-hosted repos, classified as hardware) |
| osf | 208 | Open Science Framework preregistrations tagged as open hardware |
| kitspace | 186 | Kitspace PCB project registry (Git repos, BOM data) |
| mendeley | 178 | Mendeley Data datasets related to open-source hardware |
| joh | 29 | Journal of Open Hardware publications |
| plos | 19 | PLOS ONE open-hardware papers |

## Cross-platform field coverage matrix

Shows which upstream platform fields map to each unified database column. A dash means the platform
does not provide that field.

| Unified field | hackaday | oshwa | ohr | kitspace | hardwareio | ohx | osf | plos | joh |
|---|---|---|---|---|---|---|---|---|---|
| name | title | projectName | name | project_name | project_name | paper_title | title | - | Title |
| description | description | projectDescription | description | description | - | - | description | - | Abstract Note |
| url | url | projectWebsite | web_url | url | project_url | - | url | - | Url |
| repo_url | github_links | - | http_url_to_repo | repository_link | github | specifications_table.Source file repository | - | Repository_URL | Repository Links |
| documentation_url | - | documentationUrl | - | - | homepage | - | - | - | - |
| author | userName | responsibleParty | - | - | - | authorships | contributors | - | Author |
| country | - | country | - | - | - | - | - | - | - |
| category | - | primaryType + additionalType | - | - | - | specifications_table.Hardware type | category + subjects | - | Item Type |
| tags | tags | projectKeywords | topics | - | - | - | tags | - | - |
| hw_license | - | hardwareLicense | - | - | - | specifications_table.Open source license | - | - | HW_License |
| sw_license | - | softwareLicense | - | - | - | - | - | - | SW_License |
| doc_license | - | documentationLicense | - | - | - | - | - | Rights | Documentation_License |
| created_at | created (epoch) | certificationDate | created_at | - | created | publication_date | created | - | Date |
| updated_at | updated (epoch) | - | - | - | updated | - | modified | - | - |
| doi | - | - | - | - | - | doi (OpenAlex) | - | DOI | DOI |
| engagement | views, likes, followers | - | stars, forks | - | views, likes, collects | - | downloads | - | - |
| bom | - | - | - | bill_of_materials | bill_of_materials | bill_of_materials | - | - | - |
| design_files | - | - | - | gerber_file_link | design_files | - | file_structure | - | - |
| total_cost | - | - | - | - | total_cost | specifications_table.Cost of hardware | - | - | - |
| citations | - | - | - | - | - | cited_by_count (OpenAlex) | - | - | cited_by_count (OpenAlex) |
| open_access | - | - | - | - | - | open_access (OpenAlex) | - | - | open_access (OpenAlex) |

### Platform-specific raw schema notes

- **Hackaday**: Richest engagement data (views, likes, followers). Components array and tags array.
  Timestamps are Unix epoch integers.
- **OSHWA**: Only source with country, tri-license (hw/sw/doc), and structured certification UIDs
  (e.g. "US000001"). Includes projectVersion and previousVersions.
- **OHR**: GitLab-based repos. Namespace metadata. The hw-only subset is filtered via a classifier
  (`ohr_classifier/final_classifications.csv`).
- **Kitspace**: PCB-focused. BOM includes retailer part numbers (DigiKey, Mouser, RS, Newark, Farnell,
  LCSC, JLC Assembly) and gerber file links.
- **Hardware.io**: Design files array with per-file download counts. BOM structure has 19+ unnamed
  columns from variable CSV layouts.
- **OHX (HardwareX)**: Academic papers with specifications tables (hardware name, subject area, cost,
  commercial analog). BOM format varies across papers (3+ styles with different column names and
  currencies). Repository references link to Zenodo/GitHub/etc.
- **OSF**: Research preregistrations. File structure metadata. Contributor lists.
- **PLOS / JOH**: Journal articles enriched via OpenAlex for citation counts and open-access status.
  JOH includes structured hardware cost and repository links.
- **Mendeley**: Dataset records (no native BOM or engagement data).

## Database schema (15 tables)

### Core table

**projects** -- One row per unique (source, source_id) pair.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment surrogate key |
| source | TEXT NOT NULL | Platform name (e.g. "hackaday", "oshwa") |
| source_id | TEXT | Platform-specific identifier |
| name | TEXT NOT NULL | Project title |
| description | TEXT | Free-text description |
| url | TEXT | Project web page |
| repo_url | TEXT | Source code repository URL |
| documentation_url | TEXT | External documentation link |
| author | TEXT | Creator / responsible party |
| country | TEXT | Country of origin (OSHWA only: 29% coverage) |
| category | TEXT | Hardware category (36% coverage) |
| created_at | TEXT | ISO 8601 creation date |
| updated_at | TEXT | ISO 8601 last-modified date |

UNIQUE constraint on (source, source_id). UPSERT semantics: new non-NULL values fill NULLs but do not
overwrite existing data.

### Child tables (all FK to projects.id)

| Table | Rows | Key columns | Notes |
|---|---|---|---|
| licenses | 13,160 | project_id, license_type, license_name | type is "hardware", "software", or "documentation" |
| tags | 60,541 | project_id, tag | Free-text tags/topics |
| contributors | 13,916 | project_id, name, role, permission | Named contributors with optional role |
| metrics | 21,031 | project_id, metric_name, metric_value | Key-value engagement data (views, likes, followers) |
| bom_components | 88,202 | project_id, reference, component_name, quantity, unit_cost, manufacturer, part_number, footprint | Parsed BOM line items (see BOM section) |
| publications | 793 | project_id, doi, title, publication_year, journal, cited_by_count, open_access | Linked journal articles |
| cross_references | 304 | project_id_a, project_id_b, match_type, confidence | Deduplicated project pairs matched across sources |

### GitHub enrichment tables

| Table | Rows | Key columns | Notes |
|---|---|---|---|
| repo_metrics | 7,650 | project_id, repo_url, stars, forks, watchers, open_issues, total_issues, open_prs, closed_prs, total_prs, releases_count, branches_count, tags_count, contributors_count, community_health, primary_language, has_bom, has_readme, repo_size_kb, total_files, archived, pushed_at | One row per project-repo pair. community_health is 0-100. |
| bom_file_paths | 2,792 | project_id, repo_url, file_path, processed, component_count | BOM files detected via pattern match (bom.csv, bill_of_materials.*, parts_list.*, etc.) |
| readme_contents | 7,831 | project_id, repo_url, content, size_bytes, fetched_at | Raw README markdown text |
| repo_file_trees | 2,880,048 | project_id, file_path, file_type, size_bytes | Full tree; file_type is "blob" or "tree" |

### Documentation quality tables

| Table | Rows | Key columns | Notes |
|---|---|---|---|
| doc_quality_scores | 10,698 | project_id, completeness_score, coverage_score, depth_score, open_o_meter_score, scored_at | Track 1: all projects (see scoring detail below) |
| llm_evaluations | 7,024 | project_id, prompt_version, model_id, raw_response, + 30 extracted columns, evaluated_at | Track 2: LLM-based (see scoring detail below) |

### Pricing table

| Table | Rows | Key columns | Notes |
|---|---|---|---|
| component_prices | 60,071 | bom_component_id (FK to bom_components.id), matched_mpn, distributor, unit_price, currency, quantity_break, price_date, price_source | Distributor quotes; see pricing section below |

---

## Field coverage (projects table)

| Field | Non-null | Pct of 10,698 |
|---|---|---|
| description | 9,660 | 90% |
| author | 9,471 | 89% |
| created_at | 9,728 | 91% |
| repo_url | 8,824 | 82% |
| category | 3,868 | 36% |
| documentation_url | 3,191 | 30% |
| country | 3,052 | 29% |

---

## Documentation quality scoring (detailed)

### Track 1: Metadata-based scores (all 10,698 projects)

Stored in `doc_quality_scores` as INTEGER columns. Grounded in five OSH documentation standards:
Open-o-Meter (Bonvoisin & Mies 2018), DIN SPEC 3105-1, OSHWA Certification, Open Know-How v1.0,
and HardwareX Author Guidelines.

#### 1. Completeness score (0-100)

Weighted sum of binary artifact presence checks. Each weight reflects how many of the 5 standards
require that artifact:

| Signal | Points | How detected |
|---|---|---|
| has_bom_any | 20 | BOM components exist, OR bom_file_paths exist, OR repo_metrics.has_bom = 1 |
| has_license | 15 | At least one row in licenses table |
| has_repo | 15 | projects.repo_url is not null/empty |
| has_readme | 10 | repo_metrics.has_readme = 1 |
| has_doc_url | 10 | projects.documentation_url is not null/empty |
| has_description | 10 | projects.description is not null/empty |
| has_contributors | 10 | At least one row in contributors table |
| has_author | 5 | projects.author is not null/empty |
| has_timestamps | 3 | projects.created_at is not null/empty |
| has_tags | 2 | At least one row in tags table |
| **Total** | **100** | |

**Distribution**: min=0, median=70, mean=63.4, max=100.

#### 2. Coverage score (0-100)

Counts how many of 12 documentation dimensions are present, normalized to a percentage:

1. Identity (always 1 -- name is NOT NULL)
2. Description present
3. License present
4. Multiple license types (>= 2 distinct license_type values)
5. Repository present
6. Documentation URL present
7. BOM present (any source)
8. Contributors present
9. Tags present
10. Publication present
11. README present
12. Issue tracker active (total_issues > 0)

Formula: `round(dimensions_present / 12 * 100)`.

**Distribution**: min=17, median=58, mean=56.3, max=92.

#### 3. Depth score (0-100)

Mean of non-null continuous signals, each individually normalized to 0-100:

| Signal | Normalization | Source |
|---|---|---|
| Description length | `min(chars / 500, 1.0) * 100` | projects.description |
| BOM component count | `min(count / 10, 1.0) * 100` | bom_components |
| License specificity | 100 if SPDX-normalized, 50 if any license, NULL otherwise | licenses |
| Community health | Raw value (already 0-100) | repo_metrics.community_health |
| Contributor count | `min(count / 5, 1.0) * 100` | contributors |
| Releases count | `min(count / 3, 1.0) * 100` | repo_metrics.releases_count |
| Recency | `max(0, 100 - years_since_last_push * 20)` | repo_metrics.pushed_at |

Projects with no applicable signals score 0.

**Distribution**: min=0, median=47, mean=53.6, max=100.

#### 4. Open-o-Meter score (0-8)

Exact reproduction of Bonvoisin & Mies (Procedia CIRP 78, 2018). Eight binary dimensions, 1 point each:

| Dim | Criterion | Proxy used |
|---|---|---|
| 1. Design files published | has_repo | repo_url present |
| 2. BOM published | has_bom_any | BOM detected (any method) |
| 3. Assembly instructions | has_assembly_proxy | documentation_url present OR has_readme |
| 4. Editable source format | has_repo | repo_url present (same proxy as dim 1) |
| 5. Open license | has_license | License record exists |
| 6. Version control | has_vcs | repo_url contains github.com or gitlab.com |
| 7. Contribution guide | has_contrib_guide | community_health >= 25 |
| 8. Issue tracker | has_issues | total_issues > 0 |

**Distribution**: min=0, median=6, mean=5.0, max=8.

### Track 2: LLM-based evaluation (7,024 GitHub projects)

Stored in `llm_evaluations`. Evaluated using `gemini-2.5-flash-lite` with prompt version `test_8`.
The LLM reads each project's README (truncated to 10K chars) and file tree (capped at 500 entries /
12K chars) and returns structured JSON across 12 dimensions.

`raw_response` contains the full JSON. Individual fields are extracted into typed columns:

| Column group | Columns | Types |
|---|---|---|
| Structural | project_type (TEXT), structure_quality (TEXT), doc_location (TEXT), maturity_stage (TEXT) | Categorical |
| Licensing | license_present (INT 0/1), license_type (TEXT), license_name (TEXT), hw_license_name (TEXT), sw_license_name (TEXT), doc_license_name (TEXT) | Binary + text |
| Contributing | contributing_present (INT 0/1), contributing_level (INT) | Binary + ordinal |
| BOM | bom_present (INT 0/1), bom_completeness (TEXT), bom_component_count (INT) | Binary + text + count |
| Assembly | assembly_present (INT 0/1), assembly_detail (TEXT), assembly_step_count (INT) | Binary + text + count |
| HW design | hw_design_present (INT 0/1), hw_editable_source (INT 0/1) | Binary |
| Mechanical design | mech_design_present (INT 0/1), mech_editable_source (INT 0/1) | Binary |
| Software/firmware | sw_fw_present (INT 0/1), sw_fw_type (TEXT), sw_fw_doc_level (TEXT) | Binary + text |
| Testing | testing_present (INT 0/1), testing_detail (TEXT) | Binary + text |
| Cost/supply | cost_mentioned (INT 0/1), suppliers_referenced (INT 0/1), part_numbers_present (INT 0/1) | Binary |

**Presence rates** (out of 7,024 evaluated projects):

| Dimension | Projects present | Pct |
|---|---|---|
| hw_design_present | 5,094 | 73% |
| sw_fw_present | 5,534 | 79% |
| license_present | 4,134 | 59% |
| mech_design_present | 2,638 | 38% |
| bom_present | 2,199 | 31% |
| testing_present | 1,906 | 27% |
| suppliers_referenced | 1,346 | 19% |
| assembly_present | 1,170 | 17% |
| contributing_present | 634 | 9% |
| part_numbers_present | 572 | 8% |
| cost_mentioned | 303 | 4% |

---

## BOM and pricing coverage

### BOM components

88,202 parsed BOM line items across 4,293 projects (40% of all projects). Average of 20.5 components per
project with BOM data.

| Source | Projects with BOM | Components |
|---|---|---|
| hackaday | 3,124 | 54,017 |
| ohx | 445 | 9,540 |
| hardwareio | 294 | 5,739 |
| oshwa | 244 | 13,031 |
| kitspace | 181 | 5,435 |
| joh | 4 | 175 |
| plos | 1 | 265 |

Of the 88,202 components: 25,022 (28%) have a manufacturer part number, and 11,368 (13%) have a
unit_cost value from the original source data.

### Component pricing (Nexar API)

60,071 distributor price quotes across 463 unique BOM components in **285 projects** (2.7% of all
projects, 6.6% of projects with BOM data). Pricing was fetched from the Nexar API, which returns quotes
from 87 distributors. Each component may have multiple quotes at different quantity breaks.

| Source | Projects with prices | Priced components | Price quotes |
|---|---|---|---|
| hackaday | 134 | 143 | 19,386 |
| hardwareio | 91 | 168 | 19,691 |
| kitspace | 60 | 152 | 20,994 |

**Top distributors by quote count**: DigiKey (3,399), Win Source (3,218), Avnet (3,085),
Verical (2,853), ODG (2,850), TME (2,719), Mouser (2,595), Farnell (2,369),
element14 APAC (2,273), Future Electronics (2,059).

Price columns: `unit_price` (REAL), `currency` (TEXT, default "USD"), `quantity_break` (INT,
default 1). Keyed UNIQUE on (bom_component_id, distributor, quantity_break).

### BOM file detection (GitHub)

936 projects have at least one BOM file detected in their GitHub repo tree via pattern matching
(2,792 file paths total). Detection patterns: `bom.csv`, `bill_of_materials.*`, `parts_list.*`,
`components.csv`, `*-bom.xml`.

---

## Pipeline

```
scrape (raw JSON) --> clean (standardized CSV) --> load (SQLite)
                                                     |
                                         enrichment (GitHub API,
                                          doc quality, LLM eval,
                                          Nexar pricing)
```

## Access

- **SQLite file**: `data/osh_datasets.db` (566 MB, available as a GitHub Release asset at v0.1.0)
- **Streamlit UI**: `uv run streamlit run app/Home.py` -- browse, filter, visualize, and inspect individual projects
- **Python**: `from osh_datasets.db import open_connection; conn = open_connection()`
