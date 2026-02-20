"""Scrape project data from Kitspace.org.

Two modes:
- **Full scrape** (requires ``selenium``): infinite-scroll the homepage to
  discover all project URLs, then scrape each page.
- **Lightweight scrape**: fetch the initial page load via ``requests`` + BS4.

Individual project pages are always scraped via ``requests`` + BS4
(no Selenium required for the detail pages).

Install the optional ``[scrape]`` extra for Selenium support::

    pip install osh-datasets[scrape]
"""

import contextlib
import json
import time
from pathlib import Path

import orjson
from bs4 import BeautifulSoup

from osh_datasets.config import get_logger
from osh_datasets.http import build_session
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

KITSPACE_URL = "https://kitspace.org/"


def _scrape_project_page(
    session: object,
    url: str,
) -> dict[str, object]:
    """Scrape a single Kitspace project page.

    Args:
        session: Active requests session.
        url: Full URL to the project page.

    Returns:
        Dict of project metadata.
    """
    import requests

    if not isinstance(session, requests.Session):
        return {"url": url, "error": "invalid_session"}

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"url": url, "error": str(exc)}

    soup = BeautifulSoup(resp.content, "html.parser")

    data: dict[str, object] = {
        "url": url,
        "project_name": None,
        "repository_link": None,
        "description": None,
        "bill_of_materials": [],
        "gerber_file_link": None,
    }

    # Try __NEXT_DATA__ JSON blob first
    from bs4 import Tag

    next_data: dict[str, object] | None = None
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if isinstance(script, Tag) and script.string:
        with contextlib.suppress(json.JSONDecodeError):
            next_data = json.loads(script.string)

    # Title
    title_el = soup.find("div", {"data-cy": "project-title"})
    if isinstance(title_el, Tag):
        data["project_name"] = title_el.get_text(strip=True)
    elif next_data:
        props = _deep_get(next_data, "props", "pageProps")
        if isinstance(props, dict):
            data["project_name"] = props.get("projectName")

    # Description
    desc_meta = soup.find("meta", {"name": "description"})
    if isinstance(desc_meta, Tag):
        data["description"] = desc_meta.get("content")

    # Repository link
    gh_el = soup.find("div", {"data-cy": "original-url"})
    if isinstance(gh_el, Tag):
        a = gh_el.find("a")
        if isinstance(a, Tag):
            href = str(a.get("href", ""))
            hosts = ("github.com", "gitlab.com", "bitbucket.org")
            if any(h in href for h in hosts):
                data["repository_link"] = href

    if not data["repository_link"] and next_data:
        for key_path in (
            ("props", "pageProps", "repo"),
            ("props", "pageProps", "singleProject", "repo"),
        ):
            repo = _deep_get(next_data, *key_path)
            if isinstance(repo, dict):
                orig = repo.get("original_url", "")
                if isinstance(orig, str) and "github.com" in orig:
                    data["repository_link"] = orig
                    break

    # BOM
    if next_data:
        bom_info = _deep_get(
            next_data, "props", "pageProps", "bomInfo"
        ) or _deep_get(
            next_data, "props", "pageProps", "singleProject", "bomInfo"
        )
        if isinstance(bom_info, dict):
            bom_obj = bom_info.get("bom", {})
            if isinstance(bom_obj, dict):
                lines = bom_obj.get("lines", [])
                if isinstance(lines, list):
                    bom: list[dict[str, object]] = []
                    for line in lines:
                        if not isinstance(line, dict):
                            continue
                        item: dict[str, object] = {
                            "reference": line.get("reference", ""),
                            "quantity": line.get("quantity", ""),
                            "description": line.get("description", ""),
                            "retailers": line.get("retailers", {}),
                        }
                        parts = line.get("partNumbers", [])
                        if isinstance(parts, list) and parts:
                            p0 = parts[0] if isinstance(parts[0], dict) else {}
                            item["manufacturer"] = p0.get("manufacturer", "")
                            item["mpn"] = p0.get("part", "")
                        bom.append(item)
                    data["bill_of_materials"] = bom

    # Gerber link
    if next_data:
        zip_url = _deep_get(
            next_data, "props", "pageProps", "zipUrl"
        ) or _deep_get(
            next_data, "props", "pageProps", "singleProject", "zipUrl"
        )
        if zip_url:
            data["gerber_file_link"] = zip_url

    return data


