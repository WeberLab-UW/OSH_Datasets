"""Tests for Track 2 LLM-based README evaluation module."""

from pathlib import Path
from unittest.mock import patch

import orjson
import pytest

from osh_datasets.db import init_db, open_connection
from osh_datasets.enrichment.llm_readme_eval import (
    _MAX_README_CHARS,
    _MAX_TREE_CHARS,
    _MAX_TREE_ENTRIES,
    _build_user_prompt,
    extract_fields,
    format_directory_tree,
    ingest_batch_results,
    parse_response,
    prepare_batch,
    run_realtime,
)


class TestFormatDirectoryTree:
    """Tests for directory tree formatting."""

    def test_basic_tree(self) -> None:
        """Basic entries render as simple paths."""
        entries = [
            ("README.md", "blob", 1000),
            ("src/main.py", "blob", 500),
            ("src/", "tree", None),
        ]
        result = format_directory_tree(entries)
        assert "README.md" in result
        assert "src/main.py" in result
        assert "src/" in result  # tree type gets trailing slash

    def test_empty_tree(self) -> None:
        """Empty entries produce placeholder."""
        result = format_directory_tree([])
        assert result == "(empty repository)"

    def test_sorted_output(self) -> None:
        """Entries are sorted by path."""
        entries = [
            ("z_file.txt", "blob", 100),
            ("a_file.txt", "blob", 200),
        ]
        result = format_directory_tree(entries)
        lines = result.strip().split("\n")
        assert lines[0] == "a_file.txt"
        assert lines[1] == "z_file.txt"

    def test_entry_cap(self) -> None:
        """Entries beyond _MAX_TREE_ENTRIES are truncated."""
        entries = [
            (f"file_{i:05d}.txt", "blob", 10) for i in range(_MAX_TREE_ENTRIES + 100)
        ]
        result = format_directory_tree(entries)
        lines = [
            line for line in result.strip().split("\n")
            if line and not line.startswith("[")
        ]
        assert len(lines) <= _MAX_TREE_ENTRIES

    def test_char_cap(self) -> None:
        """Tree text beyond _MAX_TREE_CHARS is truncated."""
        # Each entry ~30 chars, so 500 entries at 30 chars each = 15000 > 12000
        entries = [
            (f"very_long_directory_name/file_{i:05d}.txt", "blob", 10)
            for i in range(500)
        ]
        result = format_directory_tree(entries)
        assert "[TREE TRUNCATED]" in result or len(result) <= _MAX_TREE_CHARS + 100


class TestBuildPrompt:
    """Tests for prompt assembly."""

    def test_placeholders_filled(self) -> None:
        """Template placeholders are replaced."""
        template = "Tree:\n{directory_structure}\n\nREADME:\n{readme_content}"
        result = _build_user_prompt(template, "Hello README", "file.txt")
        assert "{directory_structure}" not in result
        assert "{readme_content}" not in result
        assert "Hello README" in result
        assert "file.txt" in result

    def test_readme_truncation(self) -> None:
        """Long README is truncated with marker."""
        template = "{readme_content}"
        long_readme = "x" * (_MAX_README_CHARS + 5000)
        result = _build_user_prompt(template, long_readme, "")
        assert "[README TRUNCATED]" in result
        # Content before truncation marker should be max length
        assert len(result.split("[README TRUNCATED]")[0].strip()) <= _MAX_README_CHARS

    def test_short_readme_not_truncated(self) -> None:
        """Short README passes through unchanged."""
        template = "{readme_content}"
        short_readme = "Short README content"
        result = _build_user_prompt(template, short_readme, "")
        assert result == short_readme


