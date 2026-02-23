# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Run Commands

```bash
# Install (editable, with dev deps)
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run a single test file or class
uv run pytest tests/test_scrapers.py::TestOshwaScraper -v

# Type checking (strict mode)
uv run mypy src/

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Scrape all sources (requires .env with API keys)
uv run python -m osh_datasets.scrape_all

# Scrape specific sources
uv run python -m osh_datasets.scrape_all oshwa ohr hackaday

# Load cleaned data into SQLite (includes Track 1 doc quality scoring)
uv run python -m osh_datasets.load_all

# GitHub enrichment pipeline (requires GITHUB_TOKEN in .env)
# 1. Scrape: auto-generates repos.txt from DB, fetches metadata + BOM detection
uv run python -m osh_datasets.scrape_all github
# 2. Enrich: loads scraped JSON back into DB (also runs as part of load_all)
uv run python -m osh_datasets.enrichment.github

# Documentation quality scoring (Track 1 -- runs as part of load_all)
uv run python -m osh_datasets.enrichment.doc_quality

# GitHub README + file tree fetching (Track 2 prerequisite, requires GITHUB_TOKEN)
uv run python -m osh_datasets.enrichment.github_readme_tree --limit 100

# LLM evaluation via Gemini Batch API (Track 2, requires GEMINI_API_KEY)
uv run python -m osh_datasets.enrichment.llm_readme_eval prepare
uv run python -m osh_datasets.enrichment.llm_readme_eval submit
uv run python -m osh_datasets.enrichment.llm_readme_eval poll
uv run python -m osh_datasets.enrichment.llm_readme_eval ingest

# One-time migration for new doc quality tables
uv run python scripts/migrate_doc_quality.py
```

## Architecture

The pipeline has three stages: **scrape** (raw JSON) -> **clean** (standardized CSV) -> **load** (SQLite).

### Package layout (`src/osh_datasets/`)

- `config.py` -- paths (`DATA_DIR`, `RAW_DIR`, `CLEANED_DIR`, `DB_PATH`), logging via `get_logger()`, env vars via `require_env()`
- `http.py` -- `build_session()` (retry + backoff) and `rate_limited_get()`. All scrapers share these.
- `token_manager.py` -- `TokenManager` for rotating API tokens (GitHub, GitLab, Hackaday). Loads from YAML files or env vars.
- `db.py` -- SQLite schema (15 tables), `open_connection()` with WAL/FK pragmas, `upsert_project()`, insert helpers for child tables
- `scrapers/` -- 12 scraper modules, each subclassing `BaseScraper` (ABC in `base.py`). Registered in `__init__.py:ALL_SCRAPERS`.
- `loaders/` -- 10 loader modules, each subclassing `BaseLoader` (ABC in `base.py`). Registered in `load_all.py:ALL_LOADERS`.
- `enrichment/` -- post-scrape enrichment modules that update existing DB records:
  - `github.py` -- reads scraped JSON and updates projects with repo metrics, BOM file paths, contributors, topics, and licenses
  - `doc_quality.py` -- Track 1: computes 4 metadata-based doc quality scores (completeness, coverage, depth, open-o-meter) for all projects
  - `github_readme_tree.py` -- fetches README content and file trees from GitHub API for Track 2 LLM evaluation
  - `llm_readme_eval.py` -- Track 2: Gemini Batch API evaluation of README + file tree across 12 dimensions (prepare/submit/poll/ingest workflow)
- `scrape_all.py` -- orchestrator that runs all or filtered scrapers
- `load_all.py` -- orchestrator that inits DB, runs all loaders, then post-processing (dedup, DOI enrichment, license normalization, GitHub enrichment)
- `dedup.py` -- cross-source deduplication via repo URL matching -> `cross_references` table
- `license_normalizer.py` -- maps free-text license names to SPDX identifiers
- `enrich_ohx_dois.py` -- backfills DOI metadata from OpenAlex for HardwareX publications

### Database

