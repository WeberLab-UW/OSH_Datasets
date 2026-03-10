"""Project Detail -- single-project deep dive with tabbed layout."""

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from db_utils import (
    get_project_bom,
    get_project_contributors,
    get_project_detail,
    get_project_licenses,
    get_project_llm_eval,
    get_project_publications,
    get_project_repo_metrics,
    get_project_scores,
    get_project_tags,
    search_projects,
)

st.set_page_config(
    page_title="Project Detail - OSH Datasets",
    layout="wide",
)

st.title("Project Detail")

# ---- Project selector ----
project_id: int | None = None

# Check query params first
qp_id = st.query_params.get("project_id")
if qp_id and qp_id.isdigit():
    project_id = int(qp_id)

# Search box fallback
search_query = st.text_input(
    "Search for a project by name",
    value="",
    help="Type to search, then select from results below.",
)

if search_query:
    results = search_projects(search_query)
    if results.height > 0:
        options = {
            f"{r['name']} ({r['source']})": r["id"]
            for r in results.iter_rows(named=True)
        }
        selection = st.selectbox(
            "Select project",
            options=list(options.keys()),
        )
        if selection:
            project_id = options[selection]
    else:
        st.caption("No projects found.")

if project_id is None:
    st.info(
        "Enter a project name above or click a row on the"
        " Browse Projects page."
    )
    st.stop()

# ---- Load project data ----
project = get_project_detail(project_id)
if project is None:
    st.error(f"Project ID {project_id} not found.")
    st.stop()

# ---- Header ----
st.header(str(project.get("name", "Untitled")))

col_meta1, col_meta2, col_meta3 = st.columns(3)
with col_meta1:
    st.markdown(
        f"**Source:** {project.get('source', 'Unknown')}",
    )
    st.markdown(f"**Author:** {project.get('author') or 'N/A'}")
with col_meta2:
    st.markdown(
        f"**Category:** {project.get('category') or 'N/A'}",
    )
    st.markdown(
        f"**Country:** {project.get('country') or 'N/A'}",
    )
with col_meta3:
    url = project.get("url")
    repo = project.get("repo_url")
    doc_url = project.get("documentation_url")
    if url:
        st.markdown(f"[Project URL]({url})")
    if repo:
        st.markdown(f"[Repository]({repo})")
    if doc_url:
        st.markdown(f"[Documentation]({doc_url})")

desc = project.get("description")
if desc:
    with st.expander("Description", expanded=False):
        st.write(str(desc)[:2000])

st.divider()

# ---- Tabs ----
tab_scores, tab_repo, tab_bom, tab_lic, tab_contrib = st.tabs([
    "Scores",
    "Repository",
    "BOM Components",
    "Licenses & Tags",
    "Contributors & Publications",
])

