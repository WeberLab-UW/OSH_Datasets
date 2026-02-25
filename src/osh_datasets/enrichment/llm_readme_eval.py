"""Track 2: LLM-based README evaluation via Gemini API.

Supports two execution modes:

**Batch mode** (prepare -> submit -> ingest):
    For large runs using the Gemini Batch API. Prepares JSONL,
    submits in chunks, and ingests results.

**Realtime mode**:
    Synchronous per-project API calls. Useful when the Batch API
    is unavailable or for incremental processing.

Uses the few-shot prompt from ``prompt_evaluation/test_8/revised_long_prompt.md``
which evaluates 12 documentation dimensions with calibrated scoring.

Usage::

    # Realtime: evaluate all pending projects
    uv run python -m osh_datasets.enrichment.llm_readme_eval realtime

    # Realtime: evaluate 100 projects, 50 concurrent threads
    uv run python -m osh_datasets.enrichment.llm_readme_eval realtime \\
        --limit 100 --model gemini-2.5-flash-lite --workers 50

    # Batch Phase 1: Prepare batch input
    uv run python -m osh_datasets.enrichment.llm_readme_eval prepare

    # Batch Phase 2: Submit chunks (run repeatedly, non-blocking)
    uv run python -m osh_datasets.enrichment.llm_readme_eval submit

    # Batch Phase 3: Ingest results into database
    uv run python -m osh_datasets.enrichment.llm_readme_eval ingest
"""

import argparse
import concurrent.futures
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import orjson
from tqdm import tqdm

from osh_datasets.config import DB_PATH, get_logger, require_env
from osh_datasets.db import open_connection, upsert_llm_evaluation

logger = get_logger(__name__)

_MODEL_ID = "gemini-3-flash-preview"
_DEFAULT_REALTIME_MODEL = "gemini-2.5-flash-lite"
_MAX_README_CHARS = 10_000
_MAX_TREE_ENTRIES = 500
_MAX_TREE_CHARS = 12_000
_MAX_OUTPUT_TOKENS = 8192
_COMMIT_INTERVAL = 50
_API_TIMEOUT_SECONDS = 60
_DEFAULT_WORKERS = 20
_MAX_RETRIES = 3
_INPUT_TOKENS_PER_MINUTE = 3_500_000  # Under 4M paid tier limit
_TOKEN_BUDGET = 2_800_000  # Under tier-1 3M enqueued-token limit
_CHARS_PER_TOKEN = 4

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


def _fix_invalid_escapes(json_str: str) -> str:
    r"""Escape backslashes that precede non-JSON-escape characters.

    LLMs sometimes emit invalid JSON escapes like ``\*`` (from
    markdown bold) or ``\c`` (from pasted shell commands). Valid
    JSON escapes are: ``\" \\ \/ \b \f \n \r \t \uXXXX``.
    This replaces any ``\X`` where X is not a valid JSON escape
    leader with ``\\X``.

    Args:
        json_str: Raw JSON string that may contain invalid escapes.

    Returns:
        Sanitized JSON string safe for strict parsers.
    """
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", json_str)


