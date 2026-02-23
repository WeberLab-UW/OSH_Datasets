"""Track 2: LLM-based README evaluation via Gemini Batch API.

Three-phase workflow for evaluating open-source hardware documentation
quality using Google Gemini 3 Flash in batch mode:

    1. **Prepare**: Build JSONL batch input from README + file tree data.
    2. **Submit**: Upload JSONL and submit to Gemini Batch API.
    3. **Ingest**: Download results and store in database.

Uses the few-shot prompt from ``prompt_evaluation/test_8/revised_long_prompt.md``
which evaluates 12 documentation dimensions with calibrated scoring.

Usage::

    # Phase 1: Prepare batch input
    uv run python -m osh_datasets.enrichment.llm_readme_eval prepare

    # Phase 2: Submit to Gemini Batch API
    uv run python -m osh_datasets.enrichment.llm_readme_eval submit

    # Phase 3: Ingest results after batch completes
    uv run python -m osh_datasets.enrichment.llm_readme_eval ingest
"""

import argparse
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import orjson

from osh_datasets.config import DB_PATH, get_logger, require_env
from osh_datasets.db import open_connection, upsert_llm_evaluation

logger = get_logger(__name__)

_MODEL_ID = "gemini-3-flash-preview"
_MAX_README_CHARS = 10_000
_MAX_TREE_ENTRIES = 500
_MAX_TREE_CHARS = 12_000
_MAX_OUTPUT_TOKENS = 8192

_PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompt_evaluation" / "test_8"
_BATCH_DIR = Path(__file__).resolve().parents[3] / "data" / "batch"


