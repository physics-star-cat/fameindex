"""
Spotify data source.

Fetches artist popularity scores from the Spotify Web API. Spotify's
popularity score (0-100) is pre-computed and represents how much an
artist's tracks are being streamed recently. It's an excellent ready-made
fame signal for musicians.

Only applicable to persons with a Spotify artist ID.
API: https://developer.spotify.com/documentation/web-api
Free tier: Client Credentials flow, no user auth needed.
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
ARTIST_URL = "https://api.spotify.com/v1/artists"
REQUEST_DELAY = 0.2

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

_token_cache = {"token": None, "expires": 0}


def _get_access_token() -> str | None:
    """Get a Spotify access token using client credentials flow."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None

    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now:
        return _token_cache["token"]

    try:
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        _token_cache["token"] = data["access_token"]
        _token_cache["expires"] = now + data.get("expires_in", 3600) - 60
        return _token_cache["token"]

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Spotify auth error: %s", e)
        return None


def fetch_artist_popularity(spotify_id: str) -> int:
    """
    Fetch the popularity score for a Spotify artist.

    Args:
        spotify_id: The Spotify artist ID.

    Returns:
        Popularity score (0-100). Returns 0 on error or if not configured.
    """
    token = _get_access_token()
    if not token:
        logger.debug("Spotify not configured, skipping")
        return 0

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            f"{ARTIST_URL}/{spotify_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("popularity", 0)

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Spotify API error for %s: %s", spotify_id, e)
        return 0


def search_artist(name: str) -> dict | None:
    """
    Search for an artist by name and return their ID and popularity.

    Args:
        name: Artist name to search for.

    Returns:
        Dict with "id", "name", "popularity", or None if not found.
    """
    token = _get_access_token()
    if not token:
        return None

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            params={"q": name, "type": "artist", "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("artists", {}).get("items", [])
        if not items:
            return None

        artist = items[0]
        return {
            "id": artist["id"],
            "name": artist["name"],
            "popularity": artist.get("popularity", 0),
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Spotify search error for %s: %s", name, e)
        return None
