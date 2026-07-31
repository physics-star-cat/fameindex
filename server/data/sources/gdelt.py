"""
GDELT news data source.

The GDELT DOC 2.0 API provides free access to a real-time index of
worldwide news coverage. We use it to count how many news articles
mention a person in a given time period.

API: https://blog.gdeltproject.org/gdelt-doc-2-0-api-unveiled/
Rate limits: Undocumented, but gentle usage (<1 req/s) works fine.
"""

import logging
import time
from urllib.parse import quote

import requests

from server.data.week_utils import period_to_dates

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT's rate limit is undocumented but empirically around one request per
# five seconds. At 1.5s a 121-person backfill triggered near-continuous 429s and
# spent most of its time in exponential backoff. Pacing up front is far faster
# overall than retrying after the fact.
REQUEST_DELAY = 5.0


# Circuit breaker. When GDELT blocks an IP it stays blocked for a while, and a
# 121-person backfill would then spend ~2 minutes per person in backoff before
# failing anyway — four hours of sleeping to collect nothing. After this many
# consecutive failures we stop asking for the rest of the run and let the
# scoring engine re-normalise over the signals we did get.
_CONSECUTIVE_FAILURES = 0
_CIRCUIT_OPEN_AFTER = 5


class GdeltUnavailable(requests.exceptions.RequestException):
    """Raised once the circuit is open, without making a request."""


def reset_circuit() -> None:
    """Close the circuit again — call between runs or in tests."""
    global _CONSECUTIVE_FAILURES
    _CONSECUTIVE_FAILURES = 0


def _get_with_retry(params: dict, attempts: int = 4):
    """
    GET with exponential backoff on 429 and 5xx.

    GDELT rate-limits without documenting the limit, and a backfill issues one
    request per person per period. Backing off and retrying keeps the run intact
    where a single attempt would drop signals for whoever hit the limit.
    Raises if every attempt fails, so the caller records an error rather than a
    fabricated zero.
    """
    global _CONSECUTIVE_FAILURES
    if _CONSECUTIVE_FAILURES >= _CIRCUIT_OPEN_AFTER:
        raise GdeltUnavailable(
            f"GDELT circuit open after {_CONSECUTIVE_FAILURES} consecutive failures")

    delay = REQUEST_DELAY
    last_error = None
    for attempt in range(attempts):
        time.sleep(delay)
        try:
            resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = requests.exceptions.HTTPError(
                    f"{resp.status_code} from GDELT", response=resp)
                delay = min(delay * 3, 60)
                logger.warning("GDELT %s, backing off %.1fs (attempt %d/%d)",
                               resp.status_code, delay, attempt + 1, attempts)
                continue
            resp.raise_for_status()
            _CONSECUTIVE_FAILURES = 0
            return resp
        except requests.exceptions.RequestException as e:
            last_error = e
            delay = min(delay * 3, 60)
    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES == _CIRCUIT_OPEN_AFTER:
        logger.error("GDELT unreachable %d times in a row — skipping it for the "
                     "rest of this run", _CONSECUTIVE_FAILURES)
    raise last_error


def fetch_news_count(person_name: str, start_date: str, end_date: str) -> int:
    """
    Count news articles mentioning a person in a date range.

    Uses GDELT DOC 2.0 API timeline mode to get article counts.

    Args:
        person_name: The person's name as it appears in news.
        start_date: Start date (YYYYMMDD format).
        end_date: End date (YYYYMMDD format).

    Returns:
        Total number of articles found.

    Raises:
        requests.exceptions.RequestException: if the API could not be reached or
            returned an error status, after retries.

    This used to return 0 on any failure, which conflated "nobody wrote about
    this person" with "we could not ask". GDELT rate-limits aggressively — a
    backfill of 121 people throttles constantly — so that silently zeroed the
    news dimension for whoever happened to be unlucky, and a false zero is far
    worse than a missing signal: the pipeline stores it as fact, and rankings
    move because of it. The scoring engine re-normalises over whichever signals
    are present, so a raised error costs accuracy far less than a fabricated 0.
    """
    params = {
        "query": f'"{person_name}"',
        "mode": "timelinevol",
        "startdatetime": f"{start_date}000000",
        "enddatetime": f"{end_date}235959",
        "format": "json",
    }

    try:
        resp = _get_with_retry(params)
        resp.raise_for_status()
        data = resp.json()

        timeline = data.get("timeline", [])
        if not timeline:
            return 0

        # Sum all data points in the timeline
        total = 0
        for series in timeline:
            for point in series.get("data", []):
                total += point.get("value", 0)

        return total

    except ValueError as e:
        # Malformed JSON body — the request succeeded but the payload is junk.
        logger.error("GDELT returned unparseable JSON for %s: %s", person_name, e)
        raise requests.exceptions.RequestException(f"unparseable GDELT response: {e}") from e


def weekly_news_count(person_name: str, week: str) -> int:
    """
    Count news articles mentioning a person in a given ISO week.

    Args:
        person_name: The person's name.
        week: ISO week string (e.g. "2026-W04").

    Returns:
        Total article count for that week.
    """
    monday, sunday = period_to_dates(week)
    start = monday.strftime("%Y%m%d")
    end = sunday.strftime("%Y%m%d")
    return fetch_news_count(person_name, start, end)
