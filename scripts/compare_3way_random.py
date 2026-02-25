"""3-way model comparison on a random sample of repositories.

Selects N random projects (with README + file tree in DB), runs
Haiku 4.5, Gemini 3 Flash, and Gemini 2.5 Flash Lite on each,
and produces a field-by-field comparison report.

Usage:
    uv run python scripts/compare_3way_random.py --n 10
    uv run python scripts/compare_3way_random.py --n 10 --seed 42
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import random
import re
import sqlite3
import time
from pathlib import Path

import orjson
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# ---- Config ----

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
GEMINI3_MODEL = "gemini-3-flash-preview"
FLASH_LITE_MODEL = "gemini-2.5-flash-lite"

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "osh_datasets.db"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompt_evaluation"
    / "test_8"
    / "revised_long_prompt.md"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "EDA" / "model_comparison"

COMPARE_FIELDS = [
    ("metadata.project_type", "Project type"),
    ("metadata.structure_quality", "Structure quality"),
    ("metadata.documentation_location", "Doc location"),
    ("license.present", "License present"),
    ("license.type", "License type"),
    ("license.name", "License name"),
    ("contributing.present", "Contributing present"),
    ("contributing.level", "Contributing level"),
    ("bom.present", "BOM present"),
    ("bom.completeness", "BOM completeness"),
    ("bom.component_count", "BOM component count"),
    ("assembly.present", "Assembly present"),
    ("assembly.detail_level", "Assembly detail"),
    ("assembly.step_count", "Assembly step count"),
    ("design_files.hardware.present", "HW design present"),
    ("design_files.hardware.types", "HW design types"),
    ("design_files.hardware.has_editable_source", "HW editable src"),
    ("design_files.mechanical.present", "Mech design present"),
    ("design_files.mechanical.types", "Mech design types"),
    ("design_files.mechanical.has_editable_source", "Mech editable src"),
    ("software_firmware.present", "SW/FW present"),
    ("software_firmware.type", "SW/FW type"),
    ("software_firmware.frameworks", "SW/FW frameworks"),
    ("software_firmware.documentation_level", "SW/FW doc level"),
    ("testing.present", "Testing present"),
    ("testing.detail_level", "Testing detail"),
    ("cost_sourcing.estimated_cost_mentioned", "Cost mentioned"),
    ("cost_sourcing.suppliers_referenced", "Suppliers ref'd"),
    ("cost_sourcing.part_numbers_present", "Part numbers"),
    ("project_maturity.stage", "Maturity stage"),
    ("specific_licenses.hardware.present", "HW license present"),
    ("specific_licenses.hardware.name", "HW license name"),
    ("specific_licenses.software.present", "SW license present"),
    ("specific_licenses.software.name", "SW license name"),
    ("specific_licenses.documentation.present", "Doc license present"),
    ("specific_licenses.documentation.name", "Doc license name"),
]


# ---- Helpers ----


def load_prompt() -> tuple[str, str]:
    """Load system prompt and user template from test_8.

    Returns:
        Tuple of (system_prompt, user_prompt_template).
    """
    content = PROMPT_PATH.read_text(encoding="utf-8")
    sys_match = re.search(
        r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL
    )
    user_match = re.search(
        r'USER_PROMPT_TEMPLATE\s*=\s*"""(.*?)"""', content, re.DOTALL
    )
    if not sys_match or not user_match:
        raise ValueError(
            "Could not parse SYSTEM_PROMPT / USER_PROMPT_TEMPLATE"
        )
    return sys_match.group(1).strip(), user_match.group(1).strip()


def format_tree_from_db(
    rows: list[tuple[str, str, int | None]],
) -> str:
    """Render file tree entries as indented directory structure.

    Args:
        rows: List of (path, type, size) tuples from repo_file_trees.

    Returns:
        Formatted directory structure string.
    """
    sorted_rows = sorted(rows, key=lambda r: r[0])
    if len(sorted_rows) > 500:
        sorted_rows = sorted_rows[:500]
    lines: list[str] = []
    for path, ftype, _size in sorted_rows:
        parts = path.split("/")
        indent = "  " * (len(parts) - 1)
        name = parts[-1]
        suffix = "/" if ftype == "tree" else ""
        lines.append(f"{indent}{name}{suffix}")
    result = "\n".join(lines)
    if len(result) > 12000:
        result = result[:12000] + "\n\n[TREE TRUNCATED]"
    return result


def extract_json(raw: str) -> dict[str, object] | None:
    """Extract the outermost JSON object from LLM response text.

    Uses brace-depth counting with string-literal awareness to
    correctly handle JSON containing triple backticks in string
    values (e.g., evidence fields quoting README code blocks).

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed dict or None on failure.
    """
    start = raw.find("{")
    if start == -1:
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
                    return orjson.loads(json_str)
                except orjson.JSONDecodeError:
                    pass
                return None

    return None


def get_nested(data: dict[str, object], path: str) -> str:
    """Get a nested dict value by dot-separated path.

    Args:
        data: Parsed JSON dict.
        path: Dot-separated key path.

    Returns:
        String representation of the value.
    """
    current: dict[str, object] | object = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return "N/A"
        current = current[key]
    return str(current)


# ---- LLM Calls ----


LLMResult = tuple[str, float, int, int]


def call_haiku(system: str, user: str) -> LLMResult | None:
    """Call Claude Haiku 4.5 and return response + metadata.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (text, latency_s, input_tokens, output_tokens)
        or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        return None
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    start = time.monotonic()
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=8192,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    latency = time.monotonic() - start
    text = response.content[0].text
    return (
        text,
        latency,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )


