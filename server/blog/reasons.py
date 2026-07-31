"""
Signal-derived reasons for why someone moved.

Replaces the previous approach, which drew commentary from `random.choice`
template pools. That produced text like "Spotify playlists noticed" attached to
whoever happened to move — the same line landing on two different people in the
same post, and crediting Spotify, which is not among the signals collected. The
post said what moved and then invented a why.

Every signal is already stored per person per period, so the real reason is
available: compare a person's signals against the previous period and name the
one that moved most. The register stays droll; the clause is now true.
"""

import logging

from server.db.queries import get_signals_for_person_week

logger = logging.getLogger(__name__)

# How each signal reads in prose. Keep these short — they are the tail of a
# sentence like "Eilish up 5 — <phrase>."
_SIGNAL_PHRASES = {
    "wikipedia_pageviews": ("Wikipedia traffic", "looking them up"),
    "google_trends": ("search interest", "searching"),
    "gdelt_count": ("news mentions", "writing about them"),
    "google_news_count": ("press coverage", "covering them"),
    "reddit_score": ("Reddit chatter", "arguing about them"),
    "wiki_edit_velocity": ("edits to their Wikipedia page", "rewriting their page"),
    "youtube_score": ("YouTube activity", "watching"),
    "wikidata_recognition": ("formal recognition", None),
}

# Ratio thresholds, largest first. A ratio of 3.1 reads as "tripled".
_MAGNITUDES = [
    (5.0, "went up fivefold"),
    (3.0, "tripled"),
    (2.0, "doubled"),
    (1.5, "jumped by half"),
    (1.15, "climbed"),
]
_DECLINES = [
    (0.2, "collapsed"),
    (0.34, "fell by two thirds"),
    (0.5, "halved"),
    (0.7, "dropped a third"),
    (0.85, "slipped"),
]

# Below this the movement is noise and we say nothing rather than inventing one.
_MIN_INTERESTING_RATIO = 1.15


def _signals_by_source(person_id: int, period: str) -> dict[str, float]:
    """Raw signal values keyed by source, for one person in one period."""
    out = {}
    for sig in get_signals_for_person_week(person_id, period):
        try:
            out[sig.source] = float(sig.raw_value)
        except (TypeError, ValueError):
            continue
    return out


def biggest_mover(person_id: int, period: str, previous_period: str) -> dict | None:
    """
    Find the signal that moved most for a person between two periods.

    Returns a dict with source, ratio, current and previous values, or None if
    nothing moved enough to be worth mentioning. Signals absent from either
    period are skipped — a signal we could not collect is not evidence of a
    change, and inventing one is exactly the failure this module exists to fix.
    """
    now = _signals_by_source(person_id, period)
    before = _signals_by_source(person_id, previous_period)

    best = None
    for source, current in now.items():
        prior = before.get(source)
        if prior is None or prior <= 0 or current <= 0:
            continue
        ratio = current / prior
        distance = max(ratio, 1 / ratio)
        if distance < _MIN_INTERESTING_RATIO:
            continue
        if best is None or distance > best["distance"]:
            best = {
                "source": source,
                "ratio": ratio,
                "distance": distance,
                "current": current,
                "previous": prior,
            }
    return best


def describe_move(person_id: int, period: str, previous_period: str,
                  rising: bool) -> str | None:
    """
    A short clause explaining why someone moved, or None if we cannot say.

    Returning None is deliberate and important: when no signal moved much, the
    honest output is silence. The previous generator always produced a reason,
    which is how "The streaming numbers don't lie" ended up attached to two
    different people in the same post.
    """
    mover = biggest_mover(person_id, period, previous_period)
    if mover is None:
        return None

    phrase = _SIGNAL_PHRASES.get(mover["source"])
    if not phrase:
        return None
    noun = phrase[0]

    ratio = mover["ratio"]
    if ratio >= 1:
        for threshold, wording in _MAGNITUDES:
            if ratio >= threshold:
                return f"{noun} {wording}"
        return None

    for threshold, wording in _DECLINES:
        if ratio <= threshold:
            return f"{noun} {wording}"
    return None
