"""Compare gemini-2.5-flash-lite against pilot Haiku 4.5 / Gemini 3 Flash.

Reads README + file tree from the local DB (already fetched), calls
gemini-2.5-flash-lite for the same 4 pilot projects, and compares
field-by-field against the existing raw outputs.

Usage:
    uv run python scripts/compare_flash_lite.py
"""

from __future__ import annotations

import logging
import os
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FLASH_LITE_MODEL = "gemini-2.5-flash-lite"

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "osh_datasets.db"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompt_evaluation"
    / "test_8"
    / "revised_long_prompt.md"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "EDA" / "model_comparison"

TEST_PROJECTS = [
    {"id": 3686, "label": "rich"},
    {"id": 2622, "label": "medium"},
    {"id": 4716, "label": "sparse"},
    {"id": 7346, "label": "testing"},
]

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


def call_flash_lite(system: str, user: str) -> tuple[str, float, int, int]:
    """Call Gemini 2.5 Flash Lite and return response + metadata.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (response_text, latency_s, input_tokens, output_tokens).
    """
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    start = time.monotonic()
    response = client.models.generate_content(
        model=FLASH_LITE_MODEL,
        contents=user,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=8192,
        ),
    )
    latency = time.monotonic() - start
    text = response.text or ""
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0
    return text, latency, input_tokens, output_tokens


# ---- Main ----


def main() -> None:
    """Run the 3-way model comparison."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    system_prompt, user_template = load_prompt()

    conn = sqlite3.connect(str(DB_PATH))

    report_lines: list[str] = [
        "# 3-Way Model Comparison: Haiku 4.5 vs Gemini 3 Flash"
        " vs Gemini 2.5 Flash Lite\n",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n",
        f"Flash Lite model: `{FLASH_LITE_MODEL}`\n",
        "---\n",
    ]

    total_in = 0
    total_out = 0

    for project in TEST_PROJECTS:
        pid = project["id"]
        label = project["label"]

        row = conn.execute(
            "SELECT name, repo_url FROM projects WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            logger.error("Project %d not found", pid)
            continue
        name, repo_url = row[0], row[1]

        # Load README from DB
        rc_row = conn.execute(
            "SELECT content FROM readme_contents WHERE project_id = ?",
            (pid,),
        ).fetchone()
        if not rc_row or not rc_row[0]:
            logger.error("No README for project %d", pid)
            continue
        readme = rc_row[0]

        # Load tree from DB
        tree_rows = conn.execute(
            "SELECT file_path, file_type, size_bytes "
            "FROM repo_file_trees WHERE project_id = ? "
            "ORDER BY file_path",
            (pid,),
        ).fetchall()
        tree_text = format_tree_from_db(tree_rows)

        # Build prompt
        max_readme = 10000
        if len(readme) > max_readme:
            readme_insert = (
                readme[:max_readme] + "\n\n[README TRUNCATED]"
            )
        else:
            readme_insert = readme

        user_prompt = user_template.replace(
            "{directory_structure}", tree_text
        ).replace("{readme_content}", readme_insert)

        logger.info(
            "Project: %s (id=%d, %s) README=%d chars, Tree=%d entries",
            name, pid, label, len(readme), len(tree_rows),
        )

        # Call flash lite
        logger.info("  Calling %s...", FLASH_LITE_MODEL)
        fl_text, fl_lat, fl_in, fl_out = call_flash_lite(
            system_prompt, user_prompt
        )
        total_in += fl_in
        total_out += fl_out
        logger.info(
            "    %.1fs, %d in / %d out tokens", fl_lat, fl_in, fl_out
        )

        # Save raw output
        out_file = OUTPUT_DIR / f"{label}_flash_lite_raw.txt"
        out_file.write_text(fl_text, encoding="utf-8")

        fl_json = extract_json(fl_text)
        if not fl_json:
            logger.error("  Flash Lite JSON parse failed")

        # Load existing raw outputs
        haiku_raw_path = OUTPUT_DIR / f"{label}_haiku_raw.txt"
        gemini_raw_path = OUTPUT_DIR / f"{label}_gemini_raw.txt"
        h_json = None
        g_json = None
        if haiku_raw_path.exists():
            h_json = extract_json(
                haiku_raw_path.read_text(encoding="utf-8")
            )
        if gemini_raw_path.exists():
            g_json = extract_json(
                gemini_raw_path.read_text(encoding="utf-8")
            )

        # Build 3-way comparison table
        report_lines.append(f"## {name} (`{label}` -- id={pid})\n")
        report_lines.append(
            f"README: {len(readme):,} chars | "
            f"Tree: {len(tree_rows):,} entries\n"
        )
        report_lines.append(
            f"| Metric | Flash Lite |\n"
            f"|--------|------------|\n"
            f"| Latency | {fl_lat:.1f}s |\n"
            f"| Input tokens | {fl_in:,} |\n"
            f"| Output tokens | {fl_out:,} |\n"
            f"| JSON parsed | {'Y' if fl_json else 'N'} |\n"
        )

        # Field comparison
        lines = [
            "| Field | Haiku 4.5 | Gemini 3 Flash | Flash Lite |"
            " H=FL | G=FL |"
        ]
        lines.append(
            "|-------|-----------|----------------|------------|"
            "------|------|"
        )
        h_fl_matches = 0
        g_fl_matches = 0
        total = len(COMPARE_FIELDS)

        for path, field_label in COMPARE_FIELDS:
            h_val = get_nested(h_json, path) if h_json else "N/A"
            g_val = get_nested(g_json, path) if g_json else "N/A"
            fl_val = get_nested(fl_json, path) if fl_json else "N/A"

            h_match = h_val == fl_val
            g_match = g_val == fl_val
            if h_match:
                h_fl_matches += 1
            if g_match:
                g_fl_matches += 1

            h_mark = "Y" if h_match else "**N**"
            g_mark = "Y" if g_match else "**N**"
            lines.append(
                f"| {field_label} | {h_val} | {g_val} | {fl_val}"
                f" | {h_mark} | {g_mark} |"
            )

        h_pct = 100 * h_fl_matches / total if total else 0
        g_pct = 100 * g_fl_matches / total if total else 0
        lines.append(
            f"\n**Haiku vs Flash Lite: {h_fl_matches}/{total}"
            f" ({h_pct:.0f}%)**"
        )
        lines.append(
            f"**Gemini 3 vs Flash Lite: {g_fl_matches}/{total}"
            f" ({g_pct:.0f}%)**"
        )

        report_lines.append("\n".join(lines) + "\n\n---\n")

    conn.close()

    # Cost summary
    fl_cost = (total_in / 1e6 * 0.05) + (total_out / 1e6 * 0.20)
    scale = 7057 / len(TEST_PROJECTS) if TEST_PROJECTS else 1
    report_lines.append("## Cost Summary\n")
    report_lines.append(
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Total input tokens | {total_in:,} |\n"
        f"| Total output tokens | {total_out:,} |\n"
        f"| Cost (4 projects) | ${fl_cost:.4f} |\n"
        f"| Extrapolated (7,057 projects) | ${fl_cost * scale:.2f} |\n"
    )

    report_path = OUTPUT_DIR / "flash_lite_comparison.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("Report written to: %s", report_path)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
