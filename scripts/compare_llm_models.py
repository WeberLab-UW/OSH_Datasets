"""Compare Claude Haiku 4.5 vs Gemini 3 Flash on README evaluation.

Fetches README + file tree from GitHub for 4 diverse projects, sends
the test_8 prompt to both models, and writes a side-by-side comparison.

Usage:
    uv run python scripts/compare_llm_models.py
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import orjson
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# ── Configuration ──────────────────────────────────────────────────────

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
GEMINI_MODEL = "gemini-3-flash-preview"

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "osh_datasets.db"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompt_evaluation"
    / "test_8"
    / "revised_long_prompt.md"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "EDA" / "model_comparison"

# Test project IDs: rich, medium, sparse, testing-positive
TEST_PROJECTS = [
    {"id": 3686, "label": "rich"},
    {"id": 2622, "label": "medium"},
    {"id": 4716, "label": "sparse"},
    {"id": 7346, "label": "testing"},
]

GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Haiku: $1/$5 per 1M tokens; Gemini 3 Flash: $0.50/$3.00 per 1M tokens
PRICING = {
    "haiku": {"input": 1.0, "output": 5.0},
    "gemini": {"input": 0.5, "output": 3.0},
}


# ── Prompt loading ─────────────────────────────────────────────────────


def load_prompt() -> tuple[str, str]:
    """Load system prompt and user template from test_6.

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


# ── GitHub data fetching ───────────────────────────────────────────────


def extract_owner_repo(url: str) -> tuple[str, str] | None:
    """Extract owner/repo from a GitHub URL.

    Args:
        url: GitHub repository URL.

    Returns:
        Tuple of (owner, repo) or None if unparseable.
    """
    match = re.search(r"github\.com/([^/]+)/([^/,\s]+)", url)
    if not match:
        return None
    repo = match.group(2).rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return match.group(1), repo


def fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch raw README content from GitHub API.

    Args:
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Raw README text or None on failure.
    """
    headers = {
        **GITHUB_HEADERS,
        "Accept": "application/vnd.github.raw+json",
    }
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/readme",
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.text
    logger.error(
        "README fetch failed (%d): %s/%s", resp.status_code, owner, repo
    )
    return None


def fetch_file_tree(
    owner: str, repo: str
) -> list[dict[str, str]] | None:
    """Fetch recursive file tree from GitHub API.

    Args:
        owner: Repository owner.
        repo: Repository name.

    Returns:
        List of {path, type} dicts or None on failure.
    """
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=GITHUB_HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        logger.error(
            "Repo metadata failed (%d): %s/%s",
            resp.status_code, owner, repo,
        )
        return None
    default_branch = resp.json().get("default_branch", "main")

    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}"
        f"/git/trees/{default_branch}",
        headers=GITHUB_HEADERS,
        params={"recursive": "1"},
        timeout=30,
    )
    if resp.status_code != 200:
        logger.error(
            "Tree fetch failed (%d): %s/%s",
            resp.status_code, owner, repo,
        )
        return None
    return [
        {"path": item["path"], "type": item["type"]}
        for item in resp.json().get("tree", [])
    ]


def format_tree(entries: list[dict[str, str]]) -> str:
    """Render file tree entries as indented directory structure.

    Args:
        entries: List of {path, type} dicts from GitHub tree API.

    Returns:
        Formatted directory structure string.
    """
    lines: list[str] = []
    for entry in sorted(entries, key=lambda e: e["path"]):
        parts = entry["path"].split("/")
        indent = "  " * (len(parts) - 1)
        name = parts[-1]
        suffix = "/" if entry["type"] == "tree" else ""
        lines.append(f"{indent}{name}{suffix}")
    return "\n".join(lines)


# ── LLM calls ─────────────────────────────────────────────────────────

# Result type: (response_text, latency_s, input_tokens, output_tokens)
LLMResult = tuple[str, float, int, int]


def call_haiku(system: str, user: str) -> LLMResult | None:
    """Call Claude Haiku 4.5 and return response + metadata.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (response_text, latency_s, input_tokens, output_tokens)
        or None if the API key is missing/invalid.
    """
    if not ANTHROPIC_API_KEY or "your_" in ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set -- skipping Haiku")
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
    return text, latency, response.usage.input_tokens, response.usage.output_tokens


def call_gemini(system: str, user: str) -> LLMResult | None:
    """Call Gemini 3 Flash and return response + metadata.

    Args:
        system: System prompt.
        user: User prompt.

    Returns:
        Tuple of (response_text, latency_s, input_tokens, output_tokens)
        or None if the API key is missing/invalid.
    """
    if not GEMINI_API_KEY or "your_" in GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set -- skipping Gemini")
        return None
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    start = time.monotonic()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=4096,
        ),
    )
    latency = time.monotonic() - start
    text = response.text or ""
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0
    return text, latency, input_tokens, output_tokens


# ── JSON extraction ────────────────────────────────────────────────────


def extract_json(raw: str) -> dict | None:
    """Extract the first JSON block from LLM response text.

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed dict or None on failure.
    """
    match = re.search(r"```json\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        try:
            return orjson.loads(match.group(1))
        except orjson.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return orjson.loads(match.group(0))
        except orjson.JSONDecodeError:
            pass
    return None


# ── Comparison logic ───────────────────────────────────────────────────

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


def get_nested(data: dict, path: str) -> str:
    """Get a nested dict value by dot-separated path.

    Args:
        data: Parsed JSON dict.
        path: Dot-separated key path.

    Returns:
        String representation of the value.
    """
    current: dict | object = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return "N/A"
        current = current[key]
    return str(current)


def build_comparison_table(
    haiku_json: dict | None, gemini_json: dict | None
) -> str:
    """Build a markdown comparison table for two model outputs.

    Args:
        haiku_json: Parsed Haiku response.
        gemini_json: Parsed Gemini response.

    Returns:
        Markdown table string.
    """
    lines = ["| Field | Haiku 4.5 | Gemini 3 Flash | Match |"]
    lines.append("|-------|-----------|----------------|-------|")
    matches = 0
    total = len(COMPARE_FIELDS)
    for path, label in COMPARE_FIELDS:
        h_val = (
            get_nested(haiku_json, path)
            if haiku_json
            else "PARSE_FAIL"
        )
        g_val = (
            get_nested(gemini_json, path)
            if gemini_json
            else "PARSE_FAIL"
        )
        match = h_val == g_val
        if match:
            matches += 1
        marker = "Y" if match else "**N**"
        lines.append(f"| {label} | {h_val} | {g_val} | {marker} |")
    pct = 100 * matches / total if total else 0
    lines.append(f"\n**Agreement: {matches}/{total} ({pct:.0f}%)**")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    """Run the model comparison pipeline."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    system_prompt, user_template = load_prompt()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    report_lines: list[str] = [
        "# LLM Model Comparison: Haiku 4.5 vs Gemini 3 Flash\n",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n",
        f"Haiku model: `{HAIKU_MODEL}`\n",
        f"Gemini model: `{GEMINI_MODEL}`\n",
        "---\n",
    ]

    total_tokens: dict[str, dict[str, int]] = {
        "haiku": {"input": 0, "output": 0},
        "gemini": {"input": 0, "output": 0},
    }

    for project in TEST_PROJECTS:
        pid = project["id"]
        label = project["label"]
        row = conn.execute(
            "SELECT name, repo_url FROM projects WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            logger.error("Project %d not found, skipping", pid)
            continue

        name, repo_url = row["name"], row["repo_url"]
        logger.info("=" * 60)
        logger.info("Project: %s (id=%d, %s)", name, pid, label)

        parsed = extract_owner_repo(repo_url)
        if not parsed:
            logger.error("Could not parse owner/repo from %s", repo_url)
            continue
        owner, repo = parsed

        readme = fetch_readme(owner, repo)
        if readme is None:
            continue
        tree_entries = fetch_file_tree(owner, repo)
        if tree_entries is None:
            continue

        max_tree = 500
        if len(tree_entries) > max_tree:
            tree_entries = tree_entries[:max_tree]
            logger.info(
                "  Tree truncated to %d entries", max_tree
            )
        tree_text = format_tree(tree_entries)

        # Truncate inputs (not the assembled prompt) to
        # preserve JSON schema and critical rules at the end
        max_readme = 10000
        if len(readme) > max_readme:
            readme_insert = readme[:max_readme] + "\n\n[README TRUNCATED]"
            logger.info(
                "  README truncated to %d chars", max_readme
            )
        else:
            readme_insert = readme
        max_tree_chars = 12000
        if len(tree_text) > max_tree_chars:
            tree_insert = (
                tree_text[:max_tree_chars] + "\n\n[TREE TRUNCATED]"
            )
            logger.info(
                "  Tree text truncated to %d chars", max_tree_chars
            )
        else:
            tree_insert = tree_text
        user_prompt = user_template.replace(
            "{directory_structure}", tree_insert
        ).replace("{readme_content}", readme_insert)

        logger.info(
            "  README: %d chars, Tree: %d entries",
            len(readme), len(tree_entries),
        )

        # Call both models
        logger.info("  Calling Haiku 4.5...")
        h_result = call_haiku(system_prompt, user_prompt)
        if h_result:
            h_text, h_lat, h_in, h_out = h_result
            total_tokens["haiku"]["input"] += h_in
            total_tokens["haiku"]["output"] += h_out
            logger.info("    %.1fs, %d in / %d out tokens", h_lat, h_in, h_out)
        else:
            h_text, h_lat, h_in, h_out = "", 0.0, 0, 0

        logger.info("  Calling Gemini 3 Flash...")
        g_result = call_gemini(system_prompt, user_prompt)
        if g_result:
            g_text, g_lat, g_in, g_out = g_result
            total_tokens["gemini"]["input"] += g_in
            total_tokens["gemini"]["output"] += g_out
            logger.info("    %.1fs, %d in / %d out tokens", g_lat, g_in, g_out)
        else:
            g_text, g_lat, g_in, g_out = "", 0.0, 0, 0

        h_json = extract_json(h_text) if h_text else None
        g_json = extract_json(g_text) if g_text else None
        if h_text and h_json is None:
            logger.error("  Haiku JSON parse failed")
        if g_text and g_json is None:
            logger.error("  Gemini JSON parse failed")

        for model_name, text in [("haiku", h_text), ("gemini", g_text)]:
            if text:
                out_file = OUTPUT_DIR / f"{label}_{model_name}_raw.txt"
                out_file.write_text(text, encoding="utf-8")

        table = build_comparison_table(h_json, g_json)

        report_lines.append(f"## {name} (`{label}` -- id={pid})\n")
        report_lines.append(f"Repo: `{owner}/{repo}`\n")
        report_lines.append(
            f"README: {len(readme):,} chars | "
            f"Tree: {len(tree_entries):,} entries\n"
        )
        h_parsed = "Y" if h_json else ("N" if h_text else "SKIP")
        g_parsed = "Y" if g_json else ("N" if g_text else "SKIP")
        report_lines.append(
            f"| Metric | Haiku 4.5 | Gemini 3 Flash |\n"
            f"|--------|-----------|----------------|\n"
            f"| Latency | {h_lat:.1f}s | {g_lat:.1f}s |\n"
            f"| Input tokens | {h_in:,} | {g_in:,} |\n"
            f"| Output tokens | {h_out:,} | {g_out:,} |\n"
            f"| JSON parsed | {h_parsed} | {g_parsed} |\n"
        )
        report_lines.append(table + "\n\n---\n")

    conn.close()

    # Cost summary
    h_in_t = total_tokens["haiku"]["input"]
    h_out_t = total_tokens["haiku"]["output"]
    g_in_t = total_tokens["gemini"]["input"]
    g_out_t = total_tokens["gemini"]["output"]
    h_cost = (h_in_t / 1e6 * PRICING["haiku"]["input"]) + (
        h_out_t / 1e6 * PRICING["haiku"]["output"]
    )
    g_cost = (g_in_t / 1e6 * PRICING["gemini"]["input"]) + (
        g_out_t / 1e6 * PRICING["gemini"]["output"]
    )

    report_lines.append("## Cost Summary (this test run)\n")
    report_lines.append(
        f"| Model | Input tokens | Output tokens "
        f"| Cost | Batch (50% off) |\n"
        f"|-------|-------------|--------------- "
        f"|------|------------|\n"
        f"| Haiku 4.5 | {h_in_t:,} | {h_out_t:,} "
        f"| ${h_cost:.4f} | ${h_cost * 0.5:.4f} |\n"
        f"| Gemini 3 Flash | {g_in_t:,} | {g_out_t:,} "
        f"| ${g_cost:.4f} | ${g_cost * 0.5:.4f} |\n"
    )

    n_projects = len(TEST_PROJECTS)
    if n_projects > 0:
        scale = 8000 / n_projects
        report_lines.append("\n## Extrapolated Cost (~8,000 projects)\n")
        report_lines.append(
            f"| Model | Estimated cost | Batch cost |\n"
            f"|-------|---------------|------------|\n"
            f"| Haiku 4.5 | ${h_cost * scale:.2f} "
            f"| ${h_cost * 0.5 * scale:.2f} |\n"
            f"| Gemini 3 Flash | ${g_cost * scale:.2f} "
            f"| ${g_cost * 0.5 * scale:.2f} |\n"
        )

    report_path = OUTPUT_DIR / "comparison_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("Report written to: %s", report_path)


if __name__ == "__main__":
    main()
