"""
Google News RSS data source.

Google News provides RSS feeds for search queries. We parse these to
count how many news articles are currently surfaced for a person's name.
This is a lightweight complement to GDELT — it captures what Google
considers the top/recent results.

Feed URL: https://news.google.com/rss/search?q={query}
Rate limits: Undocumented. Use modest delays.
"""

import logging
import time
from urllib.parse import quote

import feedparser

from server.data.week_utils import week_to_dates

logger = logging.getLogger(__name__)

BASE_URL = "https://news.google.com/rss/search"
REQUEST_DELAY = 1.0


def fetch_news_articles(person_name: str, when: str = "7d") -> list[dict]:
    """
    Fetch recent Google News articles for a person.

    Args:
        person_name: The person's name.
        when: Time window (e.g. "7d" for 7 days, "1d" for 1 day).

    Returns:
        List of article dicts with keys: "title", "source", "published".
        Returns empty list on error.
    """
    query = quote(f'"{person_name}"')
    url = f"{BASE_URL}?q={query}&hl=en-US&gl=US&ceid=US:en&when={when}"

    try:
        time.sleep(REQUEST_DELAY)
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("Google News RSS parse error for: %s", person_name)
            return []

        articles = []
        for entry in feed.entries:
            articles.append({
                "title": entry.get("title", ""),
                "source": entry.get("source", {}).get("title", ""),
                "published": entry.get("published", ""),
            })

        return articles

    except Exception as e:
        logger.error("Google News RSS error for %s: %s", person_name, e)
        return []


def weekly_article_count(person_name: str, week: str) -> int:
    """
    Count Google News articles for a person in a given week.

    Note: Google News RSS only returns recent articles (up to ~100).
    For historical weeks, this will return 0. Use GDELT for historical data.

    Args:
        person_name: The person's name.
        week: ISO week string.

    Returns:
        Number of articles found.
    """
    articles = fetch_news_articles(person_name, when="7d")
    return len(articles)