# ============================================================
# Tab 1: Scores
# ============================================================
with tab_scores:
    scores = get_project_scores(project_id)
    llm = get_project_llm_eval(project_id)

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.subheader("Track 1: Metadata Scores")
        if scores:
            gauges = [
                (
                    "Completeness",
                    scores.get("completeness_score", 0),
                    100,
                ),
                (
                    "Coverage",
                    scores.get("coverage_score", 0),
                    100,
                ),
                (
                    "Depth",
                    scores.get("depth_score", 0),
                    100,
                ),
                (
                    "Open-o-Meter",
                    scores.get("open_o_meter_score", 0),
                    8,
                ),
            ]
            g1, g2 = st.columns(2)
            g3, g4 = st.columns(2)
            for col_w, (title, val, max_v) in zip(
                [g1, g2, g3, g4], gauges, strict=True,
            ):
                with col_w:
                    fig = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=val,
                        title={"text": title},
                        gauge={
                            "axis": {"range": [0, max_v]},
                            "bar": {"color": "#1f77b4"},
                            "steps": [
                                {
                                    "range": [
                                        0, max_v * 0.33,
                                    ],
                                    "color": "#ffcccc",
                                },
                                {
                                    "range": [
                                        max_v * 0.33,
                                        max_v * 0.66,
                                    ],
                                    "color": "#ffffcc",
                                },
                                {
                                    "range": [
                                        max_v * 0.66,
                                        max_v,
                                    ],
                                    "color": "#ccffcc",
                                },
                            ],
                        },
                    ))
                    fig.update_layout(
                        height=200,
                        margin={
                            "t": 50, "b": 0,
                            "l": 20, "r": 20,
                        },
                    )
                    st.plotly_chart(
                        fig, use_container_width=True,
                    )
        else:
            st.caption("No Track 1 scores available.")

    with col_t2:
        st.subheader("Track 2: LLM Evaluation")
        if llm:
            st.markdown(
                f"**Project Type:** "
                f"{llm.get('project_type', 'N/A')}"
            )
            st.markdown(
                f"**Structure:** "
                f"{llm.get('structure_quality', 'N/A')}"
            )
            st.markdown(
                f"**Maturity:** "
                f"{llm.get('maturity_stage', 'N/A')}"
            )

            dims = [
                ("License", "license_present"),
                ("BOM", "bom_present"),
                ("Assembly", "assembly_present"),
                ("HW Design", "hw_design_present"),
                ("HW Editable Source", "hw_editable_source"),
                ("Mech Design", "mech_design_present"),
                ("Mech Editable Source", "mech_editable_source"),
                ("SW/Firmware", "sw_fw_present"),
                ("Testing", "testing_present"),
                ("Contributing", "contributing_present"),
                ("Cost Mentioned", "cost_mentioned"),
                ("Suppliers", "suppliers_referenced"),
                ("Part Numbers", "part_numbers_present"),
            ]

            check_data = []
            for label, key in dims:
                val = llm.get(key)
                status = (
                    "Yes" if val == 1
                    else "No" if val == 0
                    else "N/A"
                )
                check_data.append({
                    "Dimension": label,
                    "Present": status,
                })

            st.dataframe(
                pl.DataFrame(check_data),
                hide_index=True,
                use_container_width=True,
            )

            # Detail fields
            details = []
            for label, key in [
                ("License Type", "license_type"),
                ("BOM Completeness", "bom_completeness"),
                ("BOM Components", "bom_component_count"),
                ("Assembly Detail", "assembly_detail"),
                ("Assembly Steps", "assembly_step_count"),
                ("SW/FW Type", "sw_fw_type"),
                ("SW/FW Doc Level", "sw_fw_doc_level"),
                ("Testing Detail", "testing_detail"),
                ("Contributing Level", "contributing_level"),
                ("HW License", "hw_license_name"),
                ("SW License", "sw_license_name"),
                ("Doc License", "doc_license_name"),
            ]:
                val = llm.get(key)
                if val is not None and val != "":
                    details.append({
                        "Field": label,
                        "Value": str(val),
                    })

            if details:
                with st.expander("Evaluation details"):
                    st.dataframe(
                        pl.DataFrame(details),
                        hide_index=True,
                        use_container_width=True,
                    )

            st.caption(
                f"Model: {llm.get('model_id', 'N/A')} | "
                f"Prompt: {llm.get('prompt_version', 'N/A')} | "
                f"Evaluated: {llm.get('evaluated_at', 'N/A')}"
            )
        else:
            st.caption(
                "No Track 2 LLM evaluation available"
                " (requires GitHub repository)."
            )

    with st.expander("Score methodology"):
        st.markdown("""
**Track 1** scores are computed from structured database
fields. Completeness measures weighted artifact presence,
Coverage measures breadth across 12 categories, Depth measures
continuous documentation investment signals, and Open-o-Meter
reproduces the Bonvoisin & Mies (2018) 8-point scale.

**Track 2** evaluations are produced by sending the project's
README and file tree to Gemini 2.5 Flash Lite. The LLM
evaluates 12+ documentation dimensions and returns structured
assessments. "Present" means the LLM found evidence of that
documentation type in the repository.
""")

