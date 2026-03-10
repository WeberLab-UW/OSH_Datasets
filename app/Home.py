"""OSH Datasets Explorer -- Home page with dataset overview."""

import plotly.express as px
import streamlit as st
from db_utils import get_dataset_summary, get_sources_summary

st.set_page_config(
    page_title="OSH Datasets Explorer",
    layout="wide",
)

st.title("OSH Datasets Explorer")
st.markdown(
    "A unified dataset of open-source hardware projects from"
    " 10 platforms, scored for documentation quality using"
    " metadata analysis and LLM evaluation."
)

# ---- Summary metrics ----
summary = get_dataset_summary()
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Total Projects",
    f"{summary.get('total_projects', 0):,}",
    help="Projects collected across all 10 data sources.",
)
c2.metric(
    "Data Sources",
    summary.get("source_count", 0),
    help="Number of distinct platforms scraped.",
)
c3.metric(
    "BOM Components",
    f"{summary.get('bom_count', 0):,}",
    help="Bill of materials entries across all projects.",
)
c4.metric(
    "LLM Evaluations",
    f"{summary.get('llm_count', 0):,}",
    help=(
        "Projects evaluated by Gemini 2.5 Flash Lite"
        " across 12 documentation dimensions."
    ),
)

st.divider()

# ---- Sources breakdown ----
sources = get_sources_summary()

col_chart, col_table = st.columns([1, 1])

with col_chart:
    st.subheader("Projects by Source")
    fig = px.bar(
        sources.to_pandas(),
        x="project_count",
        y="source",
        orientation="h",
        color="source",
        text="project_count",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        showlegend=False,
        yaxis={"categoryorder": "total ascending"},
        xaxis_title="Number of Projects",
        yaxis_title="",
        height=400,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with col_table:
    st.subheader("Source Summary")
    display = sources.select([
        "source",
        "project_count",
        "with_repo",
        "with_llm_eval",
        "avg_completeness",
        "avg_open_o_meter",
    ]).rename({
        "source": "Source",
        "project_count": "Projects",
        "with_repo": "With Repo",
        "with_llm_eval": "LLM Eval",
        "avg_completeness": "Avg Completeness",
        "avg_open_o_meter": "Avg OoM",
    })
    st.dataframe(display, hide_index=True, use_container_width=True)

# ---- Method explanation ----
with st.expander("About this dataset"):
    st.markdown("""
**Data sources:** Projects are collected from 10 open-source
hardware platforms: Hackaday.io, OSHWA Certification Directory,
HardwareX (Elsevier), HardwareIO, Open Hardware Repository
(CERN), Kitspace, Mendeley Data, Open Science Framework (OSF),
PLOS journals, and the Journal of Open Hardware.

**Two-track documentation quality scoring:**

- **Track 1 (metadata-based, all projects):** Four scores
  computed from structured database fields -- Completeness
  (weighted artifact presence, 0-100), Coverage (breadth across
  12 documentation categories, 0-100), Depth (continuous signals
  for documentation investment, 0-100), and Open-o-Meter
  (reproduction of Bonvoisin & Mies 2018, 0-8).

- **Track 2 (LLM-based, GitHub projects):** Gemini 2.5 Flash
  Lite batch evaluation of README content and repository file
  trees across 12 dimensions including license, BOM, assembly
  instructions, design files, testing, and contribution
  guidelines.

**Pipeline:** Raw data is scraped from each platform, cleaned
into standardized CSVs, loaded into a unified SQLite database,
then enriched with GitHub metrics, BOM normalization, cross-source
deduplication, and documentation quality scoring.
""")
