"""Tests for enrichment modules."""

from pathlib import Path

import orjson
import pytest

from osh_datasets.db import (
    init_db,
    open_connection,
    transaction,
    upsert_project,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database and return its path."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestGitHubEnrichment:
    """Tests for GitHub enrichment pipeline."""

    def test_enriches_matching_project(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Should update an existing project with GitHub metadata."""
        from osh_datasets.enrichment.github import enrich_from_github

        # Insert a project with a GitHub repo URL
        with transaction(db_path) as conn:
            upsert_project(
                conn,
                source="hackaday",
                source_id="123",
                name="Test Project",
                repo_url="https://github.com/testowner/testrepo",
            )

        # Create fake scraped data
        scraped = [
            {
                "repository": {
                    "owner": "testowner",
                    "name": "testrepo",
                    "full_name": "testowner/testrepo",
                    "description": "A test repo",
                    "url": "https://github.com/testowner/testrepo",
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": "2024-06-01T00:00:00Z",
                    "pushed_at": "2024-06-01T12:00:00Z",
                    "size": 1024,
                    "default_branch": "main",
                    "language": "Python",
                    "license": "MIT License",
                    "archived": False,
                    "private": False,
                },
                "metrics": {
                    "stars": 42,
                    "forks": 7,
                    "watchers": 10,
                    "open_issues": 3,
                    "total_issues": 15,
                    "open_prs": 1,
                    "closed_prs": 8,
                    "total_prs": 9,
                    "releases_count": 5,
                    "branches_count": 3,
                    "tags_count": 5,
                    "contributors_count": 4,
                },
                "activity": {
                    "contributors": [
                        {"login": "alice", "contributions": 100},
                        {"login": "bob", "contributions": 50},
                    ],
                    "recent_releases": [],
                    "languages": {"Python": 5000, "C": 1000},
                    "topics": ["hardware", "3d-printing"],
                },
                "community": {"health_percentage": 85},
                "readme": {"exists": True, "size": 2048},
                "bom": {
                    "has_bom": True,
                    "bom_files": ["hardware/bom.csv", "pcb/BOM.xlsx"],
                },
                "file_tree": {"total_files": 120, "truncated": False},
            }
        ]
        json_path = tmp_path / "github_repos.jsonl"
        json_path.write_bytes(
            b"\n".join(orjson.dumps(r) for r in scraped) + b"\n"
        )

        count = enrich_from_github(db_path, json_path)
        assert count == 1

        conn = open_connection(db_path)

        # Check repo_metrics
        row = conn.execute(
            "SELECT repo_url, stars, forks, has_bom, primary_language, "
            "community_health, total_files "
            "FROM repo_metrics WHERE project_id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "https://github.com/testowner/testrepo"
        assert row[1] == 42  # stars
        assert row[2] == 7   # forks
        assert row[3] == 1   # has_bom = True
        assert row[4] == "Python"
        assert row[5] == 85  # community health
        assert row[6] == 120  # total files

        # Check BOM file paths
        bom_rows = conn.execute(
            "SELECT file_path FROM bom_file_paths "
            "WHERE project_id = 1 ORDER BY file_path"
        ).fetchall()
        assert [r[0] for r in bom_rows] == [
            "hardware/bom.csv",
            "pcb/BOM.xlsx",
        ]

        # Check license
        lic = conn.execute(
            "SELECT license_type, license_name FROM licenses "
            "WHERE project_id = 1"
        ).fetchone()
        assert lic is not None
        assert lic[0] == "software"
        assert lic[1] == "MIT License"

        # Check tags (topics)
        tags = conn.execute(
            "SELECT tag FROM tags WHERE project_id = 1 ORDER BY tag"
        ).fetchall()
        assert [t[0] for t in tags] == ["3d-printing", "hardware"]

        # Check contributors
        contribs = conn.execute(
            "SELECT name FROM contributors "
            "WHERE project_id = 1 ORDER BY name"
        ).fetchall()
        assert [c[0] for c in contribs] == ["alice", "bob"]

        conn.close()

    def test_skips_missing_json(self, db_path: Path, tmp_path: Path) -> None:
        """Should return 0 when no JSON file exists."""
        from osh_datasets.enrichment.github import enrich_from_github

        missing = tmp_path / "nonexistent.json"
        count = enrich_from_github(db_path, missing)
        assert count == 0

    def test_skips_unmatched_repos(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        """Should skip repos that don't match any project in the DB."""
        from osh_datasets.enrichment.github import enrich_from_github

        scraped = [
            {
                "repository": {
                    "owner": "unknown",
                    "name": "norepo",
                    "description": "",
                    "created_at": "",
                    "updated_at": "",
                    "pushed_at": "",
                    "size": 0,
                    "language": None,
                    "license": None,
                    "archived": False,
                    "private": False,
                },
                "metrics": {"stars": 0},
                "activity": {},
                "community": {},
                "readme": {},
                "bom": {"has_bom": False, "bom_files": []},
                "file_tree": {"total_files": 0},
            }
        ]
        json_path = tmp_path / "github_repos.jsonl"
        json_path.write_bytes(
            b"\n".join(orjson.dumps(r) for r in scraped) + b"\n"
        )

        count = enrich_from_github(db_path, json_path)
        assert count == 0
