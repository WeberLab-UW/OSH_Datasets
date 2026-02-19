"""Scrape project data from OpenHardware.io via web scraping."""

import re
import time
from pathlib import Path
from urllib.parse import urljoin

import orjson
from bs4 import BeautifulSoup

from osh_datasets.config import get_logger
from osh_datasets.http import build_session
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://www.openhardware.io/"


def _extract_number(text: str) -> int | None:
    """Extract the first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.replace(",", ""))
    return int(m.group()) if m else None


def _clean_text(text: str) -> str:
    """Remove null bytes and collapse whitespace."""
    if not text:
        return ""
    cleaned = text.replace("\x00", "").replace("\ufffd", "")
    return " ".join(cleaned.split()).strip()


def _parse_overview(soup: BeautifulSoup) -> dict[str, object]:
    """Parse the overview section for license, dates, links."""
    data: dict[str, object] = {
        "license": None,
        "created": None,
        "updated": None,
        "views": None,
        "github": None,
        "homepage": None,
    }
    from bs4 import Tag

    overview = soup.find("div", class_="overview")
    if not isinstance(overview, Tag):
        return data

    for row in overview.find_all("div", class_="row"):
        left = row.find("div", class_="left")
        right = row.find("div", class_="right")
        if not left or not right:
            continue
        key = left.get_text(strip=True).lower().rstrip(":")
        if "license" in key:
            data["license"] = right.get_text(strip=True)
        elif "created" in key:
            data["created"] = right.get_text(strip=True)
        elif "updated" in key:
            data["updated"] = right.get_text(strip=True)
        elif "views" in key:
            data["views"] = _extract_number(right.get_text(strip=True)) or 0
        elif "github" in key:
            link = right.find("a")
            if link and link.get("href"):
                href = link["href"]
                if href.startswith("/") and not href.startswith("//"):
                    href = f"https://github.com{href}"
                data["github"] = href
        elif "homepage" in key:
            link = right.find("a")
            if link and link.get("href"):
                data["homepage"] = link["href"]
    return data


def _parse_statistics(soup: BeautifulSoup) -> dict[str, int]:
    """Parse engagement statistics (likes, collects, etc.)."""
    stats: dict[str, int] = {
        "likes": 0,
        "collects": 0,
        "comments": 0,
        "downloads": 0,
    }
    for row in soup.find_all("div", class_="actionRow"):
        row_id = row.get("id", "").lower()
        count_el = row.find("span", class_="count")
        if not count_el:
            continue
        count = _extract_number(count_el.get_text(strip=True)) or 0
        row_text = row_id + " " + " ".join(row.get("class", []))
        if "like" in row_text:
            stats["likes"] = count
        elif "collect" in row_text:
            stats["collects"] = count
        elif "comment" in row_text:
            stats["comments"] = count
        elif "download" in row_text:
            stats["downloads"] = count
    return stats


def _parse_design_files(soup: BeautifulSoup) -> list[dict[str, object]]:
    """Parse the design files tab."""
    files: list[dict[str, object]] = []
    from bs4 import Tag

    tab = soup.find("div", id="tabs-design")
    if not isinstance(tab, Tag):
        return files
    table = tab.find("table")
    if not isinstance(table, Tag):
        return files

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 3:
            name_cell = cells[0]
            link = name_cell.find("a")
            if link:
                icon = link.find("i")
                if icon:
                    icon.decompose()
                name = link.get_text(strip=True)
            else:
                name = name_cell.get_text(strip=True)
            size = cells[1].get_text(strip=True)
            downloads = _extract_number(cells[2].get_text(strip=True)) or 0
            if name:
                files.append({"name": name, "size": size, "downloads": downloads})
    return files


class HardwareioScraper(BaseScraper):
    """Scrape project pages from OpenHardware.io.

    Reads project page names from ``data/raw/hardwareio/hardware.txt``.
    Output: ``data/raw/hardwareio/hardwareio_projects.json``
    """

    source_name = "hardwareio"

    def scrape(self) -> Path:
        """Scrape all listed project pages.

        Returns:
            Path to the output JSON file.
        """
        names_file = self.output_dir / "hardware.txt"
        if not names_file.exists():
            logger.warning("No project list at %s, skipping", names_file)
            out = self.output_dir / "hardwareio_projects.json"
            out.write_bytes(orjson.dumps([]))
            return out

        names = [
            line.strip()
            for line in names_file.read_text().splitlines()
            if line.strip()
        ]
        return self.scrape_pages(names)

    def scrape_pages(self, page_names: list[str]) -> Path:
        """Scrape the given project page paths.

        Args:
            page_names: List of page paths (e.g. ``view/32993/Name``).

        Returns:
            Path to the output JSON file.
        """
        session = build_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; OSH-Datasets/1.0; "
                    "+https://github.com/nicweber/OSH_Datasets)"
                )
            }
        )
        results: list[dict[str, object]] = []

        for i, name in enumerate(page_names):
            url = urljoin(BASE_URL, name.lstrip("/"))
            logger.info("[%d/%d] Scraping %s", i + 1, len(page_names), url)

            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, "html.parser")

                data: dict[str, object] = {"project_url": url}

                # Title + author
                from bs4 import Tag as _Tag

                title_el = soup.find("div", class_="title")
                data["project_name"] = (
                    _clean_text(title_el.get_text(strip=True))
                    if isinstance(title_el, _Tag)
                    else None
                )
                creator_el = soup.find("div", class_="creator")
                if isinstance(creator_el, _Tag):
                    author_link = creator_el.find("a")
                    if isinstance(author_link, _Tag):
                        data["project_author"] = author_link.get_text(
                            strip=True
                        ).replace("by ", "")

                data.update(_parse_overview(soup))
                data["statistics"] = _parse_statistics(soup)
                data["design_files"] = _parse_design_files(soup)

                results.append(data)

            except Exception:
                logger.exception("Failed to scrape %s", url)

            if i < len(page_names) - 1:
                time.sleep(2.0)

        logger.info("Scraped %d/%d projects", len(results), len(page_names))

        out = self.output_dir / "hardwareio_projects.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out
