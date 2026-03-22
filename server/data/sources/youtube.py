"""
YouTube Data API source.

Measures how much video content is being produced about a person.
Uses the YouTube Data API v3 to search for recent videos mentioning
a person's name and aggregates view counts.

API: https://developers.google.com/youtube/v3
Free tier: 10,000 units/day. A search costs 100 units. Video details cost 1 unit.
This means ~100 searches/day — enough for a weekly batch of ~100 persons.
"""

import logging
import os
import time

import requests

from server.config import ENV

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
API_KEY = os.getenv("YOUTUBE_API_KEY", "")
REQUEST_DELAY = 0.5


def fetch_recent_videos(person_name: str, max_results: int = 10) -> dict:
    """
    Search YouTube for recent videos about a person.

    Args:
        person_name: The person's name.
        max_results: Maximum number of videos to return (max 50).

    Returns:
        Dict with keys:
        - "video_count": int (number of videos found)
        - "total_views": int (sum of view counts)
        - "avg_views": float (average views per video)
        Returns zeros on error or if no API key.
    """
    empty = {"video_count": 0, "total_views": 0, "avg_views": 0.0}

    if not API_KEY:
        logger.debug("YouTube API key not set, skipping")
        return empty

    # Search for recent videos
    search_params = {
        "part": "id",
        "q": person_name,
        "type": "video",
        "order": "date",
        "publishedAfter": "",  # Will be set by caller or default to recent
        "maxResults": max_results,
        "key": API_KEY,
    }
    # Remove empty params
    search_params = {k: v for k, v in search_params.items() if v}

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        video_ids = [item["id"]["videoId"] for item in data.get("items", [])
                     if item.get("id", {}).get("videoId")]

        if not video_ids:
            return empty

        # Get view counts for found videos
        time.sleep(REQUEST_DELAY)
        stats_params = {
            "part": "statistics",
            "id": ",".join(video_ids),
            "key": API_KEY,
        }
        stats_resp = requests.get(YOUTUBE_VIDEOS_URL, params=stats_params, timeout=10)
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

        total_views = 0
        count = 0
        for item in stats_data.get("items", []):
            views = int(item.get("statistics", {}).get("viewCount", 0))
            total_views += views
            count += 1

        return {
            "video_count": count,
            "total_views": total_views,
            "avg_views": total_views / count if count > 0 else 0.0,
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("YouTube API error for %s: %s", person_name, e)
        return empty


def weekly_youtube_score(person_name: str, week: str) -> float:
    """
    Get a composite YouTube activity score for a person.

    Args:
        person_name: The person's name.
        week: ISO week string.

    Returns:
        Raw composite score based on video count and views.
    """
    data = fetch_recent_videos(person_name, max_results=10)
    # Weight: video count matters, total views add magnitude
    return data["video_count"] * 10.0 + data["total_views"] * 0.001