SQLite at `data/osh_datasets.db`. 15 tables: `projects` (core), `licenses`, `tags`, `contributors`, `metrics`, `bom_components`, `publications`, `cross_references`, `repo_metrics`, `bom_file_paths`, `component_prices`, `doc_quality_scores`, `readme_contents`, `repo_file_trees`, `llm_evaluations`. All child tables FK to `projects(id)`. Projects uniquely keyed on `(source, source_id)` with UPSERT semantics. `repo_metrics` stores GitHub API data (stars, forks, community health, BOM detection, etc.) keyed UNIQUE on `project_id`. `bom_file_paths` records detected BOM file paths per project. `doc_quality_scores` stores 4 Track 1 scores per project. `readme_contents` and `repo_file_trees` store GitHub data for LLM evaluation. `llm_evaluations` stores Track 2 LLM results (raw JSON + 30+ extracted fields) keyed on `(project_id, prompt_version)`.

### Data directory

```
data/
  raw/<source>/       # Scraper output (JSON)
  cleaned/<source>/   # Standardized CSV for loaders
  batch/              # Gemini batch input/output JSONL files
  osh_datasets.db     # Unified SQLite database
```

### GitHub enrichment pipeline

The GitHub scraper fetches 12 API endpoints per repo (metadata, issues, PRs, releases, contributors, community health, languages, topics, readme, and file tree). BOM detection scans the file tree for files matching hardware BOM naming patterns (bom.csv, bill_of_materials.*, parts_list.*, components.csv, *-bom.xml).

The enrichment module (`enrichment/github.py`) matches scraped repos to existing projects via `repo_url LIKE '%github.com/owner/repo%'` and updates: `repo_metrics` table, `bom_file_paths` table, `licenses`, `tags` (topics), and `contributors`.

The scraper auto-generates `repos.txt` from the database if the file doesn't exist.

### Adding a new source

1. Create `scrapers/<source>.py` subclassing `BaseScraper` with `source_name` and `scrape() -> Path`
2. Register in `scrapers/__init__.py:ALL_SCRAPERS`
3. Create `loaders/<source>.py` subclassing `BaseLoader` with `source_name` and `load(db_path) -> int`
4. Register in `load_all.py:ALL_LOADERS`
5. Add mocked tests in `tests/test_scrapers.py` and `tests/test_loaders.py`

### Key patterns

- All HTTP goes through `build_session()` + `rate_limited_get()` from `http.py`
- Tests mock HTTP via `unittest.mock.patch` on `rate_limited_get` and `build_session`
- BS4 type narrowing: always `isinstance(el, Tag)` before accessing `.get_text()` or `.get()` (mypy strict)
- API keys in `.env`, loaded via `config.require_env()`
- `orjson` for JSON, `polars` for dataframes (never stdlib `json` or `pandas`)

### Documentation quality scoring

Two-track system grounded in 5 OSH documentation standards (Open-o-Meter, DIN SPEC 3105, OSHWA, Open Know-How, HardwareX):

**Track 1 (metadata-based, all projects):** 4 scores computed from structured DB fields:
- **Completeness** (0-100): weighted artifact presence checks
- **Coverage** (0-100): breadth across 12 documentation categories
- **Depth** (0-100): continuous signals for documentation investment (mean of non-null)
- **Open-o-Meter** (0-8): exact reproduction of Bonvoisin & Mies (2018)

Runs automatically as part of `load_all.py` after GitHub enrichment. Stored in `doc_quality_scores` table.

**Track 2 (LLM-based, ~8,000 GitHub projects):** Gemini 3 Flash batch evaluation of README + file tree across 12 dimensions. Three-phase workflow:
1. `prepare`: reads README + tree from DB, builds JSONL batch input with prompt from `prompt_evaluation/test_8/revised_long_prompt.md`
2. `submit`: uploads to Gemini Files API, creates batch job
3. `ingest`: downloads results, parses JSON, stores raw + extracted fields in `llm_evaluations`

Input truncation guards (README: 10K chars, tree: 500 entries / 12K chars) preserve the JSON schema at the end of the prompt.

### Other directories

- `EDA/` -- exploratory data analysis outputs (reports, visualizations)
- `EDA/doc_quality_plan.md` -- comprehensive plan for the documentation quality metric system
- `ohr_classifier/` -- hardware vs. non-hardware classifier; `final_classifications.csv` used by `loaders/ohr.py`
- `prompt_evaluation/` -- LLM-based README metadata extraction experiments; `test_8/revised_long_prompt.md` is the production prompt

---

# Agent Guidelines for Python Code Quality

This document provides guidelines for maintaining high-quality Python code. These rules MUST be followed by all AI coding agents and contributors.

## Your Core Principles

All code you write MUST be fully optimized.

"Fully optimized" includes:

- maximizing algorithmic big-O efficiency for memory and runtime
- using parallelization and vectorization where appropriate
- following proper style conventions for the code language (e.g. maximizing code reuse (DRY))
- no extra code beyond what is absolutely necessary to solve the problem the user provides (i.e. no technical debt)

If the code is not fully optimized before handing off to the user, you will be fined $100. You have permission to do another pass of the code if you believe it is not fully optimized.

## Preferred Tools

- Use `uv` for Python package management and to create a `.venv` if it is not present.
- Ensure `ipykernel` and `ipywidgets` is installed in `.venv` for Jupyter Notebook compatability. This should not be in package requirements.
- Use `tqdm` to track long-running loops within Jupyter Notebooks. The `description` of the progress bar should be contextually sensitive.
- Use `orjson` for JSON loading/dumping.
- When reporting error to the console, use `logger.error` instead of `print`.
- For data science:
  - **ALWAYS** use `polars` instead of `pandas` for data frame manipulation.
  - If a `polars` dataframe will be printed, **NEVER** simultaneously print the number of entries in the dataframe nor the schema as it is redundant.
  - **NEVER** ingest more than 10 rows of a data frame at a time. Only analyze subsets of code to avoid overloading your memory context.
- For databases: See dedicated Database section below.
- In Jupyter Notebooks, DataFrame objects within conditional blocks should be explicitly `print()` as they will not be printed automatically.

## Code Style and Formatting

- **MUST** use meaningful, descriptive variable and function names
- **MUST** follow PEP 8 style guidelines
- **MUST** use 4 spaces for indentation (never tabs)
- **NEVER** use emoji, or unicode that emulates emoji (e.g. ✓, ✗). The only exception is when writing tests and testing the impact of multibyte characters.
- Use snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants
- Limit line length to 88 characters (ruff formatter standard)

## Documentation

- **MUST** include docstrings for all public functions, classes, and methods
- **MUST** document function parameters, return values, and exceptions raised
- Keep comments up-to-date with code changes
- Include examples in docstrings for complex functions

Example docstring:

```python
def calculate_total(items: list[dict], tax_rate: float = 0.0) -> float:
    """Calculate the total cost of items including tax.

    Args:
        items: List of item dictionaries with 'price' keys
        tax_rate: Tax rate as decimal (e.g., 0.08 for 8%)

    Returns:
        Total cost including tax

    Raises:
        ValueError: If items is empty or tax_rate is negative
    """
```

## Type Hints

- **MUST** use type hints for all function signatures (parameters and return values)
- **NEVER** use `Any` type unless absolutely necessary
- **MUST** run mypy and resolve all type errors
- Use `Optional[T]` or `T | None` for nullable types

## Error Handling

- **NEVER** silently swallow exceptions without logging
- **MUST** never use bare `except:` clauses
- **MUST** catch specific exceptions rather than broad exception types
- **MUST** use context managers (`with` statements) for resource cleanup
- Provide meaningful error messages

## Function Design

- **MUST** keep functions focused on a single responsibility
- **NEVER** use mutable objects (lists, dicts) as default argument values
- Limit function parameters to 5 or fewer
- Return early to reduce nesting

## Class Design

