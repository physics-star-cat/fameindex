"""
Social media data source.

Measures social velocity — the rate of change in public discussion
about a person. Uses Wikipedia edit activity as a proxy signal: when
someone is trending socially, their Wikipedia article gets more edits
and talk page activity.

This is a pragmatic choice: social platform APIs are expensive, gated,
or unstable. Wikipedia edit velocity correlates strongly with social
buzz and is freely available via the MediaWiki API.

Can be extended with additional sources (Reddit, etc.) when available.
"""

import logging
import time

import requests

from server.config import WIKIPEDIA_USER_AGENT
from server.data.week_utils import week_to_dates, previous_week

logger = logging.getLogger(__name__)

MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": WIKIPEDIA_USER_AGENT}
REQUEST_DELAY = 0.2


def _count_revisions(article_title: str, start: str, end: str) -> int:
    """
    Count the number of revisions to a Wikipedia article in a date range.

    Args:
        article_title: Wikipedia article title.
        start: Start timestamp (ISO format).
        end: End timestamp (ISO format).

    Returns:
        Number of revisions in the period.
    """
    params = {
        "action": "query",
        "titles": article_title.replace(" ", "_"),
        "prop": "revisions",
        "rvprop": "timestamp",
        "rvstart": end + "T23:59:59Z",
        "rvend": start + "T00:00:00Z",
        "rvlimit": "500",
        "format": "json",
    }

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(MEDIAWIKI_API, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            revisions = page.get("revisions", [])
            return len(revisions)

        return 0

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Wikipedia revisions API error for %s: %s", article_title, e)
        return 0


def fetch_mention_velocity(person_name: str, week: str) -> dict:
    """
    Fetch the rate of change in social activity for a person.

    Uses Wikipedia edit counts as a proxy for social discussion velocity.
    More edits = more public attention = correlates with social mentions.

    Args:
        person_name: The person's Wikipedia article title.
        week: ISO week string.

    Returns:
        Dict with keys:
        - "current_mentions": int (edits this week)
        - "previous_mentions": int (edits last week)
        - "velocity": float (ratio of current to previous, 1.0 = unchanged)
        - "acceleration": float (not available with 2-week window, set to 0)
    """
    article = person_name.replace(" ", "_")

    # Current week
    monday, sunday = week_to_dates(week)
    current_count = _count_revisions(
        article,
        monday.isoformat(),
        sunday.isoformat(),
    )

    # Previous week
    prev = previous_week(week)
    prev_monday, prev_sunday = week_to_dates(prev)
    previous_count = _count_revisions(
        article,
        prev_monday.isoformat(),
        prev_sunday.isoformat(),
    )

    # Calculate velocity (ratio, guarding against division by zero)
    if previous_count > 0:
        velocity = current_count / previous_count
    elif current_count > 0:
        velocity = float(current_count)  # Infinite growth from zero, cap later
    else:
        velocity = 1.0  # No activity either week

    return {
        "current_mentions": current_count,
        "previous_mentions": previous_count,
        "velocity": velocity,
        "acceleration": 0.0,  # Would need 3 weeks of data
    }
