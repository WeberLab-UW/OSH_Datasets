# Contributing to OSH Datasets

Thank you for your interest in contributing to OSH Datasets. This guide covers how to set up your development environment and submit changes.

## Getting Started

1. Fork and clone the repository:

```bash
git clone https://github.com/your-username/OSH_Datasets.git
cd OSH_Datasets
```

2. Create a virtual environment and install dependencies:

```bash
uv venv
uv pip install -e ".[dev]"
```

3. Copy the environment template and add your API keys:

```bash
cp .env.example .env
# Edit .env with your credentials
```

## Development Workflow

1. Create a branch for your changes:

```bash
git checkout -b feature/your-feature-name
```

2. Make your changes following the code standards below.

3. Run the full check suite before committing:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pytest tests/ -v
```

4. Submit a pull request with a clear description of your changes.

## Code Standards

- **Python 3.11+** with full type hints on all function signatures
- **Ruff** for linting and formatting (88-character line limit)
- **mypy** for static type checking (no unresolved errors)
- **pytest** for testing with mocked external dependencies
- **orjson** for JSON serialization (not stdlib `json`)
- **Polars** for dataframe operations (not pandas)
- Docstrings on all public functions, classes, and methods
- No hardcoded API keys or secrets -- use `.env` and `config.require_env()`

## Adding a New Data Source

### Scraper

1. Create `src/osh_datasets/scrapers/your_source.py`
2. Subclass `BaseScraper` and set `source_name`
3. Implement the `scrape()` method returning a `Path` to the output JSON
4. Register the class in `src/osh_datasets/scrapers/__init__.py` (`ALL_SCRAPERS`)
5. Add mocked tests in `tests/test_scrapers.py`

```python
from pathlib import Path
from osh_datasets.scrapers.base import BaseScraper

class YourScraper(BaseScraper):
    source_name = "your_source"

    def scrape(self) -> Path:
        # Fetch data, write JSON to self.output_dir
        out = self.output_dir / "your_source_data.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out
```

### Loader

1. Create `src/osh_datasets/loaders/your_source.py`
2. Subclass `BaseLoader` and set `source_name`
3. Implement the `load(db_path)` method returning a record count
4. Register the class in `src/osh_datasets/loaders/__init__.py` (`ALL_LOADERS`)
5. Add tests in `tests/test_loaders.py`

## Reporting Issues

Open an issue on GitHub with:

- A clear description of the problem or feature request
- Steps to reproduce (for bugs)
- Expected vs. actual behavior
- Your Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