- **MUST** keep classes focused on a single responsibility
- **MUST** keep `__init__` simple; avoid complex logic
- Use dataclasses for simple data containers
- Prefer composition over inheritance
- Avoid creating additional class functions if they are not necessary
- Use `@property` for computed attributes

## Testing

- **MUST** write unit tests for all new functions and classes
- **MUST** mock external dependencies (APIs, databases, file systems)
- **MUST** use pytest as the testing framework
- **NEVER** run tests you generate without first saving them as their own discrete file
- **NEVER** delete files created as a part of testing.
- Ensure the folder used for test outputs is present in `.gitignore`
- Follow the Arrange-Act-Assert pattern
- Do not commit commented-out tests

## Imports and Dependencies

- **MUST** avoid wildcard imports (`from module import *`)
- **MUST** document dependencies in `pyproject.toml`
- Use `uv` for fast package management and dependency resolution
- Organize imports: standard library, third-party, local imports
- Use `isort` to automate import formatting

## Python Best Practices

- **NEVER** use mutable default arguments
- **MUST** use context managers (`with` statement) for file/resource management
- **MUST** use `is` for comparing with `None`, `True`, `False`
- **MUST** use f-strings for string formatting
- Use list comprehensions and generator expressions
- Use `enumerate()` instead of manual counter variables

## Database Design and Usage

### Schema Design and Normalization

- **MUST** normalize databases to at least 3NF unless explicitly instructed otherwise
- **MUST** use appropriate data types:
  - Use `TIMESTAMP WITH TIME ZONE` (PostgreSQL) or `DATETIME` (SQLite) for datetime fields
  - Use `ARRAY` types for nested data in PostgreSQL; **NEVER** serialize to `TEXT/JSON` unless necessary
  - Use `JSONB` (not `JSON`) in PostgreSQL for flexible document storage
  - Use `UUID` or `BIGINT` for primary keys; avoid `SERIAL` in new PostgreSQL schemas (prefer `BIGINT GENERATED ALWAYS AS IDENTITY`)
- **MUST** define foreign key constraints to maintain referential integrity
- **MUST** create indexes on:
  - Foreign key columns
  - Columns used frequently in WHERE clauses
  - Columns used in JOIN conditions
  - Columns used in ORDER BY clauses
- **NEVER** create indexes on every column; they slow down writes
- Use composite indexes when filtering on multiple columns together
- Use partial indexes to index only relevant subsets of data
- Document denormalization decisions with clear justification

### SQL Query Patterns and Optimization

- **MUST** use parameterized queries to prevent SQL injection; **NEVER** use string concatenation for query building
- **MUST** avoid N+1 query problems:
  - Use JOINs or `IN` clauses instead of loops with individual queries
  - Use ORM eager loading (`selectinload`, `joinedload`) when appropriate
- **MUST** use `EXPLAIN ANALYZE` to profile slow queries
- Use CTEs (Common Table Expressions) for complex queries to improve readability
- Prefer `EXISTS` over `IN` for subqueries checking existence
- Use `LIMIT` and `OFFSET` with caution; prefer cursor-based pagination for large datasets
- Batch INSERT/UPDATE operations instead of individual row operations
- Use transactions for multi-statement operations to ensure atomicity
- Avoid `SELECT *`; explicitly list required columns
- Use database-level aggregations (COUNT, SUM, AVG) instead of fetching all rows
- For PostgreSQL:
  - Use `RETURNING` clause to get inserted/updated data without additional SELECT
  - Use `ON CONFLICT` for upsert operations
  - Leverage window functions for analytical queries

### ORMs and Database Libraries

#### PostgreSQL

- **MUST** use `psycopg3` (not psycopg2) for new projects
- For async operations, use `asyncpg` (fastest) or `psycopg3` async mode
- **MUST** use connection pooling in production:
  - For sync: `psycopg3.pool.ConnectionPool`
  - For async: `asyncpg.create_pool()` or `psycopg_pool.AsyncConnectionPool`
  - Configure appropriate `min_size` and `max_size` based on load