class TestParseResponse:
    """Tests for LLM response JSON extraction."""

    def test_fenced_json(self) -> None:
        """JSON in markdown code fence is extracted."""
        raw = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = parse_response(raw)
        assert result == {"key": "value"}

    def test_bare_json(self) -> None:
        """JSON without fence is extracted."""
        raw = 'Here is the result: {"key": "value"}'
        result = parse_response(raw)
        assert result == {"key": "value"}

    def test_malformed_json(self) -> None:
        """Invalid JSON returns None."""
        raw = "```json\n{invalid json}\n```"
        result = parse_response(raw)
        assert result is None

    def test_no_json(self) -> None:
        """No JSON content returns None."""
        raw = "This response contains no JSON at all."
        result = parse_response(raw)
        assert result is None

    def test_complex_nested_json(self) -> None:
        """Nested JSON structure is parsed correctly."""
        data = {
            "metadata": {"language": "english", "project_type": "hardware"},
            "license": {"present": True, "type": "explicit"},
        }
        raw = f"```json\n{orjson.dumps(data).decode()}\n```"
        result = parse_response(raw)
        assert result is not None
        assert result["metadata"]["language"] == "english"  # type: ignore[index]


class TestExtractFields:
    """Tests for flattening LLM JSON to DB columns."""

    def test_full_extraction(self) -> None:
        """All fields extracted from complete response."""
        parsed = {
            "metadata": {
                "language": "english",
                "project_type": "mixed",
                "structure_quality": "well_structured",
                "documentation_location": "inline",
            },
            "license": {
                "present": True,
                "type": "explicit",
                "name": "Apache-2.0",
            },
            "contributing": {"present": True, "level": 2},
            "bom": {
                "present": True,
                "completeness": "partial",
                "component_count": 15,
            },
            "assembly": {
                "present": True,
                "detail_level": "detailed",
                "step_count": 8,
            },
            "design_files": {
                "hardware": {
                    "present": True,
                    "has_editable_source": True,
                },
                "mechanical": {
                    "present": False,
                    "has_editable_source": False,
                },
            },
            "software_firmware": {
                "present": True,
                "type": "firmware",
                "documentation_level": "basic",
            },
            "testing": {"present": False, "detail_level": "none"},
            "cost_sourcing": {
                "estimated_cost_mentioned": True,
                "suppliers_referenced": False,
                "part_numbers_present": True,
            },
            "project_maturity": {"stage": "production"},
            "specific_licenses": {
                "hardware": {"present": True, "name": "CERN-OHL-S"},
                "software": {"present": True, "name": "MIT"},
                "documentation": {"present": False, "name": None},
            },
        }
        fields = extract_fields(parsed)

        assert fields["project_type"] == "mixed"
        assert fields["structure_quality"] == "well_structured"
        assert fields["doc_location"] == "inline"
        assert fields["license_present"] == 1
        assert fields["license_type"] == "explicit"
        assert fields["license_name"] == "Apache-2.0"
        assert fields["contributing_present"] == 1
        assert fields["contributing_level"] == 2
        assert fields["bom_present"] == 1
        assert fields["bom_completeness"] == "partial"
        assert fields["bom_component_count"] == 15
        assert fields["assembly_present"] == 1
        assert fields["assembly_detail"] == "detailed"
        assert fields["assembly_step_count"] == 8
        assert fields["hw_design_present"] == 1
        assert fields["hw_editable_source"] == 1
        assert fields["mech_design_present"] == 0
        assert fields["mech_editable_source"] == 0
        assert fields["sw_fw_present"] == 1
        assert fields["sw_fw_type"] == "firmware"
        assert fields["sw_fw_doc_level"] == "basic"
        assert fields["testing_present"] == 0
        assert fields["testing_detail"] == "none"
        assert fields["cost_mentioned"] == 1
        assert fields["suppliers_referenced"] == 0
        assert fields["part_numbers_present"] == 1
        assert fields["maturity_stage"] == "production"
        assert fields["hw_license_name"] == "CERN-OHL-S"
        assert fields["sw_license_name"] == "MIT"
        assert fields.get("doc_license_name") is None

    def test_empty_parsed(self) -> None:
        """Empty dict returns empty fields (no crash)."""
        fields = extract_fields({})
        assert isinstance(fields, dict)


class TestBatchJsonlFormat:
    """Tests for batch JSONL preparation."""

    @pytest.fixture()
    def tmp_db(self, tmp_path: Path) -> Path:
        """Create temp DB with a project that has README + tree."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = open_connection(db_path)

        # Add license_normalized column
        cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
        if "license_normalized" not in cols:
            conn.execute("ALTER TABLE licenses ADD COLUMN license_normalized TEXT")

        cursor = conn.execute(
            "INSERT INTO projects (source, source_id, name, repo_url) "
            "VALUES (?, ?, ?, ?)",
            ("test", "batch_1", "Batch Test", "https://github.com/t/r"),
        )
        pid = cursor.lastrowid

        conn.execute(
            "INSERT INTO readme_contents "
            "(project_id, repo_url, content, size_bytes, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, "https://github.com/t/r", "# Test README", 13,
             "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO repo_file_trees "
            "(project_id, file_path, file_type, size_bytes) "
            "VALUES (?, ?, ?, ?)",
            (pid, "README.md", "blob", 13),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_prepare_creates_jsonl(self, tmp_db: Path, tmp_path: Path) -> None:
        """Prepare creates a valid JSONL file."""
        with patch(
            "osh_datasets.enrichment.llm_readme_eval._BATCH_DIR",
            tmp_path / "batch",
        ), patch(
            "osh_datasets.enrichment.llm_readme_eval._PROMPT_DIR",
            Path(__file__).resolve().parents[1] / "prompt_evaluation" / "test_8",
        ):
            output = prepare_batch(tmp_db, prompt_version="test_8")

            if output.exists():
                with open(output, "rb") as f:
                    lines = [line for line in f if line.strip()]
                assert len(lines) >= 1

                first = orjson.loads(lines[0])
                assert "key" in first
                assert first["key"].startswith("project_")
                assert "request" in first
                req = first["request"]
                assert "system_instruction" in req
                assert "contents" in req
                assert "generation_config" in req
                assert req["generation_config"]["temperature"] == 0


class TestIngestBatchResults:
    """Tests for batch result ingestion."""

    @pytest.fixture()
    def tmp_db(self, tmp_path: Path) -> Path:
        """Create temp DB with a project."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = open_connection(db_path)

        # Add license_normalized column
        cols = {r[1] for r in conn.execute("PRAGMA table_info(licenses)").fetchall()}
        if "license_normalized" not in cols:
            conn.execute("ALTER TABLE licenses ADD COLUMN license_normalized TEXT")

        conn.execute(
            "INSERT INTO projects (source, source_id, name) "
            "VALUES (?, ?, ?)",
            ("test", "ingest_1", "Ingest Test"),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_ingest_valid_result(self, tmp_db: Path, tmp_path: Path) -> None:
        """Valid batch result is ingested correctly."""
        # Get project ID
        conn = open_connection(tmp_db)
        pid = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()[0]
        conn.close()

        # Create mock batch output
        response_json = {
            "metadata": {"project_type": "hardware",
                         "structure_quality": "basic",
                         "documentation_location": "inline"},
            "license": {"present": True, "type": "explicit",
                        "name": "MIT"},
            "contributing": {"present": False, "level": 0},
            "bom": {"present": False, "completeness": "none",
                    "component_count": 0},
            "assembly": {"present": False, "detail_level": "none",
                         "step_count": 0},
            "design_files": {
                "hardware": {"present": False,
                             "has_editable_source": False},
                "mechanical": {"present": False,
                               "has_editable_source": False},
            },
            "software_firmware": {"present": False, "type": "none",
                                  "documentation_level": "none"},
            "testing": {"present": False, "detail_level": "none"},
            "cost_sourcing": {"estimated_cost_mentioned": False,
                              "suppliers_referenced": False,
                              "part_numbers_present": False},
            "project_maturity": {"stage": "unstated"},
            "specific_licenses": {
                "hardware": {"present": False, "name": None},
                "software": {"present": True, "name": "MIT"},
                "documentation": {"present": False, "name": None},
            },
        }
        raw_text = f"```json\n{orjson.dumps(response_json).decode()}\n```"

        batch_result = {
            "key": f"project_{pid}",
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"text": raw_text}],
                    },
                }],
            },
        }

        results_path = tmp_path / "results.jsonl"
        results_path.write_bytes(orjson.dumps(batch_result) + b"\n")

        count = ingest_batch_results(
            tmp_db,
            results_path=results_path,
            prompt_version="test_8",
        )
        assert count == 1

        # Verify DB record
        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT project_type, license_present, license_name, "
            "sw_license_name FROM llm_evaluations "
            "WHERE project_id = ?",
            (pid,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "hardware"
        assert row[1] == 1
        assert row[2] == "MIT"
        assert row[3] == "MIT"

    def test_skip_already_evaluated(self, tmp_db: Path, tmp_path: Path) -> None:
        """Projects with existing evaluations are correctly updated."""
        conn = open_connection(tmp_db)
        pid = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()[0]
        conn.close()

        response_json = {
            "metadata": {"project_type": "hardware"},
            "license": {"present": False, "type": "none", "name": None},
        }
        raw_text = f"```json\n{orjson.dumps(response_json).decode()}\n```"

        batch_result = {
            "key": f"project_{pid}",
            "response": {
                "candidates": [{
                    "content": {"parts": [{"text": raw_text}]},
                }],
            },
        }

        results_path = tmp_path / "results.jsonl"
        results_path.write_bytes(orjson.dumps(batch_result) + b"\n")

        # Ingest twice -- should upsert without error
        count1 = ingest_batch_results(
            tmp_db, results_path=results_path, prompt_version="test_8"
        )
        count2 = ingest_batch_results(
            tmp_db, results_path=results_path, prompt_version="test_8"
        )
        assert count1 == 1
        assert count2 == 1

        # Only one row should exist
        conn = open_connection(tmp_db)
        total = conn.execute(
            "SELECT COUNT(*) FROM llm_evaluations WHERE project_id = ?",
            (pid,),
        ).fetchone()[0]
        conn.close()
        assert total == 1


class TestRunRealtime:
    """Tests for realtime Gemini evaluation."""

    @pytest.fixture()
    def tmp_db(self, tmp_path: Path) -> Path:
        """Create temp DB with two projects that have README + tree."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = open_connection(db_path)

        cols = {
            r[1]
            for r in conn.execute(
                "PRAGMA table_info(licenses)"
            ).fetchall()
        }
        if "license_normalized" not in cols:
            conn.execute(
                "ALTER TABLE licenses "
                "ADD COLUMN license_normalized TEXT"
            )

        for idx in range(2):
            cursor = conn.execute(
                "INSERT INTO projects "
                "(source, source_id, name, repo_url) "
                "VALUES (?, ?, ?, ?)",
                (
                    "test",
                    f"rt_{idx}",
                    f"Realtime Test {idx}",
                    f"https://github.com/t/r{idx}",
                ),
            )
            pid = cursor.lastrowid
            conn.execute(
                "INSERT INTO readme_contents "
                "(project_id, repo_url, content, "
                "size_bytes, fetched_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    pid,
                    f"https://github.com/t/r{idx}",
                    f"# Test README {idx}\nSome content.",
                    30,
                    "2025-01-01T00:00:00Z",
                ),
            )
            conn.execute(
                "INSERT INTO repo_file_trees "
                "(project_id, file_path, file_type, "
                "size_bytes) VALUES (?, ?, ?, ?)",
                (pid, "README.md", "blob", 30),
            )

        conn.commit()
        conn.close()
        return db_path

    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._call_gemini_realtime"
    )
    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._load_prompt_template"
    )
    def test_success_stores_evaluation(
        self,
        mock_prompt: object,
        mock_call: object,
        tmp_db: Path,
    ) -> None:
        """Successful API call stores evaluation in DB."""
        mock_prompt.return_value = (  # type: ignore[union-attr]
            "system",
            "{readme_content} {directory_structure}",
        )

        response_json = {
            "metadata": {"project_type": "hardware"},
            "license": {
                "present": True,
                "type": "explicit",
                "name": "MIT",
            },
        }
        raw = orjson.dumps(response_json).decode()
        mock_call.return_value = (raw, 100, 50)  # type: ignore[union-attr]

        run_realtime(
            db_path=tmp_db,
            prompt_version="test_rt",
            model_id="test-model",
            limit=1,
            max_workers=1,
        )

        conn = open_connection(tmp_db)
        row = conn.execute(
            "SELECT model_id, project_type "
            "FROM llm_evaluations LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "test-model"
        assert row[1] == "hardware"

    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._call_gemini_realtime"
    )
    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._load_prompt_template"
    )
    def test_failure_continues(
        self,
        mock_prompt: object,
        mock_call: object,
        tmp_db: Path,
    ) -> None:
        """API failure logs warning and does not crash."""
        mock_prompt.return_value = (  # type: ignore[union-attr]
            "system",
            "{readme_content} {directory_structure}",
        )
        mock_call.return_value = None  # type: ignore[union-attr]

        run_realtime(
            db_path=tmp_db,
            prompt_version="test_rt",
            model_id="test-model",
            limit=1,
            max_workers=1,
        )

        conn = open_connection(tmp_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM llm_evaluations"
        ).fetchone()[0]
        conn.close()
        assert count == 0

    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._call_gemini_realtime"
    )
    @patch(
        "osh_datasets.enrichment.llm_readme_eval"
        "._load_prompt_template"
    )
    def test_skip_already_evaluated(
        self,
        mock_prompt: object,
        mock_call: object,
        tmp_db: Path,
    ) -> None:
        """Projects with existing evaluations are skipped."""
        mock_prompt.return_value = (  # type: ignore[union-attr]
            "system",
            "{readme_content} {directory_structure}",
        )

        response_json = {
            "metadata": {"project_type": "hardware"},
            "license": {"present": False, "type": "none"},
        }
        raw = orjson.dumps(response_json).decode()
        mock_call.return_value = (raw, 100, 50)  # type: ignore[union-attr]

        # First run evaluates both projects
        run_realtime(
            db_path=tmp_db,
            prompt_version="test_rt",
            model_id="test-model",
            max_workers=1,
        )

        conn = open_connection(tmp_db)
        count_after_first = conn.execute(
            "SELECT COUNT(*) FROM llm_evaluations"
        ).fetchone()[0]
        conn.close()

        # Reset call count, run again
        mock_call.reset_mock()  # type: ignore[union-attr]
        run_realtime(
            db_path=tmp_db,
            prompt_version="test_rt",
            model_id="test-model",
            max_workers=1,
        )

        # Should not have called the API again
        mock_call.assert_not_called()  # type: ignore[union-attr]

        conn = open_connection(tmp_db)
        count_after_second = conn.execute(
            "SELECT COUNT(*) FROM llm_evaluations"
        ).fetchone()[0]
        conn.close()
        assert count_after_first == count_after_second == 2


class TestInputTruncation:
    """Tests for input size guard rails."""

    def test_readme_truncation_at_limit(self) -> None:
        """README at exactly the limit is not truncated."""
        template = "{readme_content}"
        readme = "x" * _MAX_README_CHARS
        result = _build_user_prompt(template, readme, "")
        assert "[README TRUNCATED]" not in result

    def test_readme_truncation_over_limit(self) -> None:
        """README over the limit is truncated."""
        template = "{readme_content}"
        readme = "x" * (_MAX_README_CHARS + 1)
        result = _build_user_prompt(template, readme, "")
        assert "[README TRUNCATED]" in result

    def test_tree_entry_truncation(self) -> None:
        """Tree with more than _MAX_TREE_ENTRIES is capped."""
        entries = [
            (f"file_{i}.txt", "blob", 10) for i in range(_MAX_TREE_ENTRIES + 50)
        ]
        result = format_directory_tree(entries)
        line_count = len([
            line for line in result.split("\n")
            if line.strip() and not line.startswith("[")
        ])
        assert line_count <= _MAX_TREE_ENTRIES
