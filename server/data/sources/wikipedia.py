"""
Wikipedia pageviews data source.

Fetches daily pageview counts for tracked persons from the Wikimedia
Pageviews API. Wikipedia pageviews are a strong proxy for general public
interest — when someone is in the news, their Wikipedia page gets traffic.

API: https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
Rate limits: 100 req/s for identified user agents.
"""

import logging
import time

import requests

from server.config import WIKIPEDIA_USER_AGENT
from server.data.week_utils import week_to_dates, format_yyyymmdd

logger = logging.getLogger(__name__)

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
HEADERS = {"User-Agent": WIKIPEDIA_USER_AGENT}

# Be polite — pause between requests
REQUEST_DELAY = 0.1  # seconds


def fetch_pageviews(person_name: str, start_date: str, end_date: str) -> list[dict]:
    """
    Fetch daily Wikipedia pageviews for a person over a date range.

    Args:
        person_name: The person's Wikipedia article title (e.g. "Taylor_Swift").
        start_date: Start date (YYYYMMDD format).
        end_date: End date (YYYYMMDD format).

    Returns:
        List of dicts with keys "date" and "views".
        Returns empty list on error.
    """
    # Wikipedia article titles use underscores for spaces
    article = person_name.replace(" ", "_")

    url = (
        f"{BASE_URL}/en.wikipedia/all-access/all-agents"
        f"/{article}/daily/{start_date}/{end_date}"
    )

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        return [
            {"date": item["timestamp"][:8], "views": item["views"]}
            for item in items
        ]

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning("No Wikipedia article found for: %s", person_name)
        else:
            logger.error("Wikipedia API HTTP error for %s: %s", person_name, e)
        return []

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Wikipedia API error for %s: %s", person_name, e)
        return []


def weekly_aggregate(person_name: str, week: str) -> int:
    """
    Get total pageviews for a person in a given ISO week.

    Args:
        person_name: The person's Wikipedia article title.
        week: ISO week string (e.g. "2026-W04").

    Returns:
        Total pageview count for that week. Returns 0 on error.
    """
    monday, sunday = week_to_dates(week)
    start = format_yyyymmdd(monday)
    end = format_yyyymmdd(sunday)

    daily = fetch_pageviews(person_name, start, end)
    return sum(day["views"] for day in daily)
