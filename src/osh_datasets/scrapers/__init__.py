"""Scrapers for collecting OSH metadata from external platforms."""

from osh_datasets.scrapers.ebay import EbayScraper
from osh_datasets.scrapers.github import GitHubScraper
from osh_datasets.scrapers.gitlab import GitLabScraper
from osh_datasets.scrapers.hackaday import HackadayScraper
from osh_datasets.scrapers.hardwareio import HardwareioScraper
from osh_datasets.scrapers.kitspace import KitspaceScraper
from osh_datasets.scrapers.mendeley import MendeleyScraper
from osh_datasets.scrapers.nexar import NexarScraper
from osh_datasets.scrapers.ohr import OhrScraper
from osh_datasets.scrapers.ohx import OhxScraper
from osh_datasets.scrapers.openalex import OpenAlexScraper
from osh_datasets.scrapers.osf import OsfScraper
from osh_datasets.scrapers.oshwa import OshwaScraper
from osh_datasets.scrapers.partstable import PartsTableScraper
from osh_datasets.scrapers.plos import PlosScraper

ALL_SCRAPERS = [
    OshwaScraper,
    OhrScraper,
    HackadayScraper,
    KitspaceScraper,
    HardwareioScraper,
    OhxScraper,
    MendeleyScraper,
    OsfScraper,
    PlosScraper,
    OpenAlexScraper,
    GitHubScraper,
    GitLabScraper,
    NexarScraper,
    PartsTableScraper,
    EbayScraper,
]

__all__ = [
    "ALL_SCRAPERS",
    "EbayScraper",
    "GitHubScraper",
    "GitLabScraper",
    "HackadayScraper",
    "HardwareioScraper",
    "KitspaceScraper",
    "MendeleyScraper",
    "NexarScraper",
    "OhrScraper",
    "PartsTableScraper",
    "OhxScraper",
    "OpenAlexScraper",
    "OsfScraper",
    "OshwaScraper",
    "PlosScraper",
]
