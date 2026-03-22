"""
TMDB (The Movie Database) data source.

TMDB provides a person popularity score based on how much a person's
films/TV shows are being discussed and viewed. It also provides
filmography data for measuring cultural output.

API: https://developer.themoviedb.org/docs
Free tier: ~50 requests/second, no daily cap. Extremely generous.
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
API_KEY = os.getenv("TMDB_API_KEY", "")
REQUEST_DELAY = 0.1  # TMDB allows ~50 req/s


def fetch_person_popularity(tmdb_id: int) -> float:
    """
    Fetch the TMDB popularity score for a person.

    TMDB popularity is a composite of how much a person's content
    is being viewed, rated, and added to watchlists.

    Args:
        tmdb_id: The TMDB person ID.

    Returns:
        Popularity score (unbounded float, typically 0-200+).
        Returns 0.0 on error or if not configured.
    """
    if not API_KEY:
        logger.debug("TMDB API key not set, skipping")
        return 0.0

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            f"{TMDB_BASE}/person/{tmdb_id}",
            params={"api_key": API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("popularity", 0.0)

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("TMDB API error for person %d: %s", tmdb_id, e)
        return 0.0


def search_person(name: str) -> dict | None:
    """
    Search TMDB for a person by name.

    Args:
        name: Person's name.

    Returns:
        Dict with "id", "name", "popularity", "known_for_department",
        or None if not found.
    """
    if not API_KEY:
        return None

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            f"{TMDB_BASE}/search/person",
            params={"api_key": API_KEY, "query": name},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        person = results[0]
        return {
            "id": person["id"],
            "name": person["name"],
            "popularity": person.get("popularity", 0.0),
            "known_for_department": person.get("known_for_department", ""),
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("TMDB search error for %s: %s", name, e)
        return None


def get_credits_count(tmdb_id: int) -> int:
    """
    Count the total number of film/TV credits for a person.

    Args:
        tmdb_id: The TMDB person ID.

    Returns:
        Total number of credits (cast + crew). Returns 0 on error.
    """
    if not API_KEY:
        return 0

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            f"{TMDB_BASE}/person/{tmdb_id}/combined_credits",
            params={"api_key": API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        cast = len(data.get("cast", []))
        crew = len(data.get("crew", []))
        return cast + crew

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("TMDB credits error for person %d: %s", tmdb_id, e)
        return 0
