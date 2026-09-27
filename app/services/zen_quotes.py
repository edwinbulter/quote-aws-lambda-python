import logging
import time

import requests
from flask import current_app

logger = logging.getLogger(__name__)

RANDOM_URL = "https://zenquotes.io/api/random"
QUOTES_URL = "https://zenquotes.io/api/quotes"


def _get(url: str) -> list[dict]:
    timeout = current_app.config.get("ZEN_QUOTES_TIMEOUT", 5)
    retries = current_app.config.get("ZEN_QUOTES_RETRIES", 2)

    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5)

    logger.warning("ZenQuotes request to %s failed after retries: %s", url, last_error)
    return []


def fetch_random() -> dict | None:
    """Fetch a single random quote from ZenQuotes. Returns None on any failure."""
    results = _get(RANDOM_URL)
    if not results:
        return None
    return results[0]


def fetch_many() -> list[dict]:
    """Fetch a batch of quotes from ZenQuotes. Returns [] on any failure
    so quote-serving degrades gracefully instead of raising."""
    return _get(QUOTES_URL)
