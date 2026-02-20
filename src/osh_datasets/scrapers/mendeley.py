"""Scrape dataset metadata from Mendeley Data via OAI-PMH.

Uses the Open Archives Initiative Protocol for Metadata Harvesting (OAI-PMH)
endpoint at ``https://data.mendeley.com/oai`` to fetch Dublin Core metadata
for datasets linked from HardwareX articles.

No authentication is required for the OAI-PMH method.
"""

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import orjson

from osh_datasets.config import get_logger
from osh_datasets.http import build_session, rate_limited_get
from osh_datasets.scrapers.base import BaseScraper

logger = get_logger(__name__)

_OAI_BASE = "https://data.mendeley.com/oai"
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

_DATASET_ID_RE = re.compile(r"data\.mendeley\.com/datasets/([a-zA-Z0-9]+)")
_DOI_RE = re.compile(r"10\.17632/([a-zA-Z0-9]+)")


def _extract_dataset_id(url: str) -> str | None:
    """Extract dataset ID from a Mendeley Data URL or DOI.

    Args:
        url: Mendeley Data URL or DOI string.

    Returns:
        Dataset ID or None.
    """
    m = _DATASET_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _DOI_RE.search(url)
    if m:
        return m.group(1)
    return None


def _parse_dc_record(record: ET.Element) -> dict[str, object]:
    """Parse Dublin Core metadata from an OAI record element.

    Args:
        record: XML element for a single OAI record.

    Returns:
        Dict of metadata fields.
    """
    header = record.find(".//oai:header", _NS)
    identifier = ""
    datestamp = ""
    if header is not None:
        id_el = header.find("oai:identifier", _NS)
        ds_el = header.find("oai:datestamp", _NS)
        identifier = id_el.text if id_el is not None and id_el.text else ""
        datestamp = ds_el.text if ds_el is not None and ds_el.text else ""

    metadata = record.find(".//oai_dc:dc", _NS)
    fields: dict[str, list[str]] = {}
    if metadata is not None:
        for elem in metadata:
            tag = elem.tag.replace("{http://purl.org/dc/elements/1.1/}", "")
            if elem.text:
                fields.setdefault(tag, []).append(elem.text.strip())

    dataset_id = ""
    m = re.search(r"datasets/([a-zA-Z0-9]+)", identifier)
    if m:
        dataset_id = m.group(1)

    doi = ""
    for ident in fields.get("identifier", []):
        if ident.startswith("10."):
            doi = ident
            break

    return {
        "oai_identifier": identifier,
        "dataset_id": dataset_id,
        "datestamp": datestamp,
        "doi": doi,
        "title": "; ".join(fields.get("title", [])),
        "creator": fields.get("creator", []),
        "description": "; ".join(fields.get("description", []))[:1000],
        "subject": fields.get("subject", []),
        "publisher": "; ".join(fields.get("publisher", [])),
        "date": "; ".join(fields.get("date", [])),
        "type": "; ".join(fields.get("type", [])),
        "format": fields.get("format", []),
        "rights": "; ".join(fields.get("rights", [])),
        "mendeley_url": (
            f"https://data.mendeley.com/datasets/{dataset_id}"
            if dataset_id
            else ""
        ),
    }


class MendeleyScraper(BaseScraper):
    """Fetch Mendeley Data metadata for datasets linked from OHX articles.

    Reads dataset URLs/DOIs from ``data/raw/mendeley/urls.txt`` (one per line).
    Uses OAI-PMH to harvest matching records.

    Output: ``data/raw/mendeley/mendeley_datasets.json``
    """

    source_name = "mendeley"

    def scrape(self) -> Path:
        """Harvest Mendeley Data metadata via OAI-PMH.

        Returns:
            Path to the output JSON file.
        """
        url_file = self.output_dir / "urls.txt"
        if not url_file.exists():
            logger.warning("No URL file at %s, skipping", url_file)
            out = self.output_dir / "mendeley_datasets.json"
            out.write_bytes(orjson.dumps([]))
            return out

        raw_urls = [
            line.strip()
            for line in url_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

        # Extract unique dataset IDs we're looking for
        target_ids: set[str] = set()
        for url in raw_urls:
            did = _extract_dataset_id(url)
            if did:
                target_ids.add(did)

        logger.info(
            "Searching OAI-PMH for %d unique dataset IDs", len(target_ids)
        )

        if not target_ids:
            out = self.output_dir / "mendeley_datasets.json"
            out.write_bytes(orjson.dumps([]))
            return out

        results = self._harvest_matching(target_ids)

        logger.info(
            "Found %d/%d datasets via OAI-PMH",
            len(results),
            len(target_ids),
        )

        out = self.output_dir / "mendeley_datasets.json"
        out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
        return out

    def _harvest_matching(
        self,
        target_ids: set[str],
    ) -> list[dict[str, object]]:
        """Harvest OAI-PMH records matching target dataset IDs.

        Args:
            target_ids: Set of Mendeley dataset IDs to find.

        Returns:
            List of parsed metadata dicts for matching records.
        """
        session = build_session()
        remaining = set(target_ids)
        results: list[dict[str, object]] = []
        resumption_token: str | None = None

        while remaining:
            params = "metadataPrefix=oai_dc"
            if resumption_token:
                params = f"resumptionToken={resumption_token}"

            url = f"{_OAI_BASE}?verb=ListRecords&{params}"

            try:
                resp = rate_limited_get(session, url, delay=1.0)
                root = ET.fromstring(resp.content)
            except Exception:
                logger.exception("OAI-PMH request failed")
                break

            # Check for OAI error
            error = root.find(".//oai:error", _NS)
            if error is not None:
                code = error.get("code", "")
                if code == "noRecordsMatch":
                    logger.info("No more records in OAI repository")
                else:
                    logger.warning("OAI error: %s - %s", code, error.text)
                break

            for record in root.findall(".//oai:record", _NS):
                header = record.find(".//oai:header", _NS)
                if header is not None and header.get("status") == "deleted":
                    continue

                parsed = _parse_dc_record(record)
                did = parsed.get("dataset_id", "")
                if isinstance(did, str) and did in remaining:
                    results.append(parsed)
                    remaining.discard(did)
                    logger.info(
                        "Found dataset %s (%d remaining)", did, len(remaining)
                    )

            # Check for resumption token
            rt_el = root.find(".//oai:resumptionToken", _NS)
            if rt_el is not None and rt_el.text:
                resumption_token = rt_el.text
                time.sleep(1.0)
            else:
                break

        return results
