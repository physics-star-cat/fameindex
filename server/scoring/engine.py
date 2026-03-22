"""
Core scoring engine for the Fame Index.

Combines normalised signals across five dimensions into:
1. Five dimension scores (0-100 each) — publicly visible on profiles
2. One headline fame score (0-100) — the ranking number

The dimension scores are simple averages of their constituent signals.
The headline score uses a private weighted combination of dimensions.
The weights are proprietary IP and never leave this module.
"""

import logging

from server.config import DIMENSION_WEIGHTS
from server.db.queries import get_signals_for_person_week, get_all_persons, get_person_history
from server.scoring.sentiment import analyse_sentiment
from server.scoring.controversy import calculate_controversy

logger = logging.getLogger(__name__)

DIMENSIONS = ["search", "news", "social", "cultural", "institutional"]


def calculate_dimension_scores(person_id: int, week: str) -> dict[str, float]:
    """
    Calculate the five dimension scores for a person in a given week.

    Each dimension score is the average of its normalised signal values.
    If no signals exist for a dimension, it scores 0.

    Args:
        person_id: Unique identifier for the person.
        week: ISO week string.

    Returns:
        Dict mapping dimension name to score (0-100).
    """
    signals = get_signals_for_person_week(person_id, week)

    # Group signals by dimension
    by_dimension: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
    for sig in signals:
        dim = sig.dimension
        if dim in by_dimension:
            by_dimension[dim].append(sig.normalised_value)

    # Average each dimension
    scores = {}
    for dim in DIMENSIONS:
        values = by_dimension[dim]
        if values:
            scores[dim] = sum(values) / len(values)
        else:
            scores[dim] = 0.0

    return scores


def calculate_fame_score(person_id: int, week: str) -> dict:
    """
    Calculate the composite fame score for a person in a given week.

    Returns both the headline score and the dimension breakdown.

    Args:
        person_id: Unique identifier for the person.
        week: ISO week string.

    Returns:
        Dict with keys:
        - "fame_score": float (0-100, the headline number)
        - "dim_search": float (0-100)
        - "dim_news": float (0-100)
        - "dim_social": float (0-100)
        - "dim_cultural": float (0-100)
        - "dim_institutional": float (0-100)
    """
    dim_scores = calculate_dimension_scores(person_id, week)

    # Apply private weights to produce headline score
    fame_score = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        fame_score += dim_scores.get(dim, 0.0) * weight

    # Clamp to 0-100
    fame_score = max(0.0, min(100.0, fame_score))

    # Calculate sentiment and controversy
    sentiment = analyse_sentiment(person_id, week)
    controversy = calculate_controversy(person_id, week)

    return {
        "fame_score": fame_score,
        "dim_search": dim_scores.get("search", 0.0),
        "dim_news": dim_scores.get("news", 0.0),
        "dim_social": dim_scores.get("social", 0.0),
        "dim_cultural": dim_scores.get("cultural", 0.0),
        "dim_institutional": dim_scores.get("institutional", 0.0),
        "sentiment_polarity": sentiment["polarity"],
        "controversy_index": controversy,
    }


def calculate_momentum(person_id: int, current_week: str) -> float:
    """
    Calculate week-on-week change in fame score.

    Args:
        person_id: Unique identifier for the person.
        current_week: ISO week string.

    Returns:
        Change in fame score from previous week. Positive = rising.
    """
    history = get_person_history(person_id, num_weeks=2)
    if len(history) < 2:
        return 0.0

    # history is most-recent-first
    current = history[0].fame_score
    previous = history[1].fame_score
    return current - previous


def score_all(week: str) -> list[dict]:
    """
    Calculate fame scores for all tracked persons in a given week.

    Args:
        week: ISO week string.

    Returns:
        List of score dicts (one per person), sorted by fame_score desc.
    """
    persons = get_all_persons(active_only=True)
    results = []

    for person in persons:
        score_data = calculate_fame_score(person.id, week)
        score_data["person_id"] = person.id
        score_data["week"] = week
        results.append(score_data)

    # Sort and assign ranks
    results.sort(key=lambda x: x["fame_score"], reverse=True)
    for i, entry in enumerate(results, 1):
        entry["rank"] = i

    return results


def rank(scores: list[dict]) -> list[tuple]:
    """
    Produce a ranked list from score dicts.

    Args:
        scores: List of score dicts with "person_id" and "fame_score".

    Returns:
        List of (person_id, score, rank) tuples, sorted by score descending.
    """
    sorted_scores = sorted(scores, key=lambda x: x["fame_score"], reverse=True)
    return [
        (s["person_id"], s["fame_score"], i + 1)
        for i, s in enumerate(sorted_scores)
    ]