def _load_prompt_template() -> tuple[str, str]:
    """Load system and user prompt templates from test_8.

    Returns:
        Tuple of ``(system_prompt, user_prompt_template)``.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    prompt_path = _PROMPT_DIR / "revised_long_prompt.md"
    text = prompt_path.read_text(encoding="utf-8")

    # Extract SYSTEM_PROMPT between first pair of triple-quotes
    sys_match = re.search(
        r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""',
        text,
        re.DOTALL,
    )
    if not sys_match:
        raise ValueError("Cannot find SYSTEM_PROMPT in prompt file")
    system = sys_match.group(1).strip()

    # Extract USER_PROMPT_TEMPLATE between second pair of triple-quotes
    user_match = re.search(
        r'USER_PROMPT_TEMPLATE\s*=\s*"""(.*?)"""',
        text,
        re.DOTALL,
    )
    if not user_match:
        raise ValueError("Cannot find USER_PROMPT_TEMPLATE in prompt file")
    user = user_match.group(1).strip()

    return system, user


def format_directory_tree(
    entries: list[tuple[str, str, int | None]],
) -> str:
    """Render file tree entries as indented text for prompt insertion.

    Args:
        entries: List of ``(path, type, size)`` tuples from
            ``repo_file_trees``.

    Returns:
        Formatted directory tree string.
    """
    if not entries:
        return "(empty repository)"

    # Sort by path for consistent output
    sorted_entries = sorted(entries, key=lambda e: e[0])

    # Cap at max entries
    if len(sorted_entries) > _MAX_TREE_ENTRIES:
        sorted_entries = sorted_entries[:_MAX_TREE_ENTRIES]

    lines: list[str] = []
    for path, ftype, _size in sorted_entries:
        if ftype == "tree":
            lines.append(f"{path}/")
        else:
            lines.append(path)

    tree_text = "\n".join(lines)

    # Cap at max chars
    if len(tree_text) > _MAX_TREE_CHARS:
        tree_text = tree_text[:_MAX_TREE_CHARS] + "\n\n[TREE TRUNCATED]"

    return tree_text


def _build_user_prompt(
    template: str,
    readme_content: str,
    directory_tree: str,
) -> str:
    """Fill user prompt template with project data.

    Applies input truncation guards before insertion to ensure
    the JSON schema at the end of the prompt is never truncated.

    Args:
        template: User prompt template with placeholders.
        readme_content: Raw README markdown text.
        directory_tree: Formatted directory tree string.

    Returns:
        Completed user prompt string.
    """
    if len(readme_content) > _MAX_README_CHARS:
        readme_insert = (
            readme_content[:_MAX_README_CHARS]
            + "\n\n[README TRUNCATED]"
        )
    else:
        readme_insert = readme_content

    # Replace placeholders first, then unescape the doubled
    # braces used in the JSON schema example ({{ -> {, }} -> }).
    filled = template.replace(
        "{directory_structure}", directory_tree
    ).replace(
        "{readme_content}", readme_insert
    )
    return filled.replace("{{", "{").replace("}}", "}")


def parse_response(raw: str) -> dict[str, object] | None:
    """Extract JSON block from LLM response text.

    Args:
        raw: Raw LLM response text, possibly with markdown fences.

    Returns:
        Parsed dict, or None if JSON extraction fails.
    """
    # Try to extract from markdown code fence
    json_match = re.search(r"```json\s*(.*?)```", raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try to find raw JSON object
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            json_str = brace_match.group(0)
        else:
            logger.warning("No JSON found in response")
            return None

    try:
        parsed = orjson.loads(json_str.encode("utf-8"))
        if not isinstance(parsed, dict):
            logger.warning("Response JSON is not a dict")
            return None
        return parsed
    except orjson.JSONDecodeError as exc:
        logger.warning("JSON parse error: %s", exc)
        return None


def extract_fields(
    parsed: dict[str, object],
) -> dict[str, int | str | None]:
    """Flatten nested LLM JSON response into DB column values.

    Args:
        parsed: Parsed JSON dict from the LLM response.

    Returns:
        Dict with keys matching ``llm_evaluations`` column names.
    """
    fields: dict[str, int | str | None] = {}

    # Metadata
    meta = parsed.get("metadata", {})
    if isinstance(meta, dict):
        fields["project_type"] = meta.get("project_type")
        fields["structure_quality"] = meta.get("structure_quality")
        fields["doc_location"] = meta.get("documentation_location")

    # License
    lic = parsed.get("license", {})
    if isinstance(lic, dict):
        fields["license_present"] = int(bool(lic.get("present")))
        fields["license_type"] = lic.get("type")
        fields["license_name"] = lic.get("name")

    # Contributing
    contrib = parsed.get("contributing", {})
    if isinstance(contrib, dict):
        fields["contributing_present"] = int(
            bool(contrib.get("present"))
        )
        fields["contributing_level"] = contrib.get("level")

    # BOM
    bom = parsed.get("bom", {})
    if isinstance(bom, dict):
        fields["bom_present"] = int(bool(bom.get("present")))
        fields["bom_completeness"] = bom.get("completeness")
        count = bom.get("component_count", 0)
        fields["bom_component_count"] = int(count) if count else 0

    # Assembly
    asm = parsed.get("assembly", {})
    if isinstance(asm, dict):
        fields["assembly_present"] = int(bool(asm.get("present")))
        fields["assembly_detail"] = asm.get("detail_level")
        steps = asm.get("step_count", 0)
        fields["assembly_step_count"] = int(steps) if steps else 0

    # Design files
    design = parsed.get("design_files", {})
    if isinstance(design, dict):
        hw = design.get("hardware", {})
        if isinstance(hw, dict):
            fields["hw_design_present"] = int(
                bool(hw.get("present"))
            )
            fields["hw_editable_source"] = int(
                bool(hw.get("has_editable_source"))
            )
        mech = design.get("mechanical", {})
        if isinstance(mech, dict):
            fields["mech_design_present"] = int(
                bool(mech.get("present"))
            )
            fields["mech_editable_source"] = int(
                bool(mech.get("has_editable_source"))
            )

    # Software/firmware
    sw = parsed.get("software_firmware", {})
    if isinstance(sw, dict):
        fields["sw_fw_present"] = int(bool(sw.get("present")))
        fields["sw_fw_type"] = sw.get("type")
        fields["sw_fw_doc_level"] = sw.get("documentation_level")

    # Testing
    test = parsed.get("testing", {})
    if isinstance(test, dict):
        fields["testing_present"] = int(bool(test.get("present")))
        fields["testing_detail"] = test.get("detail_level")

    # Cost/sourcing
    cost = parsed.get("cost_sourcing", {})
    if isinstance(cost, dict):
        fields["cost_mentioned"] = int(
            bool(cost.get("estimated_cost_mentioned"))
        )
        fields["suppliers_referenced"] = int(
            bool(cost.get("suppliers_referenced"))
        )
        fields["part_numbers_present"] = int(
            bool(cost.get("part_numbers_present"))
        )

    # Maturity
    mat = parsed.get("project_maturity", {})
    if isinstance(mat, dict):
        fields["maturity_stage"] = mat.get("stage")

    # Domain-specific licenses
    spec = parsed.get("specific_licenses", {})
    if isinstance(spec, dict):
        hw_lic = spec.get("hardware", {})
        if isinstance(hw_lic, dict) and hw_lic.get("present"):
            fields["hw_license_name"] = hw_lic.get("name")
        sw_lic = spec.get("software", {})
        if isinstance(sw_lic, dict) and sw_lic.get("present"):
            fields["sw_license_name"] = sw_lic.get("name")
        doc_lic = spec.get("documentation", {})
        if isinstance(doc_lic, dict) and doc_lic.get("present"):
            fields["doc_license_name"] = doc_lic.get("name")

    return fields


# ── Phase 1: Prepare ─────────────────────────────────────────────


def prepare_batch(
    db_path: Path = DB_PATH,
    prompt_version: str = "test_8",
) -> Path:
    """Build JSONL batch input from README + file tree data.

    Queries projects that have README content and file tree data
    but no existing LLM evaluation for the current prompt version.

    Args:
        db_path: Path to the SQLite database file.
        prompt_version: Prompt version identifier.

    Returns:
        Path to the generated JSONL batch file.
    """
    system_prompt, user_template = _load_prompt_template()
    conn = open_connection(db_path)

    candidates = conn.execute(
        """\
        SELECT rc.project_id, rc.content
        FROM readme_contents rc
        WHERE rc.content IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM repo_file_trees rft
              WHERE rft.project_id = rc.project_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM llm_evaluations le
              WHERE le.project_id = rc.project_id
                AND le.prompt_version = ?
          )
        ORDER BY rc.project_id
        """,
        (prompt_version,),
    ).fetchall()

    if not candidates:
        logger.info("No candidates for batch preparation")
        conn.close()
        return _BATCH_DIR / "gemini_batch_input.jsonl"

    _BATCH_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _BATCH_DIR / "gemini_batch_input.jsonl"

    count = 0
    with open(output_path, "wb") as f:
        for row in candidates:
            project_id = row[0]
            readme_content = row[1]

            tree_rows = conn.execute(
                """\
                SELECT file_path, file_type, size_bytes
                FROM repo_file_trees
                WHERE project_id = ?
                ORDER BY file_path
                """,
                (project_id,),
            ).fetchall()

            tree_entries = [
                (r[0], r[1], r[2]) for r in tree_rows
            ]
            tree_text = format_directory_tree(tree_entries)
            user_prompt = _build_user_prompt(
                user_template, readme_content, tree_text
            )

            request = {
                "key": f"project_{project_id}",
                "request": {
                    "system_instruction": {
                        "parts": [{"text": system_prompt}],
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": user_prompt}],
                        },
                    ],
                    "generation_config": {
                        "temperature": 0,
                        "max_output_tokens": _MAX_OUTPUT_TOKENS,
                    },
                },
            }
            f.write(orjson.dumps(request) + b"\n")
            count += 1

    conn.close()
    logger.info(
        "Prepared %d requests in %s", count, output_path
    )
    return output_path


# ── Phase 2: Submit ──────────────────────────────────────────────


def submit_batch(
    input_path: Path | None = None,
) -> str:
    """Upload JSONL and submit to Gemini Batch API.

    Args:
        input_path: Path to the JSONL batch file. Defaults to
            standard location.

    Returns:
        Batch job name/ID for polling.

    Raises:
        ImportError: If ``google-genai`` is not installed.
        FileNotFoundError: If input file does not exist.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "google-genai package required. Install with: "
            "uv pip install 'google-genai'"
        ) from exc

    api_key = require_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    if input_path is None:
        input_path = _BATCH_DIR / "gemini_batch_input.jsonl"
    if not input_path.exists():
        raise FileNotFoundError(
            f"Batch input file not found: {input_path}"
        )

    logger.info("Uploading %s to Gemini Files API", input_path)
    uploaded_file = client.files.upload(
        file=str(input_path),
        config=types.UploadFileConfig(
            display_name="osh-readme-eval-batch",
            mime_type="jsonl",
        ),
    )

    file_resource = uploaded_file.name
    if not file_resource:
        raise RuntimeError("File upload returned no resource name")

    logger.info("Submitting batch job for model %s", _MODEL_ID)
    batch_job = client.batches.create(
        model=_MODEL_ID,
        src=file_resource,
        config={"display_name": "osh-readme-eval"},
    )

    job_name = batch_job.name
    if not job_name:
        raise RuntimeError("Batch job returned no job name")
    logger.info("Batch job submitted: %s", job_name)

    # Save job name for later polling
    job_file = _BATCH_DIR / "batch_job_name.txt"
    job_file.write_text(job_name)

    return job_name


