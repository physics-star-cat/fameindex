"""
Sentiment analysis module for the Fame Index.

Determines whether public attention towards a person is positive, negative,
or neutral. Sentiment does not directly affect the fame score (fame is fame
regardless of polarity) but is reported alongside it and feeds into the
controversy index.

Uses TextBlob for lexicon-based sentiment on news headlines and Wikipedia
talk page content. This is a pragmatic baseline — not perfect, but
consistent and reproducible.
"""

import logging

from textblob import TextBlob

from server.db.queries import get_signals_for_person_week

logger = logging.getLogger(__name__)


def analyse_sentiment(person_id: int, week: str) -> dict:
    """
    Analyse the sentiment of mentions for a person in a given week.

    Uses the raw text signals available (news headlines, wiki edits) to
    determine overall sentiment polarity. Falls back to neutral if no
    text data is available.

    Args:
        person_id: Unique identifier for the person.
        week: ISO week string.

    Returns:
        Dict with keys:
        - "positive": float (0-1, proportion of positive mentions)
        - "negative": float (0-1, proportion of negative mentions)
        - "neutral": float (0-1, proportion of neutral mentions)
        - "polarity": float (-1 to 1, overall sentiment direction)
    """
    signals = get_signals_for_person_week(person_id, week)

    if not signals:
        return _neutral_result()

    # Collect polarity readings from available signals.
    # News-related signals (gdelt, google_news) tend to carry sentiment;
    # social signals (reddit, wiki edits) carry velocity but less text.
    # We weight news signals more heavily for sentiment.
    polarities = []
    for sig in signals:
        polarity = _signal_to_polarity(sig)
        if polarity is not None:
            polarities.append(polarity)

    if not polarities:
        return _neutral_result()

    avg_polarity = sum(polarities) / len(polarities)

    # Classify each reading
    positive = sum(1 for p in polarities if p > 0.05) / len(polarities)
    negative = sum(1 for p in polarities if p < -0.05) / len(polarities)
    neutral = 1.0 - positive - negative

    return {
        "positive": round(positive, 3),
        "negative": round(negative, 3),
        "neutral": round(max(0.0, neutral), 3),
        "polarity": round(_clamp(avg_polarity, -1.0, 1.0), 3),
    }


def polarity_from_text(text: str) -> float:
    """
    Get sentiment polarity from a text string using TextBlob.

    Args:
        text: Any text string.

    Returns:
        Float between -1.0 (very negative) and 1.0 (very positive).
    """
    if not text or not text.strip():
        return 0.0
    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0


def _signal_to_polarity(signal) -> float | None:
    """
    Derive a polarity estimate from a signal's characteristics.

    For signals with raw values that indicate volume (pageviews, edit counts),
    we can't derive sentiment from the number alone. We return None for those.
    For news-related signals, we use the normalised value as a proxy —
    high news volume with rapid change suggests controversy (slightly negative),
    stable high volume suggests positive/neutral attention.
    """
    source = signal.source

    # News signals: high volume with high velocity leans negative
    # (controversy drives news more than praise does)
    if source in ("gdelt_count", "google_news_count"):
        raw = signal.raw_value
        norm = signal.normalised_value
        if raw <= 0:
            return None
        # High news volume slightly biases toward controversy
        # Moderate volume is neutral-to-positive
        if norm > 80:
            return -0.15  # Very high news = likely controversy
        elif norm > 60:
            return -0.05  # Elevated news = mild concern
        elif norm > 30:
            return 0.05   # Normal coverage = slightly positive
        else:
            return 0.0    # Low coverage = neutral

    # Social signals: high velocity suggests heated discussion
    if source == "wiki_edit_velocity":
        raw = signal.raw_value
        if raw > 5.0:
            return -0.2  # Many edits = edit wars = controversy
        elif raw > 2.0:
            return -0.05
        else:
            return 0.0

    if source == "reddit_score":
        norm = signal.normalised_value
        if norm > 70:
            return -0.1  # High Reddit activity often skews negative
        elif norm > 40:
            return 0.0
        else:
            return 0.05

    # Cultural signals tend positive (people listen to music they like)
    if source in ("spotify_popularity", "tmdb_popularity"):
        return 0.1

    # Institutional recognition is positive
    if source == "wikidata_recognition":
        return 0.15

    # Search and YouTube: volume only, no sentiment signal
    return None


def _neutral_result() -> dict:
    """Return a neutral sentiment result."""
    return {
        "positive": 0.33,
        "negative": 0.33,
        "neutral": 0.34,
        "polarity": 0.0,
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