def _deep_get(d: object, *keys: str) -> object:
    """Safely navigate nested dicts."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d


def _discover_urls_lightweight(session: object) -> list[str]:
    """Discover project URLs from the initial page load (no JS)."""
    import requests

    if not isinstance(session, requests.Session):
        return []

    try:
        resp = session.get(KITSPACE_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed to fetch Kitspace homepage")
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    cards = soup.find_all("a", {"data-cy": "project-card"})
    urls: set[str] = set()
    for card in cards:
        href = card.get("href", "")
        if href.startswith("/"):
            urls.add(href)
    return sorted(urls)


def _discover_urls_selenium() -> list[str]:
    """Discover all project URLs using Selenium infinite scroll."""
    try:
        from selenium import webdriver  # type: ignore[import-not-found]
        from selenium.webdriver.chrome.options import Options  # type: ignore[import-not-found]
        from selenium.webdriver.common.by import By  # type: ignore[import-not-found]
        from selenium.webdriver.support import expected_conditions as EC  # type: ignore[import-not-found]
        from selenium.webdriver.support.ui import WebDriverWait  # type: ignore[import-not-found]
    except ImportError:
        logger.error(
            "Selenium not installed. Install with: "
            "pip install osh-datasets[scrape]"
        )
        return []

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)

    try:
        driver.get(KITSPACE_URL)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-cy="cards-grid"]')
            )
        )

        last_count = 0
        no_change = 0
        for _ in range(100):
            cards = driver.find_elements(By.CSS_SELECTOR, '[data-cy="project-card"]')
            count = len(cards)
            if count == last_count:
                no_change += 1
                if no_change >= 3:
                    break
            else:
                no_change = 0
                last_count = count
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        urls: set[str] = set()
        for card in driver.find_elements(By.CSS_SELECTOR, '[data-cy="project-card"]'):
            href = card.get_attribute("href") or ""
            if "kitspace.org" in href:
                path = href.split("kitspace.org")[-1]
                if path.startswith("/"):
                    urls.add(path)
        return sorted(urls)
    finally:
        driver.quit()


class KitspaceScraper(BaseScraper):
    """Scrape Kitspace.org project metadata.

    Output: ``data/raw/kitspace/kitspace_projects.json``
    """

    source_name = "kitspace"

    def scrape(self, use_selenium: bool = False) -> Path:
        """Discover projects and scrape each page.

        Args:
            use_selenium: If True, use Selenium for full infinite-scroll
                discovery. Otherwise, use lightweight requests-only discovery.

        Returns:
            Path to the output JSON file.
        """
        if use_selenium:
            paths = _discover_urls_selenium()
        else:
            session = build_session()
            session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; OSH-Datasets/1.0)"
                    )
                }
            )
            paths = _discover_urls_lightweight(session)

        logger.info("Discovered %d project paths", len(paths))

        # Also check for a saved URL list
        url_file = self.output_dir / "project_urls.json"
        if not paths and url_file.exists():
            saved = orjson.loads(url_file.read_bytes())
            if isinstance(saved, dict):
                paths = [
                    p.get("url", "") for p in saved.get("projects", [])
                ]
            elif isinstance(saved, list):
                paths = saved

        session = build_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; OSH-Datasets/1.0)"
                )
            }
        )

        results: list[dict[str, object]] = []
        for i, path in enumerate(paths):
            full_url = f"https://kitspace.org{path}" if path.startswith("/") else path
            logger.info("[%d/%d] Scraping %s", i + 1, len(paths), full_url)
            data = _scrape_project_page(session, full_url)
            results.append(data)
            if i < len(paths) - 1:
                time.sleep(2.0)

        logger.info("Scraped %d projects", len(results))

        out = self.output_dir / "kitspace_projects.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out