def poll_batch(
    job_name: str | None = None,
    poll_interval: int = 60,
) -> Path | None:
    """Poll batch job until complete, then download results.

    Args:
        job_name: Batch job name/ID. If None, reads from saved file.
        poll_interval: Seconds between status checks.

    Returns:
        Path to downloaded results JSONL, or None if job failed.
    """
    try:
        from google import genai
    except ImportError as exc:
        raise ImportError(
            "google-genai package required. Install with: "
            "uv pip install 'google-genai'"
        ) from exc

    api_key = require_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    if job_name is None:
        job_file = _BATCH_DIR / "batch_job_name.txt"
        if not job_file.exists():
            logger.error("No batch job name found")
            return None
        job_name = job_file.read_text().strip()

    completed_states = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }

    logger.info("Polling batch job: %s", job_name)
    state = ""
    while True:
        batch_job = client.batches.get(name=job_name)
        if batch_job.state is not None:
            state = batch_job.state.name
        logger.info("Job state: %s", state)

        if state in completed_states:
            break
        time.sleep(poll_interval)

    if state != "JOB_STATE_SUCCEEDED":
        logger.error("Batch job ended with state: %s", state)
        return None

    # Download results
    if batch_job.dest is None or not batch_job.dest.file_name:
        logger.error("No output file in completed batch job")
        return None
    result_file_name: str = batch_job.dest.file_name
    logger.info("Downloading results from %s", result_file_name)
    content = client.files.download(file=result_file_name)

    output_path = _BATCH_DIR / "gemini_batch_output.jsonl"
    output_path.write_bytes(content)
    logger.info("Results saved to %s", output_path)

    return output_path


