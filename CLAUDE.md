# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OSH_Datasets** is a research repository for collecting, cleaning, classifying, and analyzing Open Source Hardware (OSH) project metadata from multiple online platforms. Scripts scrape APIs and websites, store raw JSON/CSV, then clean and classify the results.

## Architecture

Scripts are standalone and invoked directly from `code/`:

```bash
python code/gh_opt.py
python code/hardwareIO.py
python code/ohx.py
python code/openalex_metadata.py
python code/osf/osf_comprehensive_metadata_collector.py
python ohr_classifier/ohr_final_classifier.py
```

No `pyproject.toml` or test suite exists yet. Planned rewrite into an `osh_datasets` package (Phase 3).

### Data Collection (`code/`)

Each data source has its own scraper, organized by subdirectory:

| Source | Scripts | Method |
|---|---|---|
| GitHub | `gh_data_extraction.py`, `gh_repometrics.py`, `gh_opt.py` | `ghapi` with multi-token rotation (`GitHubTokenManager`) |
| OHR (Open Hardware Repo) | `OHR/*.py` | GitLab API v4 |
| OSHWA | `oshwa/oshwa_raw.py`, `oshwa/oshwa_clean.py` | OSHWA API |
| Hackaday | `Hackaday/Hackaday_KeyRotation_API.py` | Hackaday API with key rotation |
| Kitspace | `kitspace/kitspace_projectURL.py`, `kitspace/kitspace_second.py` | Web scraping |
| Hardware.io | `hardwareIO.py` | BeautifulSoup scraping |
| PLOS | `plos/plos_gitLinks.py`, `plos/plos_das.py` | Article scraping for GitHub links |
| OHX | `ohx.py` | XML parsing (`data/ohx-allPubs.xml`) |
| OpenAlex | `openalex_metadata.py` | OpenAlex REST API |
| OSF | `osf/osf_comprehensive_metadata_collector.py`, `osf/osf_metadata_fetcher.py` | OSF API v2 (nodes/registrations/preprints) |

API tokens are expected via environment variables (`GITHUB_TOKEN`, GitLab `PRIVATE-TOKEN`) or token files.

### OHR Project Classifier (`ohr_classifier/`)

Two-pass heuristic system for labeling GitLab repos as hardware vs. non-hardware:
- **Pass 1:** Feature extraction from repo trees -- file extensions (`.kicad`, `.step`, `.stl`, etc.) and folder names (`hardware`, `pcb`, `cad`)
- **Pass 2:** Rule-based classification with confidence scoring
- Outputs: `final_classifications.csv` / `.json`

### Prompt-Based README Evaluation

`prompt_extract.md` defines a JSON schema for LLM-based extraction of documentation metadata from READMEs (license, BOM completeness, assembly instructions, design file formats) with 0-100 confidence scores. `prompt_extractTune.md` tunes extraction quality. Six strategies tested in `prompt_evaluation/test_1-test_6/`.

### Data Layout

- `data/raw/` -- unprocessed scraper output (hackaday, ohr, oshwa, scientific_literature)
- `data/cleaned/` -- normalized datasets
- `data/ohr/` -- OHR GitLab exports (CSV/JSON) and processing notebook
- `data/osf/` -- OSF metadata dataset, links, and documentation
- `data/journal_of_open_hardware/` -- Journal of Open Hardware papers
- `EDA/` -- exploratory data analysis by source (Hackaday, OHR, OSHWA)

### Key Patterns

- Many scripts use `# %%` cell markers for Jupyter-style execution in VS Code
- Common dependencies: `requests`, `pandas`, `beautifulsoup4`, `ghapi`, `pyyaml`, `lxml`, `py_ascii_tree`
- OSF collector docs: see `data/osf/README.md`

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