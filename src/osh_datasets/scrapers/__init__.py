"""Scrapers for collecting OSH metadata from external platforms."""

from osh_datasets.scrapers.github import GitHubScraper
from osh_datasets.scrapers.gitlab import GitLabScraper
from osh_datasets.scrapers.hackaday import HackadayScraper
from osh_datasets.scrapers.hardwareio import HardwareioScraper
from osh_datasets.scrapers.kitspace import KitspaceScraper
from osh_datasets.scrapers.ohr import OhrScraper
from osh_datasets.scrapers.ohx import OhxScraper
from osh_datasets.scrapers.openalex import OpenAlexScraper
from osh_datasets.scrapers.osf import OsfScraper
from osh_datasets.scrapers.oshwa import OshwaScraper
from osh_datasets.scrapers.plos import PlosScraper

ALL_SCRAPERS = [
    OshwaScraper,
    OhrScraper,
    HackadayScraper,
    KitspaceScraper,
    HardwareioScraper,
    OhxScraper,
    OsfScraper,
    PlosScraper,
    OpenAlexScraper,
    GitHubScraper,
    GitLabScraper,
]

__all__ = [
    "ALL_SCRAPERS",
    "GitHubScraper",
    "GitLabScraper",
    "HackadayScraper",
    "HardwareioScraper",
    "KitspaceScraper",
    "OhrScraper",
    "OhxScraper",
    "OpenAlexScraper",
    "OsfScraper",
    "OshwaScraper",
    "PlosScraper",
]
