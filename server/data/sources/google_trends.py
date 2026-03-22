"""
Google Trends data source.

Fetches search interest data via the pytrends library. Google Trends
provides a normalised 0-100 measure of search interest relative to
peak popularity in the given time range.

Note: pytrends is an unofficial library that scrapes Google Trends.
It can be rate-limited or break if Google changes their interface.
All calls include retry logic and graceful degradation.
"""

import logging
import time

from pytrends.request import TrendReq

from server.data.week_utils import week_to_dates

logger = logging.getLogger(__name__)

# Delay between requests to avoid rate limiting
REQUEST_DELAY = 2.0  # seconds — Google Trends is aggressive with rate limits


def _get_client() -> TrendReq:
    """Create a pytrends client with sensible defaults."""
    return TrendReq(hl="en-US", tz=0, timeout=(10, 30))


def fetch_interest(person_name: str, timeframe: str = "now 7-d") -> dict:
    """
    Fetch Google Trends interest data for a person.

    Args:
        person_name: Search term (person's name).
        timeframe: Google Trends timeframe string.
            Examples: "now 7-d", "today 1-m", "2026-01-01 2026-01-24"

    Returns:
        Dict with keys:
        - "interest_over_time": list of (date_str, value) tuples
        - "peak_value": int (always 100 — it's the reference point)
        - "average": float (mean interest over the period)
        Returns dict with zero values on error.
    """
    empty = {"interest_over_time": [], "peak_value": 0, "average": 0.0}

    try:
        time.sleep(REQUEST_DELAY)
        pytrends = _get_client()
        pytrends.build_payload([person_name], timeframe=timeframe)
        df = pytrends.interest_over_time()

        if df.empty or person_name not in df.columns:
            logger.warning("No Google Trends data for: %s", person_name)
            return empty

        values = df[person_name].tolist()
        dates = [d.strftime("%Y-%m-%d") for d in df.index]

        return {
            "interest_over_time": list(zip(dates, values)),
            "peak_value": max(values) if values else 0,
            "average": sum(values) / len(values) if values else 0.0,
        }

    except Exception as e:
        logger.error("Google Trends error for %s: %s", person_name, e)
        return empty


def fetch_interest_for_week(person_name: str, week: str) -> float:
    """
    Get the average Google Trends interest for a person in a specific week.

    Converts the ISO week to a date range and queries Google Trends.

    Args:
        person_name: Search term (person's name).
        week: ISO week string (e.g. "2026-W04").

    Returns:
        Average interest value (0-100) for that week. Returns 0.0 on error.
    """
    monday, sunday = week_to_dates(week)
    timeframe = f"{monday.isoformat()} {sunday.isoformat()}"

    result = fetch_interest(person_name, timeframe=timeframe)
    return result["average"]


def compare_interest(names: list[str], timeframe: str = "now 7-d") -> dict[str, float]:
    """
    Compare search interest across multiple persons.

    Google Trends allows up to 5 terms in a single comparison. This
    function handles batching for larger lists.

    Args:
        names: List of person names to compare.
        timeframe: Google Trends timeframe string.

    Returns:
        Dict mapping each name to its relative interest score (0-100).
    """
    results = {}
    batch_size = 5  # Google Trends limit

    for i in range(0, len(names), batch_size):
        batch = names[i:i + batch_size]

        try:
            time.sleep(REQUEST_DELAY)
            pytrends = _get_client()
            pytrends.build_payload(batch, timeframe=timeframe)
            df = pytrends.interest_over_time()

            if df.empty:
                for name in batch:
                    results[name] = 0.0
                continue

            for name in batch:
                if name in df.columns:
                    results[name] = float(df[name].mean())
                else:
                    results[name] = 0.0

        except Exception as e:
            logger.error("Google Trends comparison error: %s", e)
            for name in batch:
                results[name] = 0.0

    return results