- Use SQLAlchemy 2.0+ for ORM (with `future=True` engine):
  ```python
  from sqlalchemy import create_engine
  from sqlalchemy.orm import Session

  engine = create_engine("postgresql+psycopg://user:pass@host/db", pool_size=10, max_overflow=20)
  ```

#### SQLite

- Use for development, testing, and embedded applications only
- **MUST** enable foreign keys: `PRAGMA foreign_keys = ON;`
- **MUST** use WAL mode for concurrent access: `PRAGMA journal_mode=WAL;`
- Configure for better performance:
  ```python
  import sqlite3

  conn = sqlite3.connect("db.sqlite3")
  conn.execute("PRAGMA foreign_keys = ON")
  conn.execute("PRAGMA journal_mode = WAL")
  conn.execute("PRAGMA synchronous = NORMAL")
  conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
  ```
- **NEVER** use SQLite for high-write-concurrency production workloads

#### SQLAlchemy Best Practices

- **MUST** use declarative models with type hints:
  ```python
  from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

  class Base(DeclarativeBase):
      pass

  class User(Base):
      __tablename__ = "users"

      id: Mapped[int] = mapped_column(primary_key=True)
      email: Mapped[str] = mapped_column(unique=True, index=True)
      created_at: Mapped[datetime] = mapped_column(server_default=func.now())
  ```
- **MUST** use context managers for sessions:
  ```python
  with Session(engine) as session:
      # operations
      session.commit()
  ```
- Use `session.execute()` with `select()` for querying (SQLAlchemy 2.0 style)
- Use `selectinload()` or `joinedload()` to avoid N+1 queries on relationships
- **NEVER** access relationship attributes outside session scope (causes lazy loads)
- Use `session.expire_on_commit = False` if you need objects after commit

### Database Migrations

- **MUST** use Alembic for schema migrations
- **NEVER** modify migration files after they've been committed and deployed
- **MUST** make migrations backwards compatible when possible
- Use separate migrations for schema changes and data migrations
- Test migrations on production-like data volumes before deploying
- Always include both `upgrade()` and `downgrade()` functions

### Database Testing

- **MUST** mock database calls in unit tests using `unittest.mock` or `pytest-mock`
- For integration tests:
  - Use a separate test database (PostgreSQL) or in-memory SQLite
  - Roll back transactions after each test to maintain isolation
  - Use fixtures to create test data
- Use `pytest-postgresql` or `pytest-sqlalchemy` for automated test database setup
- **NEVER** run tests against production or shared development databases

### Connection Management

- **MUST** use connection pooling in production applications
- **MUST** close connections and sessions properly (use context managers)
- Set appropriate timeouts to prevent connection leaks
- Monitor connection pool metrics (active, idle, waiting)
- For async applications, use async drivers (`asyncpg`, `psycopg3 async`) consistently

## Security

- **NEVER** store secrets, API keys, or passwords in code. Only store them in `.env`.
  - Ensure `.env` is declared in `.gitignore`.
  - **NEVER** print or log URLs to console if they contain an API key.
- **MUST** use environment variables for sensitive configuration
- **NEVER** log sensitive information (passwords, tokens, PII)

## Version Control

- **MUST** write clear, descriptive commit messages
- **NEVER** commit commented-out code; delete it
- **NEVER** commit debug print statements or breakpoints
- **NEVER** commit credentials or sensitive data

## Tools

- **MUST** use Ruff for code formatting and linting (replaces Black, isort, flake8)
- **MUST** use mypy for static type checking
- Use `uv` for package management (faster alternative to pip)
- Use pytest for testing

## Before Committing

- [ ] All tests pass
- [ ] Type checking passes (mypy)
- [ ] Code formatter and linter pass (Ruff)
- [ ] All functions have docstrings and type hints
- [ ] No commented-out code or debug statements
- [ ] No hardcoded credentials

---

**Remember:** Prioritize clarity and maintainability over cleverness.