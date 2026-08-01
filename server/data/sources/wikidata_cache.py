"""
Cache for Wikidata institutional scores.

Awards and formal recognition are the slowest-moving thing the index measures —
a Nobel or an Oscar does not change month to month. Yet every run re-queried
Wikidata for every person: the 2026 backfill made 896 SPARQL calls (7 months x
128 people) to learn 128 facts.

That was the single slowest signal, and the largest source of the intermittent
failures fill_gaps.py kept having to repair, because Wikidata's SPARQL endpoint
times out under sustained load.

Cached in its own table rather than as columns on `persons`, so cache state
stays separate from roster data and can be cleared without touching the domain
model.

Entries older than MAX_AGE_DAYS are refetched, so a newly won award still lands
within a quarter. A stale value is served if the refetch fails — an old score is
much closer to the truth than the alternative, which is no institutional signal
at all and a person ranked under different weightings from everyone else.
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[3] / "fame_index.db"

# Awards accrue slowly. A quarter keeps the data honest without re-querying
# 128 entities every month.
MAX_AGE_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wikidata_cache (
    wikipedia_title TEXT PRIMARY KEY,
    score           REAL NOT NULL,
    fetched_at      TEXT NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute(_SCHEMA)
    return con


def get_cached(wikipedia_title: str, max_age_days: int = MAX_AGE_DAYS) -> float | None:
    """Cached score if present and fresh enough, else None."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT score, fetched_at FROM wikidata_cache WHERE wikipedia_title = ?",
            (wikipedia_title,)).fetchone()
        if not row:
            return None
        score, fetched_at = row
        age = datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)
        if age > timedelta(days=max_age_days):
            return None
        return float(score)
    finally:
        con.close()


def put(wikipedia_title: str, score: float) -> None:
    con = _connect()
    try:
        con.execute(
            "INSERT INTO wikidata_cache (wikipedia_title, score, fetched_at) "
            "VALUES (?,?,?) ON CONFLICT(wikipedia_title) DO UPDATE SET "
            "score=excluded.score, fetched_at=excluded.fetched_at",
            (wikipedia_title, float(score), datetime.now(timezone.utc).isoformat()))
        con.commit()
    finally:
        con.close()


def get_stale(wikipedia_title: str) -> float | None:
    """Cached score regardless of age — the fallback when a refetch fails."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT score FROM wikidata_cache WHERE wikipedia_title = ?",
            (wikipedia_title,)).fetchone()
        return float(row[0]) if row else None
    finally:
        con.close()


def institutional_score_cached(wikipedia_title: str,
                               max_age_days: int = MAX_AGE_DAYS) -> float:
    """
    Institutional score, from cache when possible.

    Raises only when there is no usable value at all — no fresh fetch and no
    stale entry to fall back on. The caller then records no signal, which the
    scoring engine handles by re-normalising, rather than inventing a zero.
    """
    cached = get_cached(wikipedia_title, max_age_days)
    if cached is not None:
        return cached

    from server.data.sources.wikidata import institutional_score
    try:
        score = float(institutional_score(wikipedia_title))
        put(wikipedia_title, score)
        return score
    except Exception as e:
        stale = get_stale(wikipedia_title)
        if stale is not None:
            logger.warning(
                "Wikidata refetch failed for %s (%s) — using stale cached score %.1f",
                wikipedia_title, e, stale)
            return stale
        raise


def stats() -> dict:
    con = _connect()
    try:
        total = con.execute("SELECT COUNT(*) FROM wikidata_cache").fetchone()[0]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).isoformat()
        fresh = con.execute(
            "SELECT COUNT(*) FROM wikidata_cache WHERE fetched_at > ?", (cutoff,)).fetchone()[0]
        return {"total": total, "fresh": fresh, "stale": total - fresh}
    finally:
        con.close()
