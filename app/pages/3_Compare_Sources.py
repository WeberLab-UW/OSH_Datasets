"""Compare Sources -- side-by-side statistics and gap analysis."""

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st
from db_utils import (
    get_source_coverage_matrix,
    get_sources_summary,
    get_track2_binary_rates,
)

st.set_page_config(
    page_title="Compare Sources - OSH Datasets",
    layout="wide",
)

st.title("Compare Sources")

sources_df = get_sources_summary()
all_sources = sources_df["source"].to_list()

# ---- Sidebar ----
with st.sidebar:
    selected = st.multiselect(
        "Sources to compare",
        options=all_sources,
        default=all_sources,
        help="Select which sources to include.",
    )

if not selected:
    st.info("Select at least one source in the sidebar.")
    st.stop()

filtered = sources_df.filter(pl.col("source").is_in(selected))

# ---- Source overview table ----
st.subheader("Source Overview")
display = filtered.select([
    "source",
    "project_count",
    "with_repo",
    "with_llm_eval",
    "avg_completeness",
    "avg_coverage",
    "avg_depth",
    "avg_open_o_meter",
]).rename({
    "source": "Source",
    "project_count": "Projects",
    "with_repo": "With Repo",
    "with_llm_eval": "LLM Eval",
    "avg_completeness": "Avg Completeness",
    "avg_coverage": "Avg Coverage",
    "avg_depth": "Avg Depth",
    "avg_open_o_meter": "Avg OoM",
})
st.dataframe(display, hide_index=True, use_container_width=True)

st.divider()

# ---- Radar chart ----
st.subheader("Track 1 Score Profiles")

fig_radar = go.Figure()
for row in filtered.iter_rows(named=True):
    vals = [
        row["avg_completeness"] or 0,
        row["avg_coverage"] or 0,
        row["avg_depth"] or 0,
        (row["avg_open_o_meter"] or 0) / 8 * 100,
    ]
    # Close the polygon
    vals.append(vals[0])
    cats = [
        "Completeness",
        "Coverage",
        "Depth",
        "Open-o-Meter (scaled)",
        "Completeness",
    ]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals,
        theta=cats,
        name=row["source"],
        fill="toself",
        opacity=0.5,
    ))

fig_radar.update_layout(
    polar={"radialaxis": {"range": [0, 100]}},
    height=450,
    margin={"t": 30, "b": 30},
    legend={"orientation": "h", "y": -0.1},
)
st.plotly_chart(fig_radar, use_container_width=True)

st.caption(
    "Open-o-Meter is scaled from 0-8 to 0-100 for"
    " visual comparability. All other scores are 0-100."
)

st.divider()

# ---- Documentation gap heatmap (Track 2) ----
st.subheader("Documentation Gap Analysis (Track 2)")

df_rates = get_track2_binary_rates()
df_rates = df_rates.filter(
    pl.col("source").is_in(selected) & (pl.col("total") >= 10),
)

binary_dims = [
    "license_present",
    "bom_present",
    "assembly_present",
    "hw_design_present",
    "mech_design_present",
    "sw_fw_present",
    "testing_present",
    "contributing_present",
    "cost_mentioned",
    "suppliers_referenced",
    "part_numbers_present",
]
dim_labels = [
    "License",
    "BOM",
    "Assembly",
    "HW Design",
    "Mech Design",
    "SW/FW",
    "Testing",
    "Contributing",
    "Cost",
    "Suppliers",
    "Part Numbers",
]

if df_rates.height > 0:
    hm_sources: list[str] = []
    hm_matrix: list[list[float]] = []
    for row in df_rates.iter_rows(named=True):
        hm_sources.append(row["source"])
        hm_matrix.append([
            round(row[dim] / row["total"] * 100, 1)
            for dim in binary_dims
        ])

    fig_hm = go.Figure(
        data=go.Heatmap(
            z=hm_matrix,
            x=dim_labels,
            y=hm_sources,
            text=[[f"{v:.0f}%" for v in row] for row in hm_matrix],
            texttemplate="%{text}",
            colorscale="RdYlGn",
            zmin=0,
            zmax=100,
        ),
    )
    fig_hm.update_layout(
        height=max(250, len(hm_sources) * 45),
        margin={"t": 10, "b": 10},
        xaxis={"tickangle": -45},
    )
    st.plotly_chart(fig_hm, use_container_width=True)
else:
    st.info(
        "No selected sources have LLM evaluations"
        " (minimum 10 projects required)."
    )

st.divider()

# ---- Coverage matrix (metadata signals) ----
st.subheader("Metadata Coverage by Source")

cov = get_source_coverage_matrix()
cov = cov.filter(pl.col("source").is_in(selected))

if cov.height > 0:
    cov_cols = [
        "has_repo",
        "has_license",
        "has_bom",
        "has_contributors",
        "has_publications",
        "has_description",
    ]
    cov_labels = [
        "Repository",
        "License",
        "BOM",
        "Contributors",
        "Publications",
        "Description",
    ]

    bar_data = []
    for row in cov.iter_rows(named=True):
        for col_name, label in zip(
            cov_cols, cov_labels, strict=True,
        ):
            bar_data.append({
                "Source": row["source"],
                "Signal": label,
                "Percentage": round(
                    row[col_name] / row["total"] * 100, 1,
                ),
            })

    df_bar = pl.DataFrame(bar_data)
    fig_cov = px.bar(
        df_bar.to_pandas(),
        x="Signal",
        y="Percentage",
        color="Source",
        barmode="group",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_cov.update_layout(
        yaxis_title="% of Projects",
        yaxis_range=[0, 105],
        xaxis_title="",
        height=400,
        margin={"t": 10},
        legend={"orientation": "h", "y": -0.15},
    )
    st.plotly_chart(fig_cov, use_container_width=True)

# ---- Method explanation ----
with st.expander("Interpreting the gap analysis"):
    st.markdown("""
**Documentation gap heatmap:** Each cell shows the percentage
of projects from a given source where a documentation dimension
is present, as determined by LLM evaluation (Track 2). Only
sources with 10+ LLM-evaluated projects are shown.

**Metadata coverage bars:** Based on structured database fields
(metadata), not LLM evaluation. Indicates whether certain
artifacts exist in the database for each source.

**Source-specific context:**
- **OSHWA** requires structured metadata submission for
  certification, which guarantees license, description,
  and author fields.
- **Hackaday.io** has mandatory profile fields that inflate
  completeness scores but may not reflect substantive
  documentation.
- **HardwareX (ohx)** projects are peer-reviewed publications
  with high depth scores but often lack GitHub repos.
- **Kitspace** specializes in PCB projects, giving it very high
  BOM and design file rates.
- **OSF/Mendeley** are research data repositories, not project
  platforms -- low scores reflect a category mismatch.
""")