# ============================================================
# Tab 2: Repository Metrics
# ============================================================
with tab_repo:
    metrics = get_project_repo_metrics(project_id)
    if metrics:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Stars",
            metrics.get("stars") or 0,
            help="GitHub star count.",
        )
        m2.metric(
            "Forks",
            metrics.get("forks") or 0,
            help="GitHub fork count.",
        )
        m3.metric(
            "Contributors",
            metrics.get("contributors_count") or 0,
            help="Number of contributors.",
        )
        m4.metric(
            "Releases",
            metrics.get("releases_count") or 0,
            help="Number of GitHub releases.",
        )

        detail_data = [
            ("Community Health", metrics.get("community_health")),
            ("Primary Language", metrics.get("primary_language")),
            ("Open Issues", metrics.get("open_issues")),
            ("Total Issues", metrics.get("total_issues")),
            ("Open PRs", metrics.get("open_prs")),
            ("Closed PRs", metrics.get("closed_prs")),
            ("Branches", metrics.get("branches_count")),
            ("Tags", metrics.get("tags_count")),
            ("Repo Size (KB)", metrics.get("repo_size_kb")),
            ("Total Files", metrics.get("total_files")),
            (
                "Archived",
                "Yes" if metrics.get("archived") else "No",
            ),
            ("Has BOM", "Yes" if metrics.get("has_bom") else "No"),
            (
                "Has README",
                "Yes" if metrics.get("has_readme") else "No",
            ),
            ("Last Pushed", metrics.get("pushed_at")),
        ]
        detail_filtered = [
            {"Field": f, "Value": str(v)}
            for f, v in detail_data
            if v is not None
        ]
        st.dataframe(
            pl.DataFrame(detail_filtered),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No repository metrics available.")

# ============================================================
# Tab 3: BOM Components
# ============================================================
with tab_bom:
    bom = get_project_bom(project_id)
    if bom.height > 0:
        st.caption(f"{bom.height} components")

        # Category breakdown
        cats = (
            bom.filter(pl.col("category").is_not_null())
            .group_by("category")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )
        if cats.height > 0:
            import plotly.express as px

            fig_cat = px.bar(
                cats.to_pandas(),
                x="category",
                y="count",
                text="count",
                color_discrete_sequence=["#1f77b4"],
            )
            fig_cat.update_layout(
                xaxis_title="",
                yaxis_title="Count",
                height=300,
                margin={"t": 10},
            )
            fig_cat.update_traces(textposition="outside")
            st.plotly_chart(fig_cat, use_container_width=True)

        # Component table
        st.dataframe(
            bom,
            hide_index=True,
            use_container_width=True,
            column_config={
                "category": st.column_config.TextColumn(
                    "Category",
                    help=(
                        "Classified via reference designator,"
                        " component name, or footprint."
                    ),
                ),
                "manufacturer": st.column_config.TextColumn(
                    "Manufacturer",
                    help=(
                        "Canonicalized manufacturer name."
                        " Distributors are flagged."
                    ),
                ),
                "footprint": st.column_config.TextColumn(
                    "Footprint",
                    help="Normalized package size code.",
                ),
                "mount": st.column_config.TextColumn(
                    "Mount",
                    help="smd, tht, or other.",
                ),
                "unit_cost": st.column_config.NumberColumn(
                    "Unit Cost",
                    format="$%.4f",
                ),
            },
        )
    else:
        st.caption("No BOM components for this project.")

# ============================================================
# Tab 4: Licenses & Tags
# ============================================================
with tab_lic:
    licenses = get_project_licenses(project_id)
    if licenses.height > 0:
        st.subheader("Licenses")
        st.dataframe(
            licenses,
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No licenses recorded.")

    tags = get_project_tags(project_id)
    if tags:
        st.subheader("Tags")
        st.write(", ".join(tags))
    else:
        st.caption("No tags recorded.")

# ============================================================
# Tab 5: Contributors & Publications
# ============================================================
with tab_contrib:
    contributors = get_project_contributors(project_id)
    if contributors.height > 0:
        st.subheader("Contributors")
        st.dataframe(
            contributors,
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No contributors recorded.")

    pubs = get_project_publications(project_id)
    if pubs.height > 0:
        st.subheader("Publications")
        st.dataframe(
            pubs,
            hide_index=True,
            use_container_width=True,
            column_config={
                "doi": st.column_config.LinkColumn("DOI"),
            },
        )
    else:
        st.caption("No publications recorded.")
