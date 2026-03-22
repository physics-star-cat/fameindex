"""
Data normalisation layer.

Each data source returns values in different scales and units. This module
normalises all signals to a consistent 0-100 scale so they can be combined
by the scoring engine.

Signal types grouped by dimension:
- search: wikipedia_pageviews (log), google_trends (passthrough)
- news: gdelt_count (log), google_news_count (log)
- social: reddit_score (log), wiki_edit_velocity (log_ratio), youtube_score (log)
- cultural: spotify_popularity (passthrough), tmdb_popularity (log)
- institutional: wikidata_recognition (log)
"""

import math
import logging

logger = logging.getLogger(__name__)

SIGNAL_PARAMS = {
    # --- SEARCH dimension ---
    "wikipedia_pageviews": {
        "method": "log",
        "log_floor": 100,
        "log_ceiling": 5_000_000,
    },
    "google_trends": {
        "method": "passthrough",
    },

    # --- NEWS dimension ---
    "gdelt_count": {
        "method": "log",
        "log_floor": 1,
        "log_ceiling": 10_000,
    },
    "google_news_count": {
        "method": "log",
        "log_floor": 1,
        "log_ceiling": 100,  # Google News RSS maxes at ~100 results
    },

    # --- SOCIAL dimension ---
    "reddit_score": {
        "method": "log",
        "log_floor": 1,
        "log_ceiling": 5_000,
    },
    "wiki_edit_velocity": {
        "method": "log_ratio",
        "neutral": 1.0,
        "max_ratio": 20.0,
    },
    "youtube_score": {
        "method": "log",
        "log_floor": 1,
        "log_ceiling": 10_000,
    },

    # --- CULTURAL dimension ---
    "spotify_popularity": {
        "method": "passthrough",  # Already 0-100
    },
    "tmdb_popularity": {
        "method": "log",
        "log_floor": 1.0,
        "log_ceiling": 200.0,  # TMDB popularity typically 0-200+
    },

    # --- INSTITUTIONAL dimension ---
    "wikidata_recognition": {
        "method": "log",
        "log_floor": 1,
        "log_ceiling": 500,  # awards*3 + nominations — top figures reach hundreds
    },
}

# Map each source to its dimension
SOURCE_DIMENSIONS = {
    "wikipedia_pageviews": "search",
    "google_trends": "search",
    "gdelt_count": "news",
    "google_news_count": "news",
    "reddit_score": "social",
    "wiki_edit_velocity": "social",
    "youtube_score": "social",
    "spotify_popularity": "cultural",
    "tmdb_popularity": "cultural",
    "wikidata_recognition": "institutional",
}


def get_dimension(source: str) -> str:
    """Get the dimension a source belongs to."""
    return SOURCE_DIMENSIONS.get(source, "unknown")


def normalize_signal(raw_value: float, signal_type: str, historical: list | None = None) -> float:
    """
    Normalise a raw signal value to a 0-100 scale.

    Args:
        raw_value: The raw value from a data source.
        signal_type: Type of signal (determines normalisation method).
        historical: List of historical raw values (used for adaptive scaling).

    Returns:
        A float between 0 and 100.
    """
    params = SIGNAL_PARAMS.get(signal_type)
    if not params:
        logger.warning("Unknown signal type: %s, returning 0", signal_type)
        return 0.0

    method = params["method"]

    if method == "passthrough":
        return _clamp(raw_value)

    elif method == "log":
        return _log_scale(
            raw_value,
            floor=params["log_floor"],
            ceiling=params["log_ceiling"],
            historical=historical,
        )

    elif method == "log_ratio":
        return _log_ratio_scale(
            raw_value,
            neutral=params["neutral"],
            max_ratio=params["max_ratio"],
        )

    return 0.0


def normalize_batch(signals: list[dict]) -> list[dict]:
    """
    Normalise a batch of signals.

    Args:
        signals: List of dicts with keys "person_id", "source", "raw_value".
            Optionally "historical" (list of prior raw values).

    Returns:
        Same list with "normalised_value" and "dimension" keys added.
    """
    for sig in signals:
        sig["normalised_value"] = normalize_signal(
            raw_value=sig["raw_value"],
            signal_type=sig["source"],
            historical=sig.get("historical"),
        )
        sig["dimension"] = get_dimension(sig["source"])
    return signals


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value to [low, high]."""
    return max(low, min(high, value))


def _log_scale(value: float, floor: float, ceiling: float, historical: list | None = None) -> float:
    """
    Log-scale a value to 0-100.

    Handles power-law distributions well. If historical data is provided,
    uses the max historical value to adapt the ceiling.
    """
    if value <= 0:
        return 0.0

    effective_ceiling = ceiling
    if historical:
        hist_max = max(historical) if historical else 0
        if hist_max > 0:
            effective_ceiling = max(ceiling, hist_max * 2)

    if value <= floor:
        return 0.0
    if value >= effective_ceiling:
        return 100.0

    log_value = math.log(value) - math.log(floor)
    log_range = math.log(effective_ceiling) - math.log(floor)

    return _clamp((log_value / log_range) * 100.0)


def _log_ratio_scale(value: float, neutral: float, max_ratio: float) -> float:
    """
    Scale a ratio value to 0-100 using log scaling.

    neutral maps to 50. Higher ratios → 100, lower → 0.
    """
    if value <= 0:
        return 0.0

    if value == neutral:
        return 50.0

    if value >= max_ratio:
        return 100.0

    if value < neutral:
        if value <= 1.0 / max_ratio:
            return 0.0
        log_value = math.log(value)
        log_neutral = math.log(neutral)
        log_min = math.log(1.0 / max_ratio)
        proportion = (log_value - log_min) / (log_neutral - log_min)
        return _clamp(proportion * 50.0)
    else:
        log_value = math.log(value) - math.log(neutral)
        log_max = math.log(max_ratio) - math.log(neutral)
        proportion = log_value / log_max
        return _clamp(50.0 + proportion * 50.0)
