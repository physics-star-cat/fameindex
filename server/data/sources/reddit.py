"""
Reddit data source.

Uses Reddit's JSON endpoints (no OAuth required for read-only public data)
to measure social discussion volume. Counts posts and comments mentioning
a person across major subreddits.

Reddit's JSON API is accessed by appending .json to any Reddit URL.
Rate limits: ~30 requests/minute for unauthenticated access.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
HEADERS = {"User-Agent": "FameIndex/1.0 (research project)"}
REQUEST_DELAY = 2.0  # Reddit is strict with unauthenticated requests


def fetch_reddit_mentions(person_name: str, time_filter: str = "week") -> dict:
    """
    Search Reddit for mentions of a person.

    Args:
        person_name: The person's name.
        time_filter: Time window — "hour", "day", "week", "month", "year", "all".

    Returns:
        Dict with keys:
        - "post_count": int (number of posts found)
        - "total_score": int (sum of post scores/upvotes)
        - "total_comments": int (sum of comment counts)
        Returns zeros on error.
    """
    empty = {"post_count": 0, "total_score": 0, "total_comments": 0}

    params = {
        "q": f'"{person_name}"',
        "sort": "relevance",
        "t": time_filter,
        "limit": 100,
    }

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(REDDIT_SEARCH_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        posts = data.get("data", {}).get("children", [])
        if not posts:
            return empty

        total_score = 0
        total_comments = 0
        for post in posts:
            post_data = post.get("data", {})
            total_score += post_data.get("score", 0)
            total_comments += post_data.get("num_comments", 0)

        return {
            "post_count": len(posts),
            "total_score": total_score,
            "total_comments": total_comments,
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Reddit API error for %s: %s", person_name, e)
        return empty


def weekly_social_score(person_name: str, week: str) -> float:
    """
    Get a composite social discussion score for a person this week.

    Combines post count, upvotes, and comment activity into a single
    raw number representing discussion volume.

    Args:
        person_name: The person's name.
        week: ISO week string (used for cache keying, not filtering —
              Reddit's time filter handles recency).

    Returns:
        A raw composite score (higher = more discussion).
    """
    data = fetch_reddit_mentions(person_name, time_filter="week")

    # Composite: posts contribute 1x, comments 0.5x, score 0.01x
    score = (
        data["post_count"] * 1.0 +
        data["total_comments"] * 0.5 +
        data["total_score"] * 0.01
    )
    return score