def parse_response(raw: str) -> dict[str, object] | None:
    """Extract the outermost JSON object from LLM response text.

    Uses brace-depth counting with string-literal awareness to
    correctly handle JSON containing triple backticks in string
    values (e.g., evidence fields quoting README code blocks).
    Applies escape sanitization to tolerate LLM outputs with
    invalid JSON escape sequences.

    Args:
        raw: Raw LLM response text, possibly with markdown fences.

    Returns:
        Parsed dict, or None if JSON extraction fails.
    """
    start = raw.find("{")
    if start == -1:
        logger.warning("No JSON found in response")
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(raw)):
        ch = raw[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_str = raw[start : i + 1]
                try:
                    parsed = orjson.loads(
                        json_str.encode("utf-8")
                    )
                except orjson.JSONDecodeError:
                    json_str = _fix_invalid_escapes(json_str)
                    try:
                        parsed = orjson.loads(
                            json_str.encode("utf-8")
                        )
                    except orjson.JSONDecodeError as exc:
                        logger.warning(
                            "JSON parse error: %s", exc
                        )
                        return None
                if not isinstance(parsed, dict):
                    logger.warning("Response JSON is not a dict")
                    return None
                return parsed

    logger.warning("Unterminated JSON object in response")
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


# ── Realtime execution ────────────────────────────────────────────


class _TokenBucket:
    """Thread-safe token-bucket rate limiter.

    Limits throughput to ``tokens_per_second`` on average, with
    a burst capacity equal to one second of tokens.

    Args:
        tokens_per_second: Sustained refill rate.
    """

    def __init__(self, tokens_per_second: float) -> None:
        self._rate = tokens_per_second
        self._capacity = tokens_per_second  # 1-second burst
        self._tokens = tokens_per_second
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, count: int) -> None:
        """Block until ``count`` tokens are available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(
                    self._capacity,
                    self._tokens + elapsed * self._rate,
                )
                self._last = now
                if self._tokens >= count:
                    self._tokens -= count
                    return
            time.sleep(0.1)


def _call_gemini_realtime(
    client: object,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    rate_limiter: _TokenBucket | None = None,
    est_input_tokens: int = 0,
) -> tuple[str, int, int] | None:
    """Call Gemini API with timeout and retry on rate-limit errors.

    Retries up to ``_MAX_RETRIES`` times on 429 errors with
    exponential backoff. Uses ``rate_limiter`` to throttle requests
    proactively before hitting the API.

    Args:
        client: Initialized ``genai.Client`` instance.
        model_id: Gemini model identifier.
        system_prompt: System instruction text.
        user_prompt: Filled user prompt text.
        rate_limiter: Optional token-bucket for rate limiting.
        est_input_tokens: Estimated input tokens for rate limiting.

    Returns:
        Tuple of ``(response_text, input_tokens, output_tokens)``
        or ``None`` if the call fails after all retries.
    """
    try:
        from google.genai import types as genai_types
    except ImportError as exc:
        raise ImportError(
            "google-genai package required. Install with: "
            "uv pip install 'google-genai'"
        ) from exc

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        automatic_function_calling=(
            genai_types.AutomaticFunctionCallingConfig(
                disable=True,
            )
        ),
    )

    for attempt in range(_MAX_RETRIES):
        if rate_limiter and est_input_tokens > 0:
            rate_limiter.acquire(est_input_tokens)

        def _do_call() -> tuple[str, int, int]:
            resp = client.models.generate_content(  # type: ignore[attr-defined]
                model=model_id,
                contents=user_prompt,
                config=config,
            )
            text = resp.text or ""
            usage = resp.usage_metadata
            in_tok = (
                usage.prompt_token_count if usage else 0
            )
            out_tok = (
                usage.candidates_token_count if usage else 0
            )
            return text, in_tok, out_tok

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
        ) as pool:
            future = pool.submit(_do_call)
            try:
                return future.result(
                    timeout=_API_TIMEOUT_SECONDS,
                )
            except concurrent.futures.TimeoutError:
                logger.error(
                    "Gemini API timed out after %ds",
                    _API_TIMEOUT_SECONDS,
                )
                return None
            except Exception as exc:
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Rate limited (attempt %d/%d), "
                        "retrying in %ds",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    "Gemini API call failed: %s", exc,
                )
                return None

    logger.error("Gemini API exhausted %d retries", _MAX_RETRIES)
    return None


def run_realtime(
    db_path: Path = DB_PATH,
    prompt_version: str = "test_8",
    model_id: str = _DEFAULT_REALTIME_MODEL,
    limit: int = 0,
    max_workers: int = _DEFAULT_WORKERS,
) -> None:
    """Evaluate projects via concurrent real-time Gemini API calls.

    Pre-fetches all candidate data (README + file tree), builds
    prompts, then fires up to ``max_workers`` concurrent API calls.
    DB writes happen on the main thread as futures complete.

    Args:
        db_path: Path to the SQLite database file.
        prompt_version: Prompt version identifier.
        model_id: Gemini model identifier.
        limit: Maximum projects to process (0 = all).
        max_workers: Concurrent API call threads.

    Raises:
        ImportError: If ``google-genai`` is not installed.
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
    system_prompt, user_template = _load_prompt_template()

    conn = open_connection(db_path)
    try:
        query = """\
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
        """
        params: tuple[str, ...] | tuple[str, int] = (
            prompt_version,
        )
        if limit > 0:
            query += "\n            LIMIT ?"
            params = (prompt_version, limit)
        candidates = conn.execute(query, params).fetchall()

        if not candidates:
            logger.info("No candidates for realtime evaluation")
            return

        total = len(candidates)
        logger.info(
            "Starting realtime evaluation: %d projects, "
            "model=%s, prompt=%s, workers=%d",
            total,
            model_id,
            prompt_version,
            max_workers,
        )

        # Pre-build all prompts (I/O from DB, CPU for formatting)
        work_items: list[tuple[int, str]] = []
        for row in tqdm(
            candidates,
            desc="Building prompts",
            unit="project",
        ):
            project_id: int = row[0]
            readme_content: str = row[1]
            tree_rows = conn.execute(
                """\
                SELECT file_path, file_type, size_bytes
                FROM repo_file_trees
                WHERE project_id = ?
                ORDER BY file_path
                """,
                (project_id,),
            ).fetchall()
            tree_entries: list[tuple[str, str, int | None]] = [
                (r[0], r[1], r[2]) for r in tree_rows
            ]
            tree_text = format_directory_tree(tree_entries)
            user_prompt = _build_user_prompt(
                user_template, readme_content, tree_text,
            )
            work_items.append((project_id, user_prompt))

        success_count = 0
        fail_count = 0
        parse_fail_count = 0
        total_input_tokens = 0
        total_output_tokens = 0
        now = datetime.now(UTC).isoformat()
        writes_since_commit = 0

        # Rate limiter: 3.5M tokens/min = ~58k tokens/sec
        bucket = _TokenBucket(
            _INPUT_TOKENS_PER_MINUTE / 60.0,
        )

        # Fire concurrent API calls, write results on main thread
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
        ) as pool:
            future_to_pid: dict[
                concurrent.futures.Future[
                    tuple[str, int, int] | None
                ],
                int,
            ] = {
                pool.submit(
                    _call_gemini_realtime,
                    client,
                    model_id,
                    system_prompt,
                    prompt,
                    bucket,
                    len(prompt) // _CHARS_PER_TOKEN,
                ): pid
                for pid, prompt in work_items
            }

            progress = tqdm(
                concurrent.futures.as_completed(future_to_pid),
                total=total,
                desc="Evaluating (0 ok, 0 fail)",
                unit="project",
            )
            for future in progress:
                pid = future_to_pid[future]
                result = future.result()

                if result is None:
                    fail_count += 1
                    logger.warning(
                        "API failed: project_id=%d", pid,
                    )
                    progress.set_description(
                        f"Evaluating ({success_count} ok, "
                        f"{fail_count} fail)"
                    )
                    continue

                raw_text, in_tok, out_tok = result
                total_input_tokens += in_tok
                total_output_tokens += out_tok

                parsed = parse_response(raw_text)
                if parsed is None:
                    parse_fail_count += 1
                    logger.warning(
                        "JSON parse failed: project_id=%d",
                        pid,
                    )
                    progress.set_description(
                        f"Evaluating ({success_count} ok, "
                        f"{fail_count} fail)"
                    )
                    continue

                extracted = extract_fields(parsed)
                upsert_llm_evaluation(
                    conn,
                    pid,
                    prompt_version=prompt_version,
                    model_id=model_id,
                    raw_response=raw_text,
                    evaluated_at=now,
                    extracted=extracted,
                )
                success_count += 1
                writes_since_commit += 1

                progress.set_description(
                    f"Evaluating ({success_count} ok, "
                    f"{fail_count} fail)"
                )

                if writes_since_commit >= _COMMIT_INTERVAL:
                    conn.commit()
                    writes_since_commit = 0

        conn.commit()
    finally:
        conn.close()

    print(
        f"\n--- Realtime Evaluation Complete ---\n"
        f"Total:       {total}\n"
        f"Success:     {success_count}\n"
        f"API failed:  {fail_count}\n"
        f"Parse failed:{parse_fail_count}\n"
        f"Tokens:      {total_input_tokens:,} in / "
        f"{total_output_tokens:,} out"
    )


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


