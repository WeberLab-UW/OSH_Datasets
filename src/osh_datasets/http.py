"""Shared HTTP client with retry logic and rate limiting."""

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from osh_datasets.config import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT: float = 30.0


def build_session(
    retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Session:
    """Create a ``requests.Session`` with automatic retry and backoff.

    Args:
        retries: Maximum number of retries per request.
        backoff_factor: Multiplier for exponential backoff between retries.
        status_forcelist: HTTP status codes that trigger a retry.

    Returns:
        A configured ``requests.Session``.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=["GET", "HEAD", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def rate_limited_get(
    session: requests.Session,
    url: str,
    delay: float = 0.5,
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> requests.Response:
    """Perform a GET request followed by a rate-limit delay.

    Args:
        session: An active ``requests.Session``.
        url: The URL to request.
        delay: Seconds to sleep after the request completes.
        timeout: Request timeout in seconds.
        **kwargs: Forwarded to ``session.get``.

    Returns:
        The ``requests.Response``.

    Raises:
        requests.HTTPError: On 4xx/5xx responses.
    """
    response = session.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()
    time.sleep(delay)
    return response
