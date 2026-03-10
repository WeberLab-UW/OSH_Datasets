"""Score Distributions -- Track 1 and Track 2 interactive charts."""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from db_utils import (
    get_track1_scores,
    get_track2_binary_rates,
    get_track2_categorical,
)

st.set_page_config(
    page_title="Score Distributions - OSH Datasets",
    layout="wide",
)

st.title("Score Distributions")

tab_t1, tab_t2 = st.tabs(["Track 1: Metadata Scores", "Track 2: LLM Evaluation"])

# ============================================================
# Track 1
# ============================================================
with tab_t1:
    df_t1 = get_track1_scores()
    pdf_t1 = df_t1.to_pandas()

    # ---- Source filter ----
    sources = sorted(df_t1["source"].unique().to_list())
    selected = st.multiselect(
        "Filter by source",
        options=sources,
        default=[],
        key="t1_source_filter",
        help="Leave empty to show all sources.",
    )
    if selected:
        pdf_t1 = pdf_t1[pdf_t1["source"].isin(selected)]

    st.caption(f"N = {len(pdf_t1):,} projects")

    # ---- 2x2 Histogram grid ----
    st.subheader("Score Distributions")
    score_cols = [
        ("completeness_score", "Completeness (0-100)", 100),
        ("coverage_score", "Coverage (0-100)", 100),
        ("depth_score", "Depth (0-100)", 100),
        ("open_o_meter_score", "Open-o-Meter (0-8)", 8),
    ]

    row1_c1, row1_c2 = st.columns(2)
    row2_c1, row2_c2 = st.columns(2)
    cols_layout = [row1_c1, row1_c2, row2_c1, row2_c2]

    for col_widget, (col_name, title, max_val) in zip(
        cols_layout, score_cols, strict=True,
    ):
        with col_widget:
            nbins = 20 if max_val == 100 else 9
            fig = px.histogram(
                pdf_t1,
                x=col_name,
                nbins=nbins,
                title=title,
                color_discrete_sequence=["#1f77b4"],
            )
            median_val = pdf_t1[col_name].median()
            fig.add_vline(
                x=median_val,
                line_dash="dash",
                line_color="red",
                annotation_text=f"median={median_val:.0f}",
                annotation_position="top right",
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title="Count",
                height=300,
                margin={"t": 40, "b": 30},
            )
            st.plotly_chart(fig, use_container_width=True)

    # ---- Correlation heatmap ----
    st.subheader("Score Correlations")
    score_names = [s[0] for s in score_cols]
    corr = pdf_t1[score_names].corr()
    labels = [
        s.replace("_score", "").replace("_", " ").title()
        for s in score_names
    ]
    fig_corr = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=labels,
            y=labels,
            text=corr.values.round(2),
            texttemplate="%{text}",
            colorscale="RdBu_r",
            zmin=-1,
            zmax=1,
        ),
    )
    fig_corr.update_layout(
        height=400,
        margin={"t": 10, "b": 10},
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    # ---- Box plots by source ----
    st.subheader("Scores by Source")
    score_select = st.selectbox(
        "Score metric",
        options=score_names,
        format_func=lambda s: s.replace("_score", "")
        .replace("_", " ")
        .title(),
        key="t1_box_score",
    )
    fig_box = px.box(
        pdf_t1,
        x="source",
        y=score_select,
        color="source",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_box.update_layout(
        showlegend=False,
        xaxis_title="",
        yaxis_title=score_select.replace("_score", "")
        .replace("_", " ")
        .title(),
        height=400,
        margin={"t": 10},
    )
    st.plotly_chart(fig_box, use_container_width=True)

    # ---- Method explanation ----
    with st.expander("How Track 1 scores are computed"):
        st.markdown("""
**Completeness (0-100):** Weighted sum of artifact presence
checks. Weights: BOM=20, license=15, repository=15, README=10,
documentation URL=10, description=10, contributors=10,
author=5, timestamps=3, tags=2.

**Coverage (0-100):** Breadth across 12 documentation
categories: identity, description, license, multi-license,
repository, documentation URL, BOM, contributors, tags,
publication, README, issue tracker. Each present category adds
~8.3 points.

**Depth (0-100):** Mean of non-null continuous signals
measuring documentation investment: repository count,
issue activity, releases, BOM component count, contributor
count, tag count, and description length (normalized).

**Open-o-Meter (0-8):** Reproduction of the Bonvoisin & Mies
(2018) openness metric. One point for each of 8 criteria:
(1) design files published, (2) BOM available, (3) assembly
instructions, (4) editable source format, (5) open license,
(6) version control, (7) contribution guide, (8) issue tracker.
""")

# ============================================================
# Track 2
# ============================================================
with tab_t2:
    df_rates = get_track2_binary_rates()
    df_cat = get_track2_categorical()

    # ---- Binary dimension presence rates ----
    st.subheader("Documentation Dimension Presence Rates")

    binary_dims = [
        "sw_fw_present",
        "hw_design_present",
        "license_present",
        "mech_design_present",
        "bom_present",
        "testing_present",
        "suppliers_referenced",
        "assembly_present",
        "contributing_present",
        "part_numbers_present",
        "cost_mentioned",
    ]
    dim_labels = {
        "sw_fw_present": "Software/Firmware",
        "hw_design_present": "Hardware Design",
        "license_present": "License",
        "mech_design_present": "Mechanical Design",
        "bom_present": "Bill of Materials",
        "testing_present": "Testing",
        "suppliers_referenced": "Suppliers Referenced",
        "assembly_present": "Assembly Instructions",
        "contributing_present": "Contributing Guide",
        "part_numbers_present": "Part Numbers",
        "cost_mentioned": "Cost Information",
    }

    total_t2 = int(df_rates["total"].sum())
    rates = []
    for dim in binary_dims:
        count = int(df_rates[dim].sum())
        rates.append({
            "Dimension": dim_labels[dim],
            "Percentage": round(count / total_t2 * 100, 1),
        })
    rates.sort(key=lambda r: r["Percentage"], reverse=True)

    import polars as pl

    df_bar = pl.DataFrame(rates)
    fig_bar = px.bar(
        df_bar.to_pandas(),
        x="Percentage",
        y="Dimension",
        orientation="h",
        text="Percentage",
        color_discrete_sequence=["#2ca02c"],
    )
    fig_bar.update_layout(
        yaxis={"categoryorder": "total ascending"},
        xaxis_title="% of Projects",
        xaxis_range=[0, 105],
        yaxis_title="",
        height=400,
        margin={"t": 10},
    )
    fig_bar.update_traces(texttemplate="%{text}%", textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)

    st.caption(f"N = {total_t2:,} projects with LLM evaluation")

    # ---- Categorical distributions ----
    st.subheader("Project Classifications")
    pdf_cat = df_cat.to_pandas()

    cat_c1, cat_c2, cat_c3 = st.columns(3)
    for col_widget, col_name, title in zip(
        [cat_c1, cat_c2, cat_c3],
        ["project_type", "structure_quality", "maturity_stage"],
        ["Project Type", "Structure Quality", "Maturity Stage"],
        strict=True,
    ):
        with col_widget:
            vc = (
                pdf_cat[col_name]
                .dropna()
                .value_counts()
                .reset_index()
            )
            vc.columns = [col_name, "count"]
            fig = px.bar(
                vc,
                x=col_name,
                y="count",
                title=title,
                text="count",
                color_discrete_sequence=["#ff7f0e"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title="Count",
                height=300,
                margin={"t": 40, "b": 30},
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    # ---- Source x dimension heatmap ----
    st.subheader("Presence Rates by Source")

    heatmap_data = []
    for row in df_rates.iter_rows(named=True):
        if row["total"] < 10:
            continue
        for dim in binary_dims:
            pct = round(row[dim] / row["total"] * 100, 1)
            heatmap_data.append({
                "Source": row["source"],
                "Dimension": dim_labels[dim],
                "Percentage": pct,
            })

    if heatmap_data:
        df_hm = pl.DataFrame(heatmap_data)
        pdf_hm = df_hm.to_pandas()
        pivot = pdf_hm.pivot(
            index="Source",
            columns="Dimension",
            values="Percentage",
        )
        dim_order = [dim_labels[d] for d in binary_dims]
        pivot = pivot[[c for c in dim_order if c in pivot.columns]]

        fig_hm = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                text=pivot.values.round(0).astype(int),
                texttemplate="%{text}%",
                colorscale="RdYlGn",
                zmin=0,
                zmax=100,
            ),
        )
        fig_hm.update_layout(
            height=350,
            margin={"t": 10, "b": 10},
            xaxis={"tickangle": -45},
        )
        st.plotly_chart(fig_hm, use_container_width=True)

    # ---- Method explanation ----
    with st.expander("How Track 2 evaluations work"):
        st.markdown("""
**Method:** Each project's README content and repository file
tree are sent to Gemini 2.5 Flash Lite via the Batch API. The
LLM evaluates 12 documentation dimensions and returns structured
JSON.

**Dimensions evaluated:**
- **License:** Is an open-source license present? Type
  (explicit, file reference, referenced, implied)?
- **BOM:** Is a bill of materials present? Completeness
  (partial, basic, complete)?
- **Assembly:** Are assembly instructions present? Detail level
  (referenced, basic, detailed)?
- **Hardware/Mechanical Design:** Are design files present?
  Editable source format available?
- **Software/Firmware:** Is code present? Type and
  documentation level?
- **Testing:** Are test procedures documented?
- **Contributing:** Is there a contribution guide?
- **Cost/Suppliers/Part Numbers:** Is procurement information
  available?
- **Maturity Stage:** concept, prototype, production,
  deprecated, or unstated
- **Structure Quality:** poor, basic, well_structured

**Coverage:** 7,024 of 10,698 projects (those with accessible
GitHub repositories).
""")
