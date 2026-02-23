# Documentation Quality Metric for OSH Projects

## Context

We have 10,698 open-source hardware projects across 10 sources in our database. Each project has varying levels of metadata from its primary platform and supplementary enrichment. There is no way to assess documentation quality across projects.

This plan adds a two-track documentation quality system:

**Track 1 -- Metadata-based scoring:** Four deterministic scores computed from structured DB fields, grounded in five established OSH frameworks. Covers all 10,698 projects. Fast, reproducible, complete coverage.

**Track 2 -- LLM-based evaluation:** Subjective quality scoring of README content + repository file trees using the few-shot prompt from [prompt_evaluation/test_8/revised_long_prompt.md](prompt_evaluation/test_8/revised_long_prompt.md), run on `gemini-3-flash-preview` via **Google Gemini Batch API**. Covers GitHub-linked projects (~8,000). The LLM acts as a trained content analyst: it discovers information metadata never captured (e.g., licenses mentioned in README prose, design files in directory trees), makes calibrated quality judgments (e.g., BOM completeness, assembly detail level), and provides evidence + confidence scores for each judgment. Results are validated against a gold standard dataset.

**Design decisions (from user):**
- Three independent metadata scores, no composite -- avoids subjective inter-dimension weighting
- Include an Open-o-Meter score (0--8) for academic comparability
- Score based on actual data available per project (enrichment already supplements from GitHub, etc.)
- GitHub API data fetching uses existing `TokenManager` (authenticated, 5,000 req/hr); unauthenticated fallback is impractical at ~8,000 projects
- LLM prompt is `test_8/revised_long_prompt.md` (iterated from test_6 through 3 pilots)
- **Model selection: Gemini 3 Flash in batch mode only** -- pilot testing showed 99% inter-model agreement with Haiku 4.5 on original test projects at ~50% lower cost; batch mode adds another 50% discount

### Pilot Validation Summary

Three pilot rounds validated the prompt against 4 diverse projects using both Claude Haiku 4.5 and Gemini 3 Flash:

| Pilot | Prompt | Projects | Agreement (original 3) | Key changes |
|-------|--------|----------|----------------------|-------------|
| 1 (test_6) | 7 dimensions | 3 (rich, medium, sparse) | 91% avg | Baseline; found confidence scale inconsistency, BOM hallucination, assembly threshold ambiguity |
| 2 (test_7) | 12 dimensions | 3 | 92% avg | Added software/firmware, testing, cost/sourcing, project maturity, documentation_location, editable source detection; fixed all pilot 1 bugs |
| 3 (test_8) | 12 dimensions + 11 rules | 4 (+NASA-JPL rover) | **99% avg** (107/108) | Added 3 new critical rules: assembly consistency, framework scoping, license domain assignment, maturity keywords, CPL=part numbers, OSHWA != license |

**Test projects:**
- ESPRI (id=3686, "rich"): ESP32 radio firmware, BOM files, PCB designs, Apache 2.0 license
- Dact nano (id=2622, "medium"): KiCad PCB + FreeCAD mechanical, CERN-OHL-P license
- orcon-usb-dongle (id=4716, "sparse"): 64-char README, 1 file, redirect to external docs
- NASA-JPL Open-Source Rover (id=7346, "testing"): KiCad PCBs, STEP CAD, ROS software, testing/calibration docs, OSHWA certified

**Model comparison decision:** At 99% agreement on original projects, quality differences between Haiku and Gemini Flash are negligible. Gemini 3 Flash costs ~50% less at standard rates ($0.50/$3.00 vs $1.00/$5.00 per 1M in/out tokens) and batch mode halves that again. Estimated batch cost for ~8,000 projects: **~$28** (vs ~$57 Haiku batch, ~$92 Haiku real-time).

**Input truncation guards** (applied during prompt assembly to preserve JSON schema):
- README content: capped at 10,000 characters
- File tree: capped at 500 entries / 12,000 characters
- These limits ensure the JSON output schema and critical rules at the end of the prompt are never truncated

## What We Measure (and What We Don't)

Documentation "quality" ultimately asks: could someone replicate this hardware from the available documentation? We approach that question through two complementary methods at different levels of depth:

| Level | What it tells you | Example | Who provides it |
|-------|------------------|---------|-----------------|
| **1. Existence** (binary) | Does artifact X exist? | "A license file exists" | Metadata (all 10,698 projects) |
| **2. Quantity** (continuous) | How much of artifact X exists? | "The BOM has 47 components" | Metadata (all projects with the artifact) |
| **3. Subjective scoring** (judgment) | What is the quality and type of artifact X? Does evidence support its presence? | "The README mentions components but does not constitute a BOM; the tree contains CERN-OHL-W and CC-BY-SA license files" | LLM evaluation (~8,000 GitHub projects) |

Track 1 (metadata) operates at levels 1--2: deterministic, fast, covering all projects. Track 2 (LLM) operates at level 3: the LLM acts as a trained content analyst following a codebook (the test_8 prompt) with calibration examples (few-shot), making subjective quality judgments that are validated against a gold standard expert-annotated dataset. Neither track can verify whether documentation is *correct* — but Track 2 can judge whether it is *present, substantive, and well-structured*.

**The LLM discovers, not just classifies:** A critical distinction: the LLM does not merely confirm what metadata already knows. It mines the README text and directory tree to **discover information that platform metadata never captured**. For example:
- Metadata records one software license from the platform. The LLM reads the README and finds separate hardware (CERN-OHL-W), software (GPL-3.0), and documentation (CC BY-SA) licenses mentioned in prose.
- Metadata has `has_readme = 1`. The LLM reads the actual README and determines it contains no assembly instructions — only a project description.
- Metadata has no design file detection. The LLM examines the directory tree and finds `.kicad_pcb`, `.step`, and `.stl` files, classifying them as electronic and mechanical design files.