# ── Phase 3: Ingest ──────────────────────────────────────────────


def ingest_batch_results(
    db_path: Path = DB_PATH,
    results_path: Path | None = None,
    prompt_version: str = "test_8",
) -> int:
    """Parse batch results and upsert to database.

    Args:
        db_path: Path to the SQLite database file.
        results_path: Path to the results JSONL file. Defaults to
            standard location.
        prompt_version: Prompt version identifier.

    Returns:
        Number of evaluations successfully ingested.
    """
    if results_path is None:
        results_path = _BATCH_DIR / "gemini_batch_output.jsonl"
    if not results_path.exists():
        logger.error("Results file not found: %s", results_path)
        return 0

    conn = open_connection(db_path)
    now = datetime.now(UTC).isoformat()
    ingested = 0

    with open(results_path, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                result = orjson.loads(line)
            except orjson.JSONDecodeError:
                logger.warning("Skipping malformed JSONL line")
                continue

            if not isinstance(result, dict):
                continue

            # Extract project ID from key
            key = result.get("key", "")
            if not isinstance(key, str) or not key.startswith("project_"):
                logger.warning("Unexpected key format: %s", key)
                continue

            try:
                project_id = int(key.replace("project_", ""))
            except ValueError:
                logger.warning("Cannot parse project ID from key: %s", key)
                continue

            # Check for batch-level error (no response)
            if "error" in result:
                logger.warning(
                    "Batch error for project %d: %s",
                    project_id,
                    result["error"],
                )
                continue

            # Extract response text
            response = result.get("response", {})
            if not isinstance(response, dict):
                logger.warning(
                    "Missing response for project %d", project_id
                )
                continue

            # Navigate Gemini response structure
            candidates = response.get("candidates", [])
            if not candidates or not isinstance(candidates, list):
                logger.warning(
                    "No candidates for project %d", project_id
                )
                continue

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                logger.warning(
                    "No content parts for project %d", project_id
                )
                continue

            raw_text = parts[0].get("text", "")
            parsed = parse_response(raw_text)
            extracted = extract_fields(parsed) if parsed else None

            upsert_llm_evaluation(
                conn,
                project_id,
                prompt_version=prompt_version,
                model_id=_MODEL_ID,
                raw_response=raw_text,
                evaluated_at=now,
                extracted=extracted,
            )
            ingested += 1

    conn.commit()
    conn.close()
    logger.info("Ingested %d evaluations", ingested)
    return ingested


# ── CLI ──────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point with subcommands: prepare, submit, ingest."""
    parser = argparse.ArgumentParser(
        description="LLM-based README evaluation via Gemini Batch API"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="Build JSONL batch input")
    prep.add_argument(
        "--prompt-version",
        default="test_8",
        help="Prompt version (default: test_8)",
    )

    sub.add_parser("submit", help="Submit batch job to Gemini")

    poll = sub.add_parser("poll", help="Poll batch job and download results")
    poll.add_argument("--job-name", default=None, help="Batch job name")
    poll.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Poll interval in seconds (default: 60)",
    )

    ing = sub.add_parser("ingest", help="Ingest batch results to DB")
    ing.add_argument(
        "--prompt-version",
        default="test_8",
        help="Prompt version (default: test_8)",
    )
    ing.add_argument(
        "--results-path",
        default=None,
        help="Path to results JSONL file",
    )

    args = parser.parse_args()

    if args.command == "prepare":
        path = prepare_batch(prompt_version=args.prompt_version)
        print(f"Batch input written to: {path}")

    elif args.command == "submit":
        job_name = submit_batch()
        print(f"Batch job submitted: {job_name}")

    elif args.command == "poll":
        result_path = poll_batch(
            job_name=args.job_name,
            poll_interval=args.interval,
        )
        if result_path:
            print(f"Results downloaded to: {result_path}")
        else:
            print("Batch job did not succeed.")

    elif args.command == "ingest":
        results_path = (
            Path(args.results_path) if args.results_path else None
        )
        count = ingest_batch_results(
            prompt_version=args.prompt_version,
            results_path=results_path,
        )
        print(f"Ingested {count} evaluations.")


if __name__ == "__main__":
    main()