def _call_gemini(
    model: str, system: str, user: str,
) -> LLMResult | None:
    """Call a Gemini model with timeout and error handling.

    Args:
        model: Gemini model ID.
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (text, latency_s, input_tokens, output_tokens)
        or None on failure.
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set")
        return None
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    start = time.monotonic()

    def _do_call() -> LLMResult:
        response = client.models.generate_content(
            model=model,
            contents=user,
            config=genai.types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                max_output_tokens=8192,
                automatic_function_calling=genai.types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        text = response.text or ""
        usage = response.usage_metadata
        elapsed = time.monotonic() - start
        return (
            text,
            elapsed,
            usage.prompt_token_count if usage else 0,
            usage.candidates_token_count if usage else 0,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_call)
        try:
            return future.result(timeout=60)
        except concurrent.futures.TimeoutError:
            logger.error(
                "  %s timed out after 60s", model,
            )
            return None
        except Exception as exc:
            latency = time.monotonic() - start
            logger.error(
                "  %s failed after %.1fs: %s",
                model, latency, exc,
            )
            return None


def call_gemini3(system: str, user: str) -> LLMResult | None:
    """Call Gemini 3 Flash with 60s timeout.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (text, latency_s, input_tokens, output_tokens)
        or None on failure.
    """
    return _call_gemini(GEMINI3_MODEL, system, user)


def call_flash_lite(system: str, user: str) -> LLMResult | None:
    """Call Gemini 2.5 Flash Lite with 60s timeout.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (text, latency_s, input_tokens, output_tokens)
        or None on failure.
    """
    return _call_gemini(FLASH_LITE_MODEL, system, user)


# ---- Main ----


def main() -> None:
    """Run the 3-way model comparison on random projects."""
    parser = argparse.ArgumentParser(
        description="3-way LLM comparison on random sample"
    )
    parser.add_argument(
        "--n", type=int, default=10, help="Number of projects"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed"
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    system_prompt, user_template = load_prompt()

    conn = sqlite3.connect(str(DB_PATH))

    # Select random projects with README > 100 chars + tree
    all_candidates = conn.execute(
        """\
        SELECT rc.project_id
        FROM readme_contents rc
        WHERE rc.content IS NOT NULL
          AND LENGTH(rc.content) > 100
          AND EXISTS (
              SELECT 1 FROM repo_file_trees rft
              WHERE rft.project_id = rc.project_id
          )
        ORDER BY rc.project_id
        """,
    ).fetchall()

    all_ids = [r[0] for r in all_candidates]
    if args.seed is not None:
        random.seed(args.seed)
    project_ids = random.sample(all_ids, min(args.n, len(all_ids)))
    logger.info("Selected %d projects: %s", len(project_ids), project_ids)

    # Pricing per 1M tokens
    pricing = {
        "haiku": {"input": 1.0, "output": 5.0},
        "gemini3": {"input": 0.50, "output": 3.00},
        "flash_lite": {"input": 0.05, "output": 0.20},
    }
    totals: dict[str, dict[str, int]] = {
        m: {"input": 0, "output": 0}
        for m in pricing
    }

    seed_str = f" (seed={args.seed})" if args.seed else ""
    report_lines: list[str] = [
        "# 3-Way Model Comparison: Random Sample"
        f" (n={args.n}{seed_str})\n",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n",
        "| Model | ID |\n|-------|----|\n"
        f"| Haiku 4.5 | `{HAIKU_MODEL}` |\n"
        f"| Gemini 3 Flash | `{GEMINI3_MODEL}` |\n"
        f"| Flash Lite | `{FLASH_LITE_MODEL}` |\n",
        "---\n",
    ]

    # Aggregate agreement counters
    agg_hg = 0  # Haiku vs Gemini3
    agg_hf = 0  # Haiku vs Flash Lite
    agg_gf = 0  # Gemini3 vs Flash Lite
    agg_all = 0  # All three agree
    agg_total = 0

    for idx, pid in enumerate(project_ids):
        row = conn.execute(
            "SELECT name, repo_url FROM projects WHERE id = ?",
            (pid,),
        ).fetchone()
        if not row:
            logger.error("Project %d not found", pid)
            continue
        name, repo_url = row[0], row[1]

        rc_row = conn.execute(
            "SELECT content FROM readme_contents WHERE project_id = ?",
            (pid,),
        ).fetchone()
        if not rc_row or not rc_row[0]:
            logger.error("No README for project %d", pid)
            continue
        readme = rc_row[0]

        tree_rows = conn.execute(
            "SELECT file_path, file_type, size_bytes "
            "FROM repo_file_trees WHERE project_id = ? "
            "ORDER BY file_path",
            (pid,),
        ).fetchall()
        tree_text = format_tree_from_db(tree_rows)

        # Truncate README
        max_readme = 10000
        readme_insert = readme
        if len(readme) > max_readme:
            readme_insert = (
                readme[:max_readme] + "\n\n[README TRUNCATED]"
            )

        user_prompt = user_template.replace(
            "{directory_structure}", tree_text
        ).replace("{readme_content}", readme_insert)

        logger.info(
            "[%d/%d] %s (id=%d) README=%d Tree=%d",
            idx + 1, len(project_ids),
            name, pid, len(readme), len(tree_rows),
        )

        # Call all 3 models
        results: dict[str, LLMResult | None] = {}
        for model_key, caller in [
            ("haiku", call_haiku),
            ("gemini3", call_gemini3),
            ("flash_lite", call_flash_lite),
        ]:
            logger.info("  %s ...", model_key)
            result = caller(system_prompt, user_prompt)
            results[model_key] = result
            if result:
                _text, lat, tin, tout = result
                totals[model_key]["input"] += tin
                totals[model_key]["output"] += tout
                logger.info("    %.1fs, %d in / %d out", lat, tin, tout)

        # Parse JSON from each
        jsons: dict[str, dict[str, object] | None] = {}
        for model_key in ["haiku", "gemini3", "flash_lite"]:
            r = results[model_key]
            raw_text = r[0] if r else ""
            jsons[model_key] = extract_json(raw_text) if raw_text else None
            if raw_text and jsons[model_key] is None:
                logger.error("  %s JSON parse failed", model_key)

        # Save raw outputs
        for model_key in ["haiku", "gemini3", "flash_lite"]:
            r = results[model_key]
            if r and r[0]:
                out_file = (
                    OUTPUT_DIR / f"random_{pid}_{model_key}_raw.txt"
                )
                out_file.write_text(r[0], encoding="utf-8")

        # Build comparison table
        h = jsons["haiku"]
        g = jsons["gemini3"]
        f = jsons["flash_lite"]

        report_lines.append(
            f"## {idx + 1}. {name} (id={pid})\n"
        )
        report_lines.append(
            f"README: {len(readme):,} chars | "
            f"Tree: {len(tree_rows):,} entries\n"
        )

        # Latency/token table
        metric_lines = [
            "| Metric | Haiku | Gemini 3 | Flash Lite |",
            "|--------|-------|----------|------------|",
        ]
        for model_key, label in [
            ("haiku", "Haiku"),
            ("gemini3", "Gemini 3"),
            ("flash_lite", "Flash Lite"),
        ]:
            pass  # handled below

        r_h = results["haiku"]
        r_g = results["gemini3"]
        r_f = results["flash_lite"]
        metric_lines.append(
            f"| Latency | {r_h[1]:.1f}s | {r_g[1]:.1f}s | "
            f"{r_f[1]:.1f}s |"
            if r_h and r_g and r_f
            else "| Latency | - | - | - |"
        )
        metric_lines.append(
            f"| Input tok | {r_h[2]:,} | {r_g[2]:,} | "
            f"{r_f[2]:,} |"
            if r_h and r_g and r_f
            else "| Input tok | - | - | - |"
        )
        metric_lines.append(
            f"| Output tok | {r_h[3]:,} | {r_g[3]:,} | "
            f"{r_f[3]:,} |"
            if r_h and r_g and r_f
            else "| Output tok | - | - | - |"
        )
        h_ok = "Y" if h else "N"
        g_ok = "Y" if g else "N"
        f_ok = "Y" if f else "N"
        metric_lines.append(
            f"| JSON OK | {h_ok} | {g_ok} | {f_ok} |"
        )
        report_lines.append("\n".join(metric_lines) + "\n")

        # Field comparison
        lines = [
            "| Field | Haiku | Gemini 3 | Flash Lite "
            "| H=G | H=FL | G=FL | All |",
            "|-------|-------|----------|------------"
            "|-----|------|------|-----|",
        ]
        hg_match = hf_match = gf_match = all_match = 0
        total_fields = len(COMPARE_FIELDS)

        for path, field_label in COMPARE_FIELDS:
            h_val = get_nested(h, path) if h else "FAIL"
            g_val = get_nested(g, path) if g else "FAIL"
            f_val = get_nested(f, path) if f else "FAIL"

            hg = h_val == g_val
            hf = h_val == f_val
            gf = g_val == f_val
            all3 = hg and hf

            if hg:
                hg_match += 1
            if hf:
                hf_match += 1
            if gf:
                gf_match += 1
            if all3:
                all_match += 1

            lines.append(
                f"| {field_label} | {h_val} | {g_val} | {f_val}"
                f" | {'Y' if hg else '**N**'}"
                f" | {'Y' if hf else '**N**'}"
                f" | {'Y' if gf else '**N**'}"
                f" | {'Y' if all3 else '**N**'} |"
            )

        agg_hg += hg_match
        agg_hf += hf_match
        agg_gf += gf_match
        agg_all += all_match
        agg_total += total_fields

        hg_pct = 100 * hg_match / total_fields
        hf_pct = 100 * hf_match / total_fields
        gf_pct = 100 * gf_match / total_fields
        all_pct = 100 * all_match / total_fields

        lines.append(
            f"\n| **Totals** | | | "
            f"| **{hg_match}/{total_fields} ({hg_pct:.0f}%)**"
            f" | **{hf_match}/{total_fields} ({hf_pct:.0f}%)**"
            f" | **{gf_match}/{total_fields} ({gf_pct:.0f}%)**"
            f" | **{all_match}/{total_fields} ({all_pct:.0f}%)** |"
        )

        report_lines.append("\n".join(lines) + "\n\n---\n")

    conn.close()

    # ---- Aggregate summary ----
    report_lines.append("## Aggregate Agreement\n")
    if agg_total > 0:
        report_lines.append(
            "| Pair | Matches | Total | Agreement |\n"
            "|------|---------|-------|-----------|\n"
            f"| Haiku vs Gemini 3 | {agg_hg} | {agg_total}"
            f" | {100 * agg_hg / agg_total:.1f}% |\n"
            f"| Haiku vs Flash Lite | {agg_hf} | {agg_total}"
            f" | {100 * agg_hf / agg_total:.1f}% |\n"
            f"| Gemini 3 vs Flash Lite | {agg_gf} | {agg_total}"
            f" | {100 * agg_gf / agg_total:.1f}% |\n"
            f"| All three agree | {agg_all} | {agg_total}"
            f" | {100 * agg_all / agg_total:.1f}% |\n"
        )

    # ---- Cost summary ----
    report_lines.append("## Cost Summary\n")
    cost_lines = [
        "| Model | Input tok | Output tok | Cost"
        " | Per-project | Extrap (7,057) |",
        "|-------|-----------|------------|------"
        "|-------------|----------------|",
    ]
    n = len(project_ids)
    for model_key, label in [
        ("haiku", "Haiku 4.5"),
        ("gemini3", "Gemini 3 Flash"),
        ("flash_lite", "Flash Lite"),
    ]:
        tin = totals[model_key]["input"]
        tout = totals[model_key]["output"]
        cost = (
            tin / 1e6 * pricing[model_key]["input"]
            + tout / 1e6 * pricing[model_key]["output"]
        )
        per_proj = cost / n if n > 0 else 0
        extrap = per_proj * 7057
        cost_lines.append(
            f"| {label} | {tin:,} | {tout:,} | ${cost:.4f}"
            f" | ${per_proj:.4f} | ${extrap:.2f} |"
        )
    report_lines.append("\n".join(cost_lines) + "\n")

    report_path = OUTPUT_DIR / "random_3way_comparison.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("Report: %s", report_path)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