Each LLM judgment comes with **evidence** (direct quotes from the README), **confidence scores** (0.0--1.0 decimal scale with calibrated thresholds), and **reasoning** — making the subjective assessments transparent and auditable.

**Why both tracks:** They measure fundamentally different things and have non-overlapping strengths:

- **Metadata** covers all 10,698 projects deterministically and captures **ecosystem signals** invisible to the LLM (community size, release history, cross-source presence, temporal patterns).
- **LLM** reads unstructured content (README + tree) to make **subjective quality judgments** that metadata cannot: is this BOM complete or just a parts list? Are there actual assembly steps or just a mention? What specific licenses apply to hardware vs software vs documentation?

**Signal reuse across metadata scores:** The same underlying data (e.g., BOM presence) feeds multiple metadata scores. This is intentional — each score asks a different question about the same artifacts. Completeness asks "does it exist?" (weighted by standards importance), Coverage asks "is it one of the breadth categories?" (unweighted count), and Depth asks "how detailed is it?" (continuous quantity). These scores will be correlated because the same documentation effort drives all three, but correlation is not redundancy when the questions differ.

## Foundational Standards

| Standard | Published | Focus | Reference |
|----------|-----------|-------|-----------|
| Open-o-Meter | Bonvoisin & Mies, Procedia CIRP 78, 2018 | 8 binary criteria: 5 product openness + 3 process openness | [ResearchGate](https://www.researchgate.net/publication/329173342) |
| DIN SPEC 3105-1 | DIN, 2020 | Technology-aware technical documentation requirements | [GOSH](https://openhardware.science/2020/08/27/din-spec-3105-explained/) |
| OSHWA Certification | OSHWA, ongoing | Self-certification checklist for open hardware compliance | [OSHWA](https://certification.oshwa.org/requirements.html) |
| Open Know-How v1.0 | IoP Alliance, 2019 | YAML manifest spec with required/recommended metadata fields | [IoP Alliance](https://standards.internetofproduction.org/pub/okh/release/1) |
| HardwareX Author Guidelines | Elsevier, ongoing | Peer-reviewed hardware article submission requirements | [HardwareX](https://www.sciencedirect.com/journal/hardwarex/publish/guide-for-authors) |

## Conceptual Differentiation of the Three Metadata Scores

### Completeness: "Do the essential artifacts exist?" (Level 1 -- existence)

Binary presence checks for documentation artifacts weighted by how many standards require them. A project with all core artifacts present scores 100 regardless of how detailed they are. Answers the question: **Would this project pass a certification checklist?**

Grounded in: OSHWA certification (binary pass/fail checklist), Open-o-Meter (binary 0/1 per dimension), OKH manifest (required vs optional fields).

**Proxy weakness:** Several signals use coarse proxies. Most critically, `has_readme = 1` earns 10 points toward "build instructions" even if the README contains no assembly content. `repo_url` earns 15 points for "design files" even if the repository contains only software. These proxy assumptions are the strongest available from metadata alone; Track 2 (LLM) provides ground truth for the subset of projects it evaluates.

### Coverage: "How many documentation types are represented?" (Level 1 -- existence)

Counts how many distinct documentation categories are populated, with all categories equally weighted. A project documenting 8 of 12 categories scores 67 regardless of the importance of each category. Answers the question: **How broad is the documentation across DIN SPEC 3105's technology-aware categories?**

Grounded in: DIN SPEC 3105 Part 1 (enumerates documentation categories without prioritizing them -- the standard explicitly states requirements depend on technology type and should not be ranked).

**Proxy weakness:** Coverage and Completeness share 8 of the same underlying signals (BOM, license, repo_url, README, doc_url, description, contributors, tags), differing only in weighting (Completeness weights by standards importance; Coverage counts uniformly). Scores will be strongly correlated. They are retained as separate metrics because the questions they answer are conceptually distinct (standards compliance vs. breadth), and downstream researchers may prefer one framing over the other.

### Depth: "How much investment does the documentation infrastructure show?" (Level 2 -- quantity)

Continuous signals measuring the scale and maturity of documentation artifacts and project ecosystem. Only evaluates signals where the underlying data is non-null -- a project with 3 knowable signals averaging 80 scores 80, not penalized for missing data.

Grounded in: DIN SPEC 3105 Part 2 (community-based assessment of documentation quality), HardwareX review criteria (reviewers assess sufficiency and correctness, not just presence).

**What Depth actually contains:** Unlike Completeness and Coverage (which are purely level-1 existence checks), Depth attempts level-2 measurement by using quantity as a proxy for quality. However, many of its signals are better understood as **ecosystem health** indicators (contributor count, release history, recency) rather than **content quality** measures. Only BOM component count directly measures documentation detail. The plan groups signals by what they actually indicate (see Score 3 below) and is explicit about this limitation.

**What Depth does NOT measure:** Depth cannot tell you whether documentation is accurate, well-organized, or sufficient for replication. A project with 100 BOM components and 10 contributors scores high even if the BOM is full of errors and the README is incoherent. Content quality assessment requires Track 2 (LLM classification).

## Score 1: Completeness (0--100)

Each artifact earns fixed points. Points are weighted by how many of the five standards require or recommend that artifact.

| Signal | DB proxy | Pts | Standard basis |
|--------|----------|-----|----------------|
| Has BOM | `repo_metrics.has_bom = 1` OR `bom_components` rows exist OR `bom_file_paths` rows exist | **20** | **5/5**: OoM dim 2 (required), DIN 3105-1 (required for PCBs), OSHWA (required), OKH `bom` (recommended), HardwareX BOM table (required) |
| Has license | `licenses` row exists | **15** | **5/5**: OoM dim 5 (required), DIN 3105-1 (implied by open definition), OSHWA (required, CC-BY/CC-BY-SA), OKH `license` (required), HardwareX (required) |
| Has design files / repo | `projects.repo_url` non-empty | **15** | **4/5**: OoM dims 1+4 (design files published + editable format), DIN 3105-1 (source files in modifiable format), OSHWA (design files publicly available), OKH `project-link` (required) |
| Has README / build instructions | `repo_metrics.has_readme = 1` | **10** | **3/5**: OoM dim 3 (assembly instructions published), DIN 3105-1 (build/assembly instructions), HardwareX Build Instructions section (required) |
| Has documentation URL | `projects.documentation_url` non-empty | **10** | **3/5**: OKH `documentation-home` (required, one of project-link or doc-home), DIN 3105-1 (documentation artifacts), HardwareX (design files in approved repository) |
| Has description | `projects.description` non-empty | **10** | **2/5**: OKH `description` (required), HardwareX Hardware Description section (required) |
| Has contributors | `contributors` row exists | **10** | **2/5**: OKH `contributors` (recommended), OoM dim 7 (contribution guide implies contributors exist) |
| Has author | `projects.author` non-empty | **5** | **2/5**: OKH `manifest-author` (required), OSHWA `responsibleParty` (required) |
| Has timestamps | `projects.created_at` non-empty | **3** | **1/5**: OKH `date-created` (required) |
| Has tags / keywords | `tags` row exists | **2** | **1/5**: OKH `keywords` (recommended, "at least one keyword") |
| **Total** | | **100** | |

## Score 2: Coverage (0--12, normalized to 0--100)

Each dimension is binary (0 or 1). Score = (dimensions present / 12) x 100. All dimensions carry equal weight because coverage measures breadth across DIN SPEC 3105-1's documentation categories, which the standard explicitly does not rank.

| # | Dimension | DB proxy | Standard category |
|---|-----------|----------|-------------------|
| 1 | Identity | `projects.name IS NOT NULL` (always true by schema) | OKH: `title` (required) |
| 2 | Description | `projects.description` non-empty | OKH: `description` (required); HardwareX: Hardware Description |
| 3 | Licensing (any) | `license_count >= 1` | OoM dim 5; OSHWA; OKH: `license`; HardwareX |
| 4 | Licensing (multi-type) | `distinct license_type values >= 2` | OSHWA: separate hw/sw/doc licenses; OKH: `license` supports hw+doc+sw |
| 5 | Version control | `projects.repo_url` non-empty | OoM dim 6; DIN 3105-1: source files |
| 6 | Dedicated documentation | `projects.documentation_url` non-empty | OKH: `documentation-home`; DIN 3105-1 |
| 7 | Bill of materials | BOM detected (any of 3 signals) | OoM dim 2; DIN 3105-1; OSHWA; OKH; HardwareX |
| 8 | Community participation | `contributor_count >= 1` | OoM dim 7; OKH: `contributors`; DIN 3105-2: community assessment |
| 9 | Classification | `tag_count >= 1` | OKH: `keywords` (recommended) |
| 10 | Academic publication | `publication_count >= 1` (has DOI) | HardwareX: peer-reviewed article; OKH: `standards-used` |
| 11 | README / instructions | `repo_metrics.has_readme = 1` | OoM dim 3; DIN 3105-1; HardwareX: Build Instructions |
| 12 | Issue tracking | `repo_metrics.total_issues > 0` | OoM dim 8: bug/issue tracking system |

## Score 3: Depth (0--100)

Continuous signals normalized to 0--100 each. Final score = mean of all signals where the underlying data is non-null. This prevents penalizing projects for data we simply don't have.

Signals are grouped by what they actually measure. This grouping is descriptive (all signals contribute equally to the mean), but makes the composite's composition transparent.

**Content detail signals** -- how much documentation substance exists:

| Signal | Computation | Actually measures | Standard basis |
|--------|------------|-------------------|----------------|
| Description richness | `min(len(description) / 500, 1.0) * 100` | Whether the description goes beyond a one-liner. 500 chars is ~75 words, roughly 2 sentences. This is a crude length proxy, not a semantic quality measure. | HardwareX requires detailed hardware description. |
| BOM detail | `min(bom_component_count / 10, 1.0) * 100` | How many components are individually documented. The only signal that directly measures documentation granularity. Caps at 10; a 10-component and 200-component BOM score identically. | HardwareX requires "a separate row for each component." |
| License specificity | SPDX-recognized: 100; non-SPDX present: 50; none: null | Whether the license is machine-readable (SPDX-mapped). A 3-level ordinal variable, not truly continuous. Projects with non-standard but valid licenses score 50. | OSHWA requires CC-BY/CC-BY-SA; OKH requires SPDX identifiers. |

**Ecosystem health signals** -- how active and collaborative the project is:

| Signal | Computation | Actually measures | Standard basis |
|--------|------------|-------------------|----------------|
| Community health | `repo_metrics.community_health` directly (0--100) | GitHub's composite of README, contributing guide, license, code of conduct, issue/PR templates. Partially overlaps with Completeness (license, README presence). | DIN 3105-2: community-based quality assessment. |
| Contributor diversity | `min(contributor_count / 5, 1.0) * 100` | Whether multiple people contribute. 5+ contributors is full marks. A well-documented solo project scores 20. | DIN 3105-2 requires minimum 2 reviewers; OoM dim 7. |
| Release maturity | `min(releases_count / 3, 1.0) * 100` | Whether formal releases exist. 3+ releases is full marks. Measures versioning discipline, not documentation quality. | OKH `version` and `development-stage` fields. |
| Recency | `max(0, 100 - years_since_last_update * 20)` | How recently the project was updated. Penalizes completed, stable hardware projects equally with abandoned ones -- a known bias. | OKH `date-updated`; HardwareX reviews check currency. |

**Removed from prior version** (were disguised binary checks, not depth signals):
- ~~Tag richness~~ (tag count is metadata completeness, not documentation depth; already captured by Coverage dim 9)
- ~~Cross-source presence~~ (binary 0/100; measures project visibility across platforms, not documentation investment; no meaningful continuous range)

## Score 4: Open-o-Meter (0--8)

Exact reproduction of Bonvoisin & Mies (2018). Each of the 8 dimensions is binary (0 or 1).

| # | Original dimension (from paper) | Category | DB proxy | Limitation |
|---|--------------------------------|----------|----------|------------|
| 1 | Design files are published | Product | `projects.repo_url` non-empty | Cannot distinguish design files from code-only repos |
| 2 | BOM is published | Product | BOM detected (any of 3 signals) | Detects presence, not completeness of BOM |
| 3 | Assembly instructions are published | Product | `documentation_url` non-empty OR `has_readme = 1` | README is a proxy; may not contain assembly instructions |
| 4 | Files in original (editable) format | Product | `projects.repo_url` non-empty | Repos imply source files; cannot verify format type |
| 5 | Open license allowing commercial reuse | Product | `license_count >= 1` | Cannot verify all licenses permit commercial reuse |
| 6 | Version control system used | Process | `projects.repo_url` contains `github.com` or `gitlab.com` | Only detects GitHub/GitLab, not other VCS |
| 7 | Contribution guide published | Process | `repo_metrics.community_health >= 25` | GitHub community health includes contributing guide detection |
| 8 | Bug/issue tracking system used | Process | `repo_metrics.total_issues IS NOT NULL AND total_issues > 0` | Issues > 0 implies active use of tracker |

**Proxy analysis:** Dims 1 and 4 both proxy off `repo_url` because we cannot distinguish source vs. export format from metadata alone. Dim 3 uses `has_readme` which does not confirm assembly content. Dim 5 uses license existence without verifying commercial reuse terms. In total, 5 of 8 dimensions rely on proxies with known validity gaps. For the ~8,000 projects with Track 2 LLM evaluations, the following direct replacements become possible (not used in the score, but available for validation analysis):

| OoM dim | Metadata proxy | LLM replacement | Proxy risk |
|---------|---------------|-----------------|------------|
| 1 | `repo_url` non-empty | `hw_design_present OR mech_design_present` | High false-positive: code-only repos score 1 |
| 3 | `doc_url OR has_readme` | `assembly_present` | High false-positive: any README scores 1 |
| 4 | `repo_url` non-empty | File tree contains editable formats (`.kicad`, `.step`, `.scad`) | High false-positive: same as dim 1 |
| 5 | `license_count >= 1` | `license_name` checked against known open/commercial-use licenses | Medium: proprietary licenses score 1 |
| 7 | `community_health >= 25` | `contributing_level >= 2` | Medium: health score is composite, may not reflect contribution guide |

---

## Track 2: LLM-Based Evaluation

### Overview

The prompt in [test_8/revised_long_prompt.md](prompt_evaluation/test_8/revised_long_prompt.md) is a few-shot codebook that instructs the LLM to act as a trained content analyst. Given a project's README + directory structure, the LLM produces structured JSON with subjective quality judgments across **12 dimensions**:

1. **Metadata**: language, project type (hardware/software/mixed/unclear), structure quality, documentation location
2. **License**: type (explicit/referenced/implied/none), name, per-domain identification (hardware/software/documentation)
3. **Contributing guidelines**: 4-level scale (0=none, 1=brief mention, 2=external reference, 3=detailed process with commands)
4. **BOM**: completeness (complete/basic/partial/none), component extraction
5. **Assembly instructions**: detail level (detailed/basic/referenced/none), step count, with strict threshold (3+ inline steps OR direct link to dedicated assembly doc)
6. **Hardware design files**: types (PCB_Layout/Circuit_Schematic), formats, editable source detection
7. **Mechanical design files**: types (CAD/3D_Printable/Technical_Drawing), formats, editable source detection
8. **Software/firmware**: type (firmware/control_software/driver/library), embedded frameworks only (web frontend frameworks excluded), documentation level
9. **Testing/validation**: detail level (detailed/basic/referenced/none)
10. **Cost and sourcing**: estimated cost, suppliers referenced, part numbers present (CPL files count)
11. **Project maturity**: stage (concept/prototype/production/deprecated/unstated) based on explicit keywords only
12. **Domain-specific licenses**: separate hardware, software, and documentation license identification with domain-assignment rules

Each judgment includes **evidence** (verbatim quotes from the README), **confidence scores** (0.0--1.0 decimal scale with defined calibration thresholds), and **reasoning**. The prompt includes a complete worked example (OpenScout robot) that calibrates the LLM's scoring -- for instance, teaching it that "brief mentions of components do not constitute a bill of materials" and "fewer than 3 specific assembly steps do not constitute assembly instructions." The prompt enforces **11 critical rules** covering evidence requirements, confidence scale, BOM caution, assembly thresholds, framework scoping, license domain assignment, maturity keyword-only classification, and OSHWA certification distinction (certification is not a license).

This requires two pieces of data not currently stored: **README content** and **repository file tree**. The existing GitHub scraper fetches both but discards README content (stores only `download_url`) and discards tree entries (stores only `total_files` count and BOM paths).

### Data Fetching: GitHub API

A new enrichment module fetches README content and full file trees for all projects with a GitHub `repo_url`. Uses existing `TokenManager` with `GITHUB_TOKEN` (5,000 req/hr). All repos are public so authentication is not strictly required, but unauthenticated rate limits (60 req/hr) make it impractical at ~8,000 projects.

**Endpoints:**

| Data | Endpoint | Notes |
|------|----------|-------|
| README content | `GET /repos/{owner}/{repo}/readme` with `Accept: application/vnd.github.raw+json` | Returns raw markdown; no base64 decoding needed |
| File tree | `GET /repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1` | Returns all files; truncates at ~100k entries (flag: `truncated`) |

**Rate limit strategy:** 2 requests per project. ~8,000 GitHub-linked projects = ~16,000 requests. Authenticated: ~3.2 hours. Unauthenticated: ~267 hours (impractical — use TokenManager). The module checks `X-RateLimit-Remaining` and sleeps until reset when exhausted, following the same pattern as [scrapers/github.py](src/osh_datasets/scrapers/github.py).

**Default branch resolution:** `repo_metrics.pushed_at` is already stored, but `default_branch` is not. The module first fetches `GET /repos/{owner}/{repo}` (1 additional request) to get `default_branch`, or uses `main` as fallback.

### Storage: New Tables

```sql
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
    file_type   TEXT    NOT NULL,  -- 'blob' or 'tree'
    size_bytes  INTEGER,
    UNIQUE(project_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_rft_project ON repo_file_trees(project_id);

CREATE TABLE IF NOT EXISTS llm_evaluations (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    prompt_version  TEXT    NOT NULL,  -- 'test_8'
    model_id        TEXT    NOT NULL,  -- 'gemini-3-flash-preview'
    raw_response    TEXT    NOT NULL,  -- full JSON response
    -- Extracted fields for querying:
    project_type    TEXT,    -- hardware|software|mixed|unclear
    structure_quality TEXT,  -- well_structured|basic|poor
    doc_location    TEXT,    -- inline|external_wiki|external_repo|redirect|none
    license_present INTEGER, -- 0 or 1
    license_type    TEXT,    -- explicit|referenced|implied|none
    license_name    TEXT,
    contributing_present INTEGER,
    contributing_level   INTEGER, -- 0-3
    bom_present     INTEGER,
    bom_completeness TEXT,   -- complete|basic|partial|none
    bom_component_count INTEGER,
    assembly_present INTEGER,
    assembly_detail  TEXT,   -- detailed|basic|referenced|none
    assembly_step_count INTEGER,
    hw_design_present INTEGER,
    hw_editable_source INTEGER, -- 0 or 1
    mech_design_present INTEGER,
    mech_editable_source INTEGER, -- 0 or 1
    sw_fw_present   INTEGER, -- 0 or 1
    sw_fw_type      TEXT,    -- firmware|control_software|driver|library|none
    sw_fw_doc_level TEXT,    -- complete|basic|referenced|none
    testing_present INTEGER, -- 0 or 1
    testing_detail  TEXT,    -- detailed|basic|referenced|none
    cost_mentioned  INTEGER, -- 0 or 1
    suppliers_referenced INTEGER, -- 0 or 1
    part_numbers_present INTEGER, -- 0 or 1
    maturity_stage  TEXT,    -- concept|prototype|production|deprecated|unstated
    hw_license_name  TEXT,
    sw_license_name  TEXT,
    doc_license_name TEXT,
    evaluated_at    TEXT    NOT NULL,
    UNIQUE(project_id, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_llm_project ON llm_evaluations(project_id);
```

**Design rationale:**
- `readme_contents` stores raw text for re-use across prompt versions. Separate from `repo_metrics` because README content is large (avg ~5KB, some >100KB) and not always needed.
- `repo_file_trees` stores individual entries to support design-file detection, documentation-file detection, and directory structure formatting. ~8,000 projects x ~200 files avg = ~1.6M rows.
- `llm_evaluations` stores both raw JSON (for future re-parsing) and extracted fields (for SQL queries). Keyed on `(project_id, prompt_version)` to allow re-running with updated prompts without losing prior results.

### LLM Execution Pipeline (Gemini Batch)

New module [enrichment/llm_readme_eval.py](src/osh_datasets/enrichment/llm_readme_eval.py):

**Batch preparation phase** (local, no API cost):
1. **Query candidates:** Projects with rows in `readme_contents` AND `repo_file_trees` but no row in `llm_evaluations` for the current prompt version.
2. **Format directory structure:** Query `repo_file_trees` for the project, render as indented tree text (matching the format in the test_8 example). Cap at 500 entries / 12,000 chars.
3. **Build prompt:** Insert `{directory_structure}` and `{readme_content}` (capped at 10,000 chars) into the `USER_PROMPT_TEMPLATE` from test_8.
4. **Write JSONL batch file:** Each line is one request in Gemini batch format. Output to `data/batch/gemini_batch_input.jsonl`.

**Batch submission phase** (Google Gemini Batch API):
5. **Submit batch job:** Upload JSONL to Google Cloud Storage, submit via Gemini Batch Prediction API.
6. **Poll for completion:** Check batch job status until complete.

**Results ingestion phase** (local):
7. **Download results:** Retrieve batch output JSONL from GCS.
8. **Parse JSON:** Extract the JSON block from each response. Validate required keys. On parse failure, store `raw_response` with extracted fields as NULL.
9. **Upsert results:** `INSERT ... ON CONFLICT(project_id, prompt_version) DO UPDATE`.

**Configuration:**
- `GEMINI_API_KEY` via `.env` (loaded by `config.require_env()`)
- Model: `gemini-3-flash-preview`
- Temperature: 0, max output tokens: 8192
- `--prompt-version` flag (default: `test_8`)

**Cost estimate:** ~8,000 projects using `gemini-3-flash-preview` batch mode. Input: ~5K tokens (prompt template) + ~4K tokens (README + tree) avg = ~9K input. Output: ~1.3K tokens avg. At Gemini 3 Flash batch pricing ($0.25/$1.50 per 1M tokens -- 50% off standard): 72M input tokens = ~$18; 10.4M output tokens = ~$16. **Total: ~$34.**

### How Track 2 Complements Track 1

The two tracks operate at different depths and have asymmetric strengths:

| Aspect | Track 1 (Metadata) | Track 2 (LLM) |
|--------|-------------------|----------------|
| Depth | Existence + quantity (levels 1--2) | Subjective quality judgments (level 3) |
| Project coverage | All 10,698 projects | ~8,000 GitHub-linked projects |
| Computation | Seconds (SQL queries), deterministic | Hours (API calls), probabilistic |
| Ecosystem signals | Stars, forks, contributors, releases, recency, cross-source | Not visible from README + tree |
| Content understanding | None (metadata has no semantic capability) | Reads README prose and directory tree; discovers and judges |

**The LLM discovers information metadata never had:**

The core value of Track 2 is not confirming what metadata already reports — it is **mining unstructured content to find signals invisible to metadata**. Examples:

| What the LLM discovers | How it discovers it | What metadata knows |
|------------------------|--------------------|--------------------|
| Project uses CERN-OHL-W for hardware, GPL-3.0 for software, CC BY-SA for docs | Reads README prose: "Licensed under..." or finds `CERN-OHL-W_LICENSE` in tree | Platform reported one `license_name` (e.g., "GPL-3.0") |
| README mentions components but does not constitute a BOM | Applies codebook: "Brief mentions of components do not constitute a bill of materials" | `has_bom = 0` (correct) or `has_bom = 1` from file tree match (may be wrong) |
| Assembly instructions link to external PDF but no inline steps | Reads README, counts steps, applies threshold: "Fewer than 3 specific steps do not constitute assembly instructions" | `has_readme = 1` (says nothing about assembly content) |
| Repository contains `.kicad_pcb` and `.step` files | Scans directory tree for hardware extensions | `repo_url` non-empty (cannot distinguish design files from code) |
| README is well-structured with headers, tables, and sections | Assesses structure quality against calibration example | No metadata proxy exists |

**The LLM makes calibrated quality judgments:**

Each dimension uses the few-shot example to calibrate what counts as "present." This is where the LLM goes beyond binary detection — it judges whether documentation is substantive enough to be meaningful:

| Dimension | LLM judgment scale | Calibration from prompt |
|-----------|-------------------|------------------------|
| BOM | complete / basic / partial / none | "Brief mentions of components and materials do not constitute a bill of materials" |
| Assembly | detailed (5+ steps) / basic (3-4) / referenced / none | "3+ inline steps OR direct link to dedicated assembly doc; if present=false then detail_level MUST be none" |
| Contributing | level 3 (detailed process) / 2 (external ref) / 1 (brief mention) / 0 | Worked example shows level 3 requires step-by-step commands |
| License | explicit / referenced / implied / none | Distinguishes direct statement from file reference from copyright notice |
| SW/FW doc level | complete / basic / referenced / none | "complete = IDE/toolchain version AND versioned deps AND build/flash commands" |
| Maturity | concept / prototype / production / deprecated / unstated | "Explicit keywords only; no inference from timestamps or 'moved to X'" |
| Confidence | 0.90-1.00 / 0.70-0.89 / 0.50-0.69 / 0.30-0.49 / 0.00-0.29 | "All confidence values MUST be decimals between 0.0 and 1.0" |

These judgments are validated against a gold standard dataset to measure inter-rater reliability.

**What metadata uniquely provides (not available from LLM):**

Temporal signals (recency, release history), community size metrics (stars, forks, contributor count), cross-platform presence, issue/PR activity, and universal coverage across all 10,698 projects regardless of hosting platform. These ecosystem signals reflect project health and maintenance, which the LLM cannot infer from a single README snapshot.

**Cross-validation:** For the ~8,000 projects where both tracks produce results, the LLM's subjective judgments can be compared against metadata proxies to quantify proxy accuracy. For example: "Of projects where `has_readme = 1` (Track 1 awards assembly points), what fraction have `assembly_present = true` (Track 2 confirms actual assembly content)?" This calibration reveals the false-positive rate of metadata proxies and informs how much trust to place in Track 1 scores for projects without LLM evaluation.

## Files to Create/Modify

| File | Change |
|------|--------|
| [db.py](src/osh_datasets/db.py) | Add `doc_quality_scores`, `readme_contents`, `repo_file_trees`, `llm_evaluations` tables to `SCHEMA_SQL`; add upsert helpers |
| [enrichment/doc_quality.py](src/osh_datasets/enrichment/doc_quality.py) | **New** -- Track 1: metadata-based scoring logic |
| [enrichment/github_readme_tree.py](src/osh_datasets/enrichment/github_readme_tree.py) | **New** -- Track 2 data: fetch README content + file trees from GitHub API |
| [enrichment/llm_readme_eval.py](src/osh_datasets/enrichment/llm_readme_eval.py) | **New** -- Track 2 eval: Gemini batch preparation, submission, and results ingestion using test_8 prompt |
| [load_all.py](src/osh_datasets/load_all.py) | Add `score_doc_quality()` call after `enrich_from_github()` |
| [tests/test_doc_quality.py](tests/test_doc_quality.py) | **New** -- unit tests for Track 1 scoring |
| [tests/test_llm_readme_eval.py](tests/test_llm_readme_eval.py) | **New** -- unit tests for Track 2 (prompt formatting, JSON parsing, tree rendering) |
| `scripts/migrate_doc_quality.py` | **New** -- one-time migration for all new tables |

## Implementation Steps

### Step 1: Schema + helper in [db.py](src/osh_datasets/db.py)

Add table to `SCHEMA_SQL`:
```sql
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
CREATE INDEX IF NOT EXISTS idx_dqs_project ON doc_quality_scores(project_id);
```

Add `upsert_doc_quality_score()` following the pattern of existing `upsert_repo_metrics()` in [db.py:320](src/osh_datasets/db.py#L320).

### Step 2: Enrichment module [enrichment/doc_quality.py](src/osh_datasets/enrichment/doc_quality.py)

Module structure:
- Docstring citing all five frameworks with full references
- `COMPLETENESS_WEIGHTS` dict mapping signal names to (points, standard_basis) tuples
- `_compute_completeness(row) -> int`
- `_compute_coverage(row) -> int`
- `_compute_depth(row) -> int`
- `_compute_open_o_meter(row) -> int`
- `score_doc_quality(db_path) -> int` -- orchestrator
- `if __name__ == "__main__":` block

Single query gathers all data in one pass (LEFT JOIN on `repo_metrics`, correlated subqueries for child table counts -- all FK columns are indexed). Batch upsert via `INSERT ... ON CONFLICT(project_id) DO UPDATE`.

### Step 3: Integration in [load_all.py](src/osh_datasets/load_all.py)

Add `score_doc_quality()` call after `enrich_from_github(db_path)` (line 70). Scoring depends on `repo_metrics`, `license_normalized`, and `cross_references` being populated first. Only Track 1 is integrated here -- Track 2 (GitHub fetcher + LLM eval) runs standalone via CLI.

### Step 4: GitHub README + file tree fetcher [enrichment/github_readme_tree.py](src/osh_datasets/enrichment/github_readme_tree.py)

Module structure:
- `_extract_owner_repo(url: str) -> tuple[str, str] | None` -- reuse pattern from [scrapers/github.py](src/osh_datasets/scrapers/github.py)
- `_fetch_readme(session, owner, repo) -> tuple[str | None, int]` -- returns (content, size_bytes)
- `_fetch_file_tree(session, owner, repo, branch) -> list[dict]` -- returns list of `{path, type, size}`
- `_format_directory_tree(entries: list[dict]) -> str` -- renders indented tree text for prompt insertion
- `fetch_readme_and_trees(db_path) -> int` -- orchestrator: queries projects with GitHub `repo_url` missing from `readme_contents`, fetches data, upserts
- `if __name__ == "__main__":` block with `--limit` flag

Uses `TokenManager` with `GITHUB_TOKEN` (required). Monitors `X-RateLimit-Remaining` header and sleeps on exhaustion. Processes projects sequentially with 0.5s delay between repos (matching existing scraper pattern).

**Not integrated into `load_all.py`** -- runs as a standalone enrichment step via CLI because it requires long-running API calls and should not block the main pipeline.

### Step 5: LLM evaluation module [enrichment/llm_readme_eval.py](src/osh_datasets/enrichment/llm_readme_eval.py)

Module structure:
- `PROMPT_SYSTEM` and `PROMPT_USER_TEMPLATE` loaded from [test_8/revised_long_prompt.md](prompt_evaluation/test_8/revised_long_prompt.md) at import time
- `_build_prompt(readme_content: str, directory_tree: str) -> str` -- fills template with input truncation guards (10K chars README, 500 entries / 12K chars tree)
- `_parse_response(raw: str) -> dict | None` -- extracts JSON block, validates required keys
- `_extract_fields(parsed: dict) -> dict` -- flattens nested JSON into column values for `llm_evaluations` (all 36 extracted fields)
- **Batch preparation:** `prepare_batch(db_path, prompt_version) -> Path` -- writes JSONL batch input file
- **Batch submission:** `submit_batch(input_path) -> str` -- submits to Gemini Batch API, returns job ID
- **Batch polling:** `poll_batch(job_id) -> Path` -- polls until complete, downloads results JSONL
- **Results ingestion:** `ingest_batch_results(db_path, results_path, prompt_version) -> int` -- parses results, upserts to DB
- `if __name__ == "__main__":` block with subcommands: `prepare`, `submit`, `ingest`

Model: `gemini-3-flash-preview`. Requires `google-genai` package (add to `pyproject.toml` optional deps under `[project.optional-dependencies] llm = ["google-genai"]`).

**Not integrated into `load_all.py`** -- runs standalone because it incurs API costs and should be opt-in. Batch workflow is: `prepare` -> `submit` -> wait -> `ingest`.

### Step 6: Migration script `scripts/migrate_doc_quality.py`

Creates all four new tables (`doc_quality_scores`, `readme_contents`, `repo_file_trees`, `llm_evaluations`) on existing DB. Pattern: [scripts/migrate_bom_footprint.py](scripts/migrate_bom_footprint.py). Checks `sqlite_master` for existing tables before creating.

### Step 7: Tests

**[tests/test_doc_quality.py](tests/test_doc_quality.py)** -- Track 1:

| Test | Verifies |
|------|----------|
| `test_fully_documented_project` | All fields populated -> high scores across all 4 metrics |
| `test_minimal_project` | Only name/source -> completeness near 0, coverage 1/12, depth 0 |
| `test_bom_via_components` | BOM signal from `bom_components` |
| `test_bom_via_file_paths` | BOM signal from `bom_file_paths` |
| `test_bom_via_repo_metrics` | BOM signal from `repo_metrics.has_bom` |
| `test_depth_ignores_null_signals` | Only non-null signals contribute to depth average |
| `test_open_o_meter_range` | Score always 0--8, max achievable with full metadata |
| `test_idempotent_upsert` | Running twice produces identical results |
| `test_empty_database` | Returns 0, no crashes |

**[tests/test_llm_readme_eval.py](tests/test_llm_readme_eval.py)** -- Track 2:

| Test | Verifies |
|------|----------|
| `test_format_directory_tree` | Tree entries render as indented text matching test_8 example format |
| `test_build_prompt` | Template variables filled; input truncation applied (10K README, 500 entries tree) |
| `test_parse_valid_response` | Well-formed JSON block extracted from LLM response text |
| `test_parse_malformed_response` | Returns None on invalid JSON without crashing |
| `test_extract_fields` | Nested JSON correctly flattened to all 36 column values |
| `test_batch_jsonl_format` | Batch JSONL output has correct Gemini request format per line |
| `test_ingest_batch_results` | Batch result JSONL parsed and upserted correctly |
| `test_skip_already_evaluated` | Projects with existing `llm_evaluations` row are skipped |
| `test_input_truncation` | README > 10K chars and tree > 500 entries are properly truncated |

## Known Limitations

| Limitation | Affects | Severity | Mitigation |
|-----------|---------|----------|------------|
| **Proxy validity**: `has_readme` proxies for assembly instructions; `repo_url` proxies for design files. Both may have high false-positive rates. | Completeness (25 pts), OoM dims 1+3+4 (3 of 8 pts) | High | Track 2 LLM classification provides ground truth for ~8,000 projects; cross-validation quantifies false-positive rates. |
| **Signal correlation**: 8 of 10 Completeness signals also appear in Coverage. `repo_url` feeds 6 slots across 3 scores. Scores are not statistically independent. | All metadata scores | Medium | Correlation is acknowledged and justified (different questions about the same data). Downstream analysis should not assume independence. |
| **Missing data = absence**: Non-GitHub projects have no `repo_metrics`, so README, issues, community health, etc. default to 0 / null. These projects are penalized for lack of observability, not lack of documentation. | Completeness, Coverage (dims 11-12), Depth (4 of 7 signals), OoM (dims 6-8) | High | Depth uses mean-of-non-null to avoid penalizing missing signals. Completeness and Coverage cannot avoid this -- missing data genuinely looks like absence. Researchers should stratify analysis by source platform. |
| **Recency bias**: Depth penalizes projects older than 5 years regardless of documentation completeness. Stable, "finished" hardware designs are scored as stale. | Depth recency signal | Medium | Signal is one of 7 in Depth's non-null mean. Researchers can exclude recency from analysis if studying completed projects. |
| **LLM non-determinism**: Even at `temperature=0`, LLM outputs may vary across runs or model versions. Results are not perfectly reproducible. | Track 2 all fields | Low-medium | Store `model_id` and `prompt_version` with every evaluation. Pilot testing showed 99% inter-model agreement (Haiku vs Gemini) at temperature=0. |
| **Input truncation**: READMEs > 10K chars and trees > 500 entries are truncated. Information in truncated portions is lost. | Track 2, large projects | Low | Affects <5% of projects. Truncation preserves prompt schema/rules. Alternative would require multi-turn or summarization approaches. |
| **OSHWA certification confusion**: LLMs may conflate OSHWA certification with a license. | Track 2 license fields | Low | Critical Rule 12 in test_8 prompt explicitly states OSHWA certification is not a license. |
| **Coverage gap**: Track 2 covers ~8,000 GitHub-linked projects (75% of dataset). The remaining ~2,700 non-GitHub projects have no LLM evaluation. | Track 2 | Low-medium | Track 1 metadata scores provide universal coverage. Most non-GitHub projects are from platforms with richer structured metadata (OSHWA certifications, HardwareX publications). |
| **Quantity != quality**: Depth's BOM detail signal caps at 10 components. A 10-row BOM with no specs scores identically to a 200-row BOM with full sourcing info. | Depth BOM detail | Medium | Track 2 LLM provides `bom_completeness` classification (complete/basic/partial/none) for projects it evaluates. |

## Verification

### Code quality
1. `uv run ruff check src/ tests/`
2. `uv run mypy src/`
3. `uv run pytest tests/test_doc_quality.py tests/test_llm_readme_eval.py -v`

### Track 1: Metadata scoring
4. `uv run python scripts/migrate_doc_quality.py`
5. `uv run python -m osh_datasets.enrichment.doc_quality`
6. Distribution checks:
   - `SELECT completeness_score, COUNT(*) FROM doc_quality_scores GROUP BY completeness_score`
   - `SELECT open_o_meter_score, COUNT(*) FROM doc_quality_scores GROUP BY open_o_meter_score`
7. Sanity check: OSHWA projects (documentation_url + 3 license types) should cluster at top of completeness; HardwareX projects (publication + BOM) should score high on coverage

### Track 2: LLM evaluation (Gemini Batch)
8. `uv run python -m osh_datasets.enrichment.github_readme_tree --limit 10` (fetch 10 READMEs + trees)
9. Verify data: `SELECT COUNT(*) FROM readme_contents; SELECT COUNT(*) FROM repo_file_trees;`
10. `uv run python -m osh_datasets.enrichment.llm_readme_eval prepare` (generate batch JSONL)
11. Inspect batch file: verify JSONL line count matches candidate projects
12. `uv run python -m osh_datasets.enrichment.llm_readme_eval submit` (submit to Gemini Batch API)
13. Wait for batch completion (poll or check manually)
14. `uv run python -m osh_datasets.enrichment.llm_readme_eval ingest` (parse results, upsert to DB)
15. Inspect results: `SELECT project_id, project_type, license_present, bom_present, assembly_present, testing_present, maturity_stage FROM llm_evaluations LIMIT 10;`
16. Validate sample results manually against actual project READMEs

### Full pipeline (after verification)
17. `uv run python -m osh_datasets.enrichment.github_readme_tree` (all GitHub-linked projects)
18. `uv run python -m osh_datasets.enrichment.llm_readme_eval prepare` (all projects with README + tree)
19. `uv run python -m osh_datasets.enrichment.llm_readme_eval submit` (Gemini batch)
20. Wait for batch completion
21. `uv run python -m osh_datasets.enrichment.llm_readme_eval ingest` (load all results)