# ── Phase 2: Submit (non-blocking, chunked) ─────────────────────

_STATE_FILE = _BATCH_DIR / "batch_state.json"


def _estimate_request_tokens(line: bytes) -> int:
    """Estimate input token count for one JSONL request line.

    Args:
        line: Raw JSONL line bytes.

    Returns:
        Estimated token count (chars / 4).
    """
    obj = orjson.loads(line)
    req = obj.get("request", {})
    sys_parts = req.get("system_instruction", {}).get("parts") or [{}]
    contents = req.get("contents") or [{}]
    user_parts = contents[0].get("parts") or [{}]
    sys_text = sys_parts[0].get("text", "") if sys_parts else ""
    user_text = user_parts[0].get("text", "") if user_parts else ""
    return (len(sys_text) + len(user_text)) // _CHARS_PER_TOKEN


def _split_jsonl(input_path: Path) -> list[Path]:
    """Split batch JSONL into chunks within the enqueued token budget.

    Only writes chunk files that don't already exist.

    Args:
        input_path: Path to the full batch JSONL file.

    Returns:
        Ordered list of chunk file paths.
    """
    chunks: list[Path] = []
    buf: list[bytes] = []
    buf_tokens = 0
    idx = 0

    with open(input_path, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            tokens = _estimate_request_tokens(raw)
            if buf_tokens + tokens > _TOKEN_BUDGET and buf:
                chunk_path = _BATCH_DIR / f"batch_chunk_{idx:03d}.jsonl"
                if not chunk_path.exists():
                    chunk_path.write_bytes(b"\n".join(buf) + b"\n")
                chunks.append(chunk_path)
                idx += 1
                buf = []
                buf_tokens = 0
            buf.append(raw)
            buf_tokens += tokens

    if buf:
        chunk_path = _BATCH_DIR / f"batch_chunk_{idx:03d}.jsonl"
        if not chunk_path.exists():
            chunk_path.write_bytes(b"\n".join(buf) + b"\n")
        chunks.append(chunk_path)

    logger.info("Split into %d chunks", len(chunks))
    return chunks


_COMPLETED_STATES = frozenset({
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
})


def _load_state() -> dict[str, object]:
    """Load batch processing state from disk.

    Returns:
        State dict with ``chunk_idx``, ``job_name``, and
        ``total_chunks`` keys, or empty dict if no state exists.
    """
    if _STATE_FILE.exists():
        return orjson.loads(_STATE_FILE.read_bytes())  # type: ignore[no-any-return]
    return {}


def _save_state(state: dict[str, object]) -> None:
    """Persist batch processing state to disk.

    Args:
        state: State dict to save.
    """
    _STATE_FILE.write_bytes(orjson.dumps(state))


def submit_batch(
    input_path: Path | None = None,
) -> None:
    """Non-blocking batch submission with state tracking.

    Each invocation performs one action and exits:

    - If no active job: splits JSONL (if needed) and submits the
      next chunk. Exits immediately after submission.
    - If active job is still running: reports status and exits.
    - If active job succeeded: downloads results, then submits
      the next chunk (or merges all results if all chunks done).
    - If active job failed: logs error and advances to next chunk.

    Run repeatedly (manually or via cron) until all chunks are done.

    Args:
        input_path: Path to the full JSONL batch file.

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
        raise FileNotFoundError(f"Batch input not found: {input_path}")

    # Split (idempotent -- skips existing chunk files)
    chunks = _split_jsonl(input_path)
    if not chunks:
        logger.error("No chunks produced from input")
        return

    state = _load_state()

    # Check active job if one exists
    active_job: str | None = state.get("job_name")  # type: ignore[assignment]
    active_idx: int = state.get("chunk_idx", 0)  # type: ignore[assignment]

    if active_job:
        batch_job = client.batches.get(name=active_job)
        job_state = ""
        if batch_job.state is not None:
            job_state = batch_job.state.name

        if job_state not in _COMPLETED_STATES:
            print(
                f"[Chunk {active_idx}/{len(chunks)}] "
                f"Job {active_job} is {job_state}. "
                f"Run submit again later."
            )
            return

        # Job finished -- handle result
        if job_state == "JOB_STATE_SUCCEEDED":
            output_path = _BATCH_DIR / f"batch_output_{active_idx:03d}.jsonl"
            if batch_job.dest and batch_job.dest.file_name:
                logger.info(
                    "[Chunk %d] Downloading results", active_idx,
                )
                content = client.files.download(
                    file=batch_job.dest.file_name,
                )
                output_path.write_bytes(content)
                print(
                    f"[Chunk {active_idx}/{len(chunks)}] "
                    f"Complete. Saved to {output_path.name}"
                )
            else:
                logger.error(
                    "[Chunk %d] Succeeded but no output file",
                    active_idx,
                )
        else:
            logger.error(
                "[Chunk %d] Job ended with: %s", active_idx, job_state,
            )

        active_idx += 1
        active_job = None

    # Find next chunk to submit (skip already-downloaded)
    while active_idx < len(chunks):
        output_path = _BATCH_DIR / f"batch_output_{active_idx:03d}.jsonl"
        if output_path.exists() and output_path.stat().st_size > 0:
            active_idx += 1
            continue
        break

    if active_idx >= len(chunks):
        _merge_results(len(chunks))
        _STATE_FILE.unlink(missing_ok=True)
        return

    # Submit next chunk
    chunk_path = chunks[active_idx]
    logger.info(
        "[Chunk %d/%d] Uploading %s",
        active_idx, len(chunks), chunk_path.name,
    )
    uploaded = client.files.upload(
        file=str(chunk_path),
        config=types.UploadFileConfig(
            display_name=f"osh-eval-chunk-{active_idx:03d}",
            mime_type="jsonl",
        ),
    )
    file_resource = uploaded.name
    if not file_resource:
        logger.error("[Chunk %d] Upload returned no resource name", active_idx)
        return

    logger.info("[Chunk %d/%d] Submitting batch job", active_idx, len(chunks))
    batch_job = client.batches.create(
        model=_MODEL_ID,
        src=file_resource,
        config={"display_name": f"osh-eval-chunk-{active_idx:03d}"},
    )
    job_name = batch_job.name
    if not job_name:
        logger.error("[Chunk %d] No job name returned", active_idx)
        return

    _save_state({
        "chunk_idx": active_idx,
        "job_name": job_name,
        "total_chunks": len(chunks),
    })

    print(
        f"[Chunk {active_idx}/{len(chunks)}] "
        f"Submitted: {job_name}\n"
        f"Run 'submit' again later to check status and continue."
    )


def _merge_results(total_chunks: int) -> None:
    """Merge all chunk output files into a single results JSONL.

    Args:
        total_chunks: Total number of chunks to merge.
    """
    merged_path = _BATCH_DIR / "gemini_batch_output.jsonl"
    count = 0
    with open(merged_path, "wb") as out:
        for i in range(total_chunks):
            chunk_output = _BATCH_DIR / f"batch_output_{i:03d}.jsonl"
            if chunk_output.exists():
                data = chunk_output.read_bytes()
                out.write(data)
                if not data.endswith(b"\n"):
                    out.write(b"\n")
                count += 1
    print(
        f"All {count}/{total_chunks} chunks complete. "
        f"Merged results: {merged_path}\n"
        f"Run 'ingest' to load results into the database."
    )


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
    """CLI entry point: prepare, submit, ingest, realtime."""
    parser = argparse.ArgumentParser(
        description=(
            "LLM-based README evaluation via "
            "Gemini Batch or Realtime API"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rt = sub.add_parser(
        "realtime",
        help="Evaluate via real-time Gemini API calls",
    )
    rt.add_argument(
        "--model",
        default=_DEFAULT_REALTIME_MODEL,
        help=(
            "Gemini model ID "
            f"(default: {_DEFAULT_REALTIME_MODEL})"
        ),
    )
    rt.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max projects to process (default: 0 = all)",
    )
    rt.add_argument(
        "--prompt-version",
        default="test_8",
        help="Prompt version (default: test_8)",
    )
    rt.add_argument(
        "--workers",
        type=int,
        default=_DEFAULT_WORKERS,
        help=(
            "Concurrent API threads "
            f"(default: {_DEFAULT_WORKERS})"
        ),
    )

    prep = sub.add_parser("prepare", help="Build JSONL batch input")
    prep.add_argument(
        "--prompt-version",
        default="test_8",
        help="Prompt version (default: test_8)",
    )

    sub.add_parser(
        "submit",
        help="Submit next chunk / check active job (non-blocking)",
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

    if args.command == "realtime":
        run_realtime(
            prompt_version=args.prompt_version,
            model_id=args.model,
            limit=args.limit,
            max_workers=args.workers,
        )

    elif args.command == "prepare":
        path = prepare_batch(prompt_version=args.prompt_version)
        print(f"Batch input written to: {path}")

    elif args.command == "submit":
        submit_batch()

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
