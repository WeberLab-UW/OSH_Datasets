"""Browse Projects -- paginated, sortable, filterable table."""

import streamlit as st
from db_utils import (
    get_distinct_sources,
    get_project_count,
    get_projects_page,
)

st.set_page_config(
    page_title="Browse Projects - OSH Datasets",
    layout="wide",
)

st.title("Browse Projects")

PAGE_SIZE = 50

# ---- Sidebar filters ----
with st.sidebar:
    st.header("Filters")

    all_sources = get_distinct_sources()
    selected_sources = st.multiselect(
        "Source",
        options=all_sources,
        default=[],
        help="Filter by data source platform.",
    )

    search_text = st.text_input(
        "Search",
        value="",
        help="Search in project name, description, and author.",
    )

    has_repo = st.checkbox(
        "Has repository URL",
        value=False,
        help="Only show projects with a linked repository.",
    )

    has_bom = st.checkbox(
        "Has BOM data",
        value=False,
        help="Only show projects with bill of materials.",
    )

    st.divider()

    sort_col = st.selectbox(
        "Sort by",
        options=[
            "name",
            "source",
            "completeness",
            "coverage",
            "depth",
            "open_o_meter",
            "stars",
        ],
        index=0,
        help="Column to sort the results by.",
    )

    sort_dir = st.radio(
        "Sort direction",
        options=["ASC", "DESC"],
        index=0,
        horizontal=True,
    )

# ---- Pagination state ----
if "browse_page" not in st.session_state:
    st.session_state.browse_page = 1

sources_tuple = tuple(selected_sources) if selected_sources else None

total = get_project_count(
    sources=sources_tuple,
    search=search_text,
    has_repo=has_repo,
    has_bom=has_bom,
)
total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

# Reset page if filters changed
if st.session_state.browse_page > total_pages:
    st.session_state.browse_page = 1

current_page = st.session_state.browse_page
offset = (current_page - 1) * PAGE_SIZE

# ---- Results ----
st.caption(
    f"Showing {offset + 1}-{min(offset + PAGE_SIZE, total)}"
    f" of {total:,} projects"
)

df = get_projects_page(
    sources=sources_tuple,
    search=search_text,
    has_repo=has_repo,
    has_bom=has_bom,
    sort_col=sort_col,
    sort_dir=sort_dir,
    offset=offset,
    limit=PAGE_SIZE,
)

if df.height > 0:
    # Display as interactive dataframe
    event = st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "id": st.column_config.NumberColumn(
                "ID", width="small",
            ),
            "source": st.column_config.TextColumn(
                "Source", width="small",
            ),
            "name": st.column_config.TextColumn(
                "Name", width="large",
            ),
            "author": st.column_config.TextColumn(
                "Author", width="medium",
            ),
            "completeness": st.column_config.ProgressColumn(
                "Completeness",
                min_value=0,
                max_value=100,
                help="Weighted artifact presence (0-100).",
            ),
            "coverage": st.column_config.ProgressColumn(
                "Coverage",
                min_value=0,
                max_value=100,
                help=(
                    "Breadth across 12 documentation"
                    " categories (0-100)."
                ),
            ),
            "depth": st.column_config.ProgressColumn(
                "Depth",
                min_value=0,
                max_value=100,
                help=(
                    "Continuous signals for documentation"
                    " investment (0-100)."
                ),
            ),
            "open_o_meter": st.column_config.NumberColumn(
                "OoM",
                help=(
                    "Open-o-Meter score (0-8) based on"
                    " Bonvoisin & Mies (2018)."
                ),
            ),
            "stars": st.column_config.NumberColumn(
                "Stars",
                help="GitHub stars (if repository exists).",
            ),
        },
    )

    # Handle row selection -> navigate to detail
    if event and event.selection and event.selection.rows:
        row_idx = event.selection.rows[0]
        project_id = int(df["id"][row_idx])
        st.query_params["project_id"] = str(project_id)
        st.switch_page("pages/4_Project_Detail.py")
else:
    st.info("No projects match the current filters.")

# ---- Pagination controls ----
col_prev, col_info, col_next = st.columns([1, 2, 1])

with col_prev:
    if st.button(
        "Previous",
        disabled=current_page <= 1,
        use_container_width=True,
    ):
        st.session_state.browse_page -= 1
        st.rerun()

with col_info:
    st.markdown(
        f"<div style='text-align:center'>"
        f"Page {current_page} of {total_pages}</div>",
        unsafe_allow_html=True,
    )

with col_next:
    if st.button(
        "Next",
        disabled=current_page >= total_pages,
        use_container_width=True,
    ):
        st.session_state.browse_page += 1
        st.rerun()
