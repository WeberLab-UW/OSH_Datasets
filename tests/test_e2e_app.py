"""End-to-end Playwright tests for the Streamlit web interface.

Starts a Streamlit server as a subprocess, runs browser-based tests
against it, then shuts it down.
"""

import subprocess
import time
from collections.abc import Generator

import pytest
from playwright.sync_api import Page, expect, sync_playwright

APP_URL = "http://localhost:8502"
STARTUP_TIMEOUT = 30


@pytest.fixture(scope="module")
def streamlit_server() -> Generator[subprocess.Popen[bytes], None, None]:
    """Start Streamlit server for the test session.

    Yields:
        The server subprocess handle.
    """
    proc = subprocess.Popen(
        [
            "uv", "run", "streamlit", "run", "app/Home.py",
            "--server.headless=true",
            "--server.port=8502",
            "--browser.gatherUsageStats=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    import urllib.request
    start = time.time()
    while time.time() - start < STARTUP_TIMEOUT:
        try:
            urllib.request.urlopen(APP_URL, timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.kill()
        raise RuntimeError(
            f"Streamlit server did not start within"
            f" {STARTUP_TIMEOUT}s"
        )

    yield proc

    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser_page(
    streamlit_server: subprocess.Popen[bytes],
) -> Generator[Page, None, None]:
    """Create a Playwright browser page.

    Args:
        streamlit_server: The running Streamlit server.

    Yields:
        A Playwright Page connected to the server.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


class TestHomePage:
    """Tests for the Home page."""

    def test_title_visible(self, browser_page: Page) -> None:
        """Home page displays the main title."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        expect(
            browser_page.get_by_text("OSH Datasets Explorer"),
        ).to_be_visible(timeout=15000)

    def test_metric_cards(self, browser_page: Page) -> None:
        """Home page shows the 4 summary metric cards."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        # Check for key metric labels
        expect(
            browser_page.get_by_text("Total Projects"),
        ).to_be_visible(timeout=15000)
        expect(
            browser_page.get_by_text("Data Sources"),
        ).to_be_visible(timeout=10000)
        expect(
            browser_page.get_by_text("BOM Components"),
        ).to_be_visible(timeout=10000)
        expect(
            browser_page.get_by_text("LLM Evaluations"),
        ).to_be_visible(timeout=10000)

    def test_metric_values_nonzero(
        self, browser_page: Page,
    ) -> None:
        """Metric cards display non-zero values."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        # "10,698" should appear as the total projects count
        expect(
            browser_page.get_by_text("10,698"),
        ).to_be_visible(timeout=15000)

    def test_source_chart_rendered(
        self, browser_page: Page,
    ) -> None:
        """Projects by Source chart is rendered."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        expect(
            browser_page.get_by_text("Projects by Source"),
        ).to_be_visible(timeout=15000)
        # Plotly charts render as SVG within iframes or divs
        # Check that at least one plotly container exists
        browser_page.wait_for_selector(
            ".stPlotlyChart", timeout=15000,
        )

    def test_about_expander(self, browser_page: Page) -> None:
        """About this dataset expander works."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        expander = browser_page.get_by_text("About this dataset")
        expect(expander).to_be_visible(timeout=15000)
        expander.click()
        expect(
            browser_page.get_by_text("Two-track documentation"),
        ).to_be_visible(timeout=5000)

    def test_source_table_rendered(
        self, browser_page: Page,
    ) -> None:
        """Source Summary table is rendered with data."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        expect(
            browser_page.get_by_text("Source Summary"),
        ).to_be_visible(timeout=15000)
        # Table should contain known source names
        expect(
            browser_page.get_by_text("hackaday").first,
        ).to_be_visible(timeout=10000)

    def test_navigation_sidebar(
        self, browser_page: Page,
    ) -> None:
        """Sidebar navigation links exist."""
        browser_page.goto(APP_URL, wait_until="networkidle")
        # Streamlit multi-page apps show page names in sidebar
        expect(
            browser_page.get_by_role(
                "link", name="Browse Projects",
            ),
        ).to_be_visible(timeout=15000)


class TestBrowseProjectsPage:
    """Tests for the Browse Projects page."""

    def test_page_loads(self, browser_page: Page) -> None:
        """Browse Projects page loads successfully."""
        browser_page.goto(
            f"{APP_URL}/Browse_Projects",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text("Browse Projects").first,
        ).to_be_visible(timeout=15000)

    def test_results_count_shown(
        self, browser_page: Page,
    ) -> None:
        """Results count is displayed."""
        browser_page.goto(
            f"{APP_URL}/Browse_Projects",
            wait_until="networkidle",
        )
        # Should show "Showing 1-50 of 10,698 projects"
        expect(
            browser_page.get_by_text("Showing 1-50"),
        ).to_be_visible(timeout=15000)

    def test_dataframe_rendered(
        self, browser_page: Page,
    ) -> None:
        """Project table is rendered with data."""
        browser_page.goto(
            f"{APP_URL}/Browse_Projects",
            wait_until="networkidle",
        )
        # Streamlit dataframes render in a specific container
        browser_page.wait_for_selector(
            "[data-testid='stDataFrame']", timeout=15000,
        )

    def test_pagination_controls(
        self, browser_page: Page,
    ) -> None:
        """Pagination buttons are present."""
        browser_page.goto(
            f"{APP_URL}/Browse_Projects",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_role("button", name="Previous"),
        ).to_be_visible(timeout=15000)
        expect(
            browser_page.get_by_role("button", name="Next"),
        ).to_be_visible(timeout=10000)

    def test_sidebar_filters_present(
        self, browser_page: Page,
    ) -> None:
        """Sidebar filter controls exist."""
        browser_page.goto(
            f"{APP_URL}/Browse_Projects",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text("Filters").first,
        ).to_be_visible(timeout=15000)


class TestScoreDistributionsPage:
    """Tests for the Score Distributions page."""

    def test_page_loads(self, browser_page: Page) -> None:
        """Score Distributions page loads."""
        browser_page.goto(
            f"{APP_URL}/Score_Distributions",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text(
                "Score Distributions",
            ).first,
        ).to_be_visible(timeout=15000)

    def test_track1_tab_content(
        self, browser_page: Page,
    ) -> None:
        """Track 1 tab shows histograms."""
        browser_page.goto(
            f"{APP_URL}/Score_Distributions",
            wait_until="networkidle",
        )
        # Track 1 tab should be visible by default
        expect(
            browser_page.get_by_text("Score Distributions").nth(1),
        ).to_be_visible(timeout=15000)
        # Check for plotly charts
        browser_page.wait_for_selector(
            ".stPlotlyChart", timeout=15000,
        )

    def test_track2_tab_exists(
        self, browser_page: Page,
    ) -> None:
        """Track 2 tab is accessible."""
        browser_page.goto(
            f"{APP_URL}/Score_Distributions",
            wait_until="networkidle",
        )
        tab = browser_page.get_by_role(
            "tab", name="Track 2: LLM Evaluation",
        )
        expect(tab).to_be_visible(timeout=15000)

    def test_track2_tab_content(
        self, browser_page: Page,
    ) -> None:
        """Track 2 tab renders content when clicked."""
        browser_page.goto(
            f"{APP_URL}/Score_Distributions",
            wait_until="networkidle",
        )
        tab = browser_page.get_by_role(
            "tab", name="Track 2: LLM Evaluation",
        )
        tab.click()
        expect(
            browser_page.get_by_text(
                "Documentation Dimension Presence Rates",
            ),
        ).to_be_visible(timeout=15000)

    def test_method_expander(
        self, browser_page: Page,
    ) -> None:
        """Track 1 method expander is present."""
        browser_page.goto(
            f"{APP_URL}/Score_Distributions",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text(
                "How Track 1 scores are computed",
            ),
        ).to_be_visible(timeout=15000)


class TestCompareSourcesPage:
    """Tests for the Compare Sources page."""

    def test_page_loads(self, browser_page: Page) -> None:
        """Compare Sources page loads."""
        browser_page.goto(
            f"{APP_URL}/Compare_Sources",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text("Compare Sources").first,
        ).to_be_visible(timeout=15000)

    def test_overview_table_rendered(
        self, browser_page: Page,
    ) -> None:
        """Source overview table is rendered."""
        browser_page.goto(
            f"{APP_URL}/Compare_Sources",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text("Source Overview"),
        ).to_be_visible(timeout=15000)

    def test_radar_chart_rendered(
        self, browser_page: Page,
    ) -> None:
        """Radar chart section is visible."""
        browser_page.goto(
            f"{APP_URL}/Compare_Sources",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text("Track 1 Score Profiles"),
        ).to_be_visible(timeout=15000)
        browser_page.wait_for_selector(
            ".stPlotlyChart", timeout=15000,
        )

    def test_gap_analysis_heatmap(
        self, browser_page: Page,
    ) -> None:
        """Documentation gap heatmap is rendered."""
        browser_page.goto(
            f"{APP_URL}/Compare_Sources",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text(
                "Documentation Gap Analysis",
            ),
        ).to_be_visible(timeout=15000)

    def test_interpretation_expander(
        self, browser_page: Page,
    ) -> None:
        """Gap analysis expander works."""
        browser_page.goto(
            f"{APP_URL}/Compare_Sources",
            wait_until="networkidle",
        )
        expander = browser_page.get_by_text(
            "Interpreting the gap analysis",
        )
        expect(expander).to_be_visible(timeout=15000)
        expander.click()
        expect(
            browser_page.get_by_text("OSHWA").nth(0),
        ).to_be_visible(timeout=5000)


class TestProjectDetailPage:
    """Tests for the Project Detail page."""

    def test_page_loads_with_id(
        self, browser_page: Page,
    ) -> None:
        """Project detail loads when given a project_id."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail?project_id=1",
            wait_until="networkidle",
        )
        # Should show project name, not the selector prompt
        browser_page.wait_for_timeout(3000)
        # The page should not show the "Enter a project name"
        # info message since we provided an ID
        page_text = browser_page.text_content("body")
        assert page_text is not None
        # Should have loaded some project data
        assert "Scores" in page_text or "Repository" in page_text

    def test_search_box_present(
        self, browser_page: Page,
    ) -> None:
        """Search box is present on the detail page."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail",
            wait_until="networkidle",
        )
        expect(
            browser_page.get_by_text(
                "Search for a project by name",
            ),
        ).to_be_visible(timeout=15000)

    def test_tabs_visible_with_project(
        self, browser_page: Page,
    ) -> None:
        """All 5 tabs are visible when a project is loaded."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail?project_id=1",
            wait_until="networkidle",
        )
        browser_page.wait_for_timeout(3000)
        for tab_name in [
            "Scores",
            "Repository",
            "BOM Components",
            "Licenses & Tags",
            "Contributors & Publications",
        ]:
            expect(
                browser_page.get_by_role("tab", name=tab_name),
            ).to_be_visible(timeout=10000)

    def test_gauge_charts_render(
        self, browser_page: Page,
    ) -> None:
        """Track 1 gauge charts render on the Scores tab."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail?project_id=1",
            wait_until="networkidle",
        )
        browser_page.wait_for_timeout(3000)
        # Should have plotly charts (gauges) on the scores tab
        charts = browser_page.query_selector_all(
            ".stPlotlyChart",
        )
        assert len(charts) >= 1, "Expected at least 1 gauge chart"

    def test_score_methodology_expander(
        self, browser_page: Page,
    ) -> None:
        """Score methodology expander is present."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail?project_id=1",
            wait_until="networkidle",
        )
        browser_page.wait_for_timeout(3000)
        expect(
            browser_page.get_by_text("Score methodology"),
        ).to_be_visible(timeout=10000)

    def test_invalid_project_id(
        self, browser_page: Page,
    ) -> None:
        """Invalid project ID shows error message."""
        browser_page.goto(
            f"{APP_URL}/Project_Detail?project_id=999999",
            wait_until="networkidle",
        )
        browser_page.wait_for_timeout(3000)
        expect(
            browser_page.get_by_text("not found"),
        ).to_be_visible(timeout=10000)
