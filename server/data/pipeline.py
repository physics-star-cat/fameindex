"""
Data pipeline orchestrator.

Coordinates the collection of data from all sources across five dimensions:
- Search Interest: Wikipedia pageviews, Google Trends
- News Presence: GDELT, Google News RSS
- Social Buzz: Reddit, Wikipedia edit velocity, YouTube
- Cultural Output: Spotify, TMDB
- Institutional Recognition: Wikidata awards/nominations

Each source is fetched independently with error isolation — if one
source fails, the others continue. Results are normalised and stored.
"""

import logging

from server.data.sources.wikipedia import weekly_aggregate as wiki_pageviews
from server.data.sources.google_trends import fetch_interest_for_week
from server.data.sources.gdelt import weekly_news_count
from server.data.sources.google_news import weekly_article_count
from server.data.sources.social import fetch_mention_velocity
from server.data.sources.reddit import weekly_social_score as reddit_score
from server.data.sources.youtube import weekly_youtube_score
from server.data.sources.spotify import fetch_artist_popularity
from server.data.sources.tmdb import fetch_person_popularity as tmdb_popularity
from server.data.sources.wikidata import institutional_score

from server.data.normalize import normalize_batch
from server.db import init_db, get_session
from server.db.models import Person
from server.db.queries import upsert_signal, get_historical_signals

logger = logging.getLogger(__name__)


def run_pipeline(week: str, persons: list[dict] | None = None) -> dict:
    """
    Run the full data collection pipeline for a week.

    Fetches data from all sources across all dimensions for all tracked
    persons, normalises it, and stores the results in the database.

    Args:
        week: ISO week string (e.g. "2026-W04").
        persons: Optional list of person dicts. If None, loads from database.
            Each dict needs: "id", "name", "wikipedia_title".
            Optional: "spotify_id", "tmdb_id".

    Returns:
        Dict summarising the pipeline run.
    """
    init_db()

    if persons is None:
        persons = _load_persons_from_db()

    errors = []
    signals_collected = 0

    for person in persons:
        person_signals = _fetch_all_dimensions(person, week, errors)
        signals_collected += len(person_signals)

        # Attach historical data for adaptive normalisation
        person_signals = _attach_historical(person_signals, person["id"])

        # Normalise (also sets dimension field)
        person_signals = normalize_batch(person_signals)

        # Store each signal
        for sig in person_signals:
            upsert_signal(
                person_id=sig["person_id"],
                week=sig["week"],
                source=sig["source"],
                dimension=sig["dimension"],
                raw_value=sig["raw_value"],
                normalised_value=sig["normalised_value"],
            )

    logger.info(
        "Pipeline complete: %d persons, %d signals, %d errors",
        len(persons), signals_collected, len(errors),
    )

    return {
        "persons_processed": len(persons),
        "signals_collected": signals_collected,
        "errors": errors,
    }


def _load_persons_from_db() -> list[dict]:
    """Load active persons from the database."""
    with get_session() as session:
        from sqlalchemy import select
        stmt = select(Person).where(Person.active == True)  # noqa: E712
        persons = session.scalars(stmt).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "wikipedia_title": p.wikipedia_title,
                "spotify_id": p.spotify_id,
                "tmdb_id": p.tmdb_id,
            }
            for p in persons
        ]


def _fetch_all_dimensions(person: dict, week: str, errors: list) -> list[dict]:
    """Fetch data from all sources across all dimensions for one person."""
    signals = []
    pid = person["id"]
    name = person["name"]
    wiki = person["wikipedia_title"]

    # --- SEARCH dimension ---
    _try_fetch(signals, errors, name, "wikipedia_pageviews", pid, week,
               lambda: float(wiki_pageviews(wiki, week)))

    _try_fetch(signals, errors, name, "google_trends", pid, week,
               lambda: float(fetch_interest_for_week(name, week)))

    # --- NEWS dimension ---
    _try_fetch(signals, errors, name, "gdelt_count", pid, week,
               lambda: float(weekly_news_count(name, week)))

    _try_fetch(signals, errors, name, "google_news_count", pid, week,
               lambda: float(weekly_article_count(name, week)))

    # --- SOCIAL dimension ---
    _try_fetch(signals, errors, name, "reddit_score", pid, week,
               lambda: float(reddit_score(name, week)))

    _try_fetch(signals, errors, name, "wiki_edit_velocity", pid, week,
               lambda: float(fetch_mention_velocity(wiki, week)["velocity"]))

    _try_fetch(signals, errors, name, "youtube_score", pid, week,
               lambda: float(weekly_youtube_score(name, week)))

    # --- CULTURAL dimension (only if identifiers available) ---
    spotify_id = person.get("spotify_id")
    if spotify_id:
        _try_fetch(signals, errors, name, "spotify_popularity", pid, week,
                   lambda: float(fetch_artist_popularity(spotify_id)))

    tmdb_id = person.get("tmdb_id")
    if tmdb_id:
        _try_fetch(signals, errors, name, "tmdb_popularity", pid, week,
                   lambda: float(tmdb_popularity(tmdb_id)))

    # --- INSTITUTIONAL dimension ---
    _try_fetch(signals, errors, name, "wikidata_recognition", pid, week,
               lambda: float(institutional_score(wiki)))

    return signals


def _try_fetch(signals: list, errors: list, person_name: str,
               source: str, person_id: int, week: str, fetcher) -> None:
    """Try to fetch a signal, appending to signals or errors."""
    try:
        raw_value = fetcher()
        signals.append({
            "person_id": person_id,
            "week": week,
            "source": source,
            "raw_value": raw_value,
        })
    except Exception as e:
        msg = f"{source} error for {person_name}: {e}"
        logger.error(msg)
        errors.append(msg)


def _attach_historical(signals: list[dict], person_id: int) -> list[dict]:
    """Attach historical raw values to each signal for normalisation."""
    for sig in signals:
        historical_signals = get_historical_signals(
            person_id=person_id,
            source=sig["source"],
            num_weeks=12,
        )
        sig["historical"] = [s.raw_value for s in historical_signals]
    return signals


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        from server.data.week_utils import date_to_week
        from datetime import date
        week = date_to_week(date.today())
    else:
        week = sys.argv[1]

    print(f"Running pipeline for week: {week}")
    result = run_pipeline(week)
    print(f"Done: {result['persons_processed']} persons, "
          f"{result['signals_collected']} signals, "
          f"{len(result['errors'])} errors")
    if result["errors"]:
        for err in result["errors"]:
            print(f"  ERROR: {err}")
