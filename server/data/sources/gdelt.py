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

from server.data.week_utils import week_to_dates

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_DELAY = 1.5  # Be conservative — rate limits undocumented


def fetch_news_count(person_name: str, start_date: str, end_date: str) -> int:
    """
    Count news articles mentioning a person in a date range.

    Uses GDELT DOC 2.0 API timeline mode to get article counts.

    Args:
        person_name: The person's name as it appears in news.
        start_date: Start date (YYYYMMDD format).
        end_date: End date (YYYYMMDD format).

    Returns:
        Total number of articles found. Returns 0 on error.
    """
    params = {
        "query": f'"{person_name}"',
        "mode": "timelinevol",
        "startdatetime": f"{start_date}000000",
        "enddatetime": f"{end_date}235959",
        "format": "json",
    }

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
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

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("GDELT API error for %s: %s", person_name, e)
        return 0


def weekly_news_count(person_name: str, week: str) -> int:
    """
    Count news articles mentioning a person in a given ISO week.

    Args:
        person_name: The person's name.
        week: ISO week string (e.g. "2026-W04").

    Returns:
        Total article count for that week.
    """
    monday, sunday = week_to_dates(week)
    start = monday.strftime("%Y%m%d")
    end = sunday.strftime("%Y%m%d")
    return fetch_news_count(person_name, start, end)
