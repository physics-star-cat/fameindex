"""
Controversy index for the Fame Index.

The controversy index is a derived metric that identifies when someone is
famous primarily *because* of controversy. It combines high attention volume
with polarised sentiment — lots of people talking, and they strongly disagree.

A high controversy index doesn't mean someone is bad. It means they are
divisive. The public is paying attention AND has strong opposing opinions.

Formula:
    controversy = attention_factor * polarisation_factor * 100

Where:
    attention_factor = normalised fame score / 100 (0-1)
    polarisation_factor = 1 - neutral_proportion (0-1, higher = more polarised)

A person with high fame and evenly split positive/negative sentiment
scores high. A person with high fame but uniformly positive sentiment
scores low. A person with low fame scores low regardless of sentiment.
"""

import logging

from server.scoring.sentiment import analyse_sentiment
from server.db.queries import get_signals_for_person_week

logger = logging.getLogger(__name__)


def calculate_controversy(person_id: int, week: str) -> float:
    """
    Calculate the controversy index for a person in a given week.

    High controversy = high attention + polarised sentiment.
    Low controversy = either low attention, or high attention with
    uniform sentiment (everyone agrees).

    Args:
        person_id: Unique identifier for the person.
        week: ISO week string.

    Returns:
        A float between 0 and 100 representing controversy level.
    """
    # Get attention level from signal volume
    attention = _attention_factor(person_id, week)

    # Get sentiment polarisation
    sentiment = analyse_sentiment(person_id, week)
    polarisation = _polarisation_factor(sentiment)

    # Controversy requires both high attention AND polarised sentiment
    controversy = attention * polarisation * 100.0

    return round(max(0.0, min(100.0, controversy)), 1)


def _attention_factor(person_id: int, week: str) -> float:
    """
    Calculate how much attention a person is receiving (0-1).

    Uses the average normalised signal value as a proxy for overall
    attention level.
    """
    signals = get_signals_for_person_week(person_id, week)
    if not signals:
        return 0.0

    norm_values = [s.normalised_value for s in signals]
    avg = sum(norm_values) / len(norm_values)

    # Scale to 0-1
    return max(0.0, min(1.0, avg / 100.0))


def _polarisation_factor(sentiment: dict) -> float:
    """
    Calculate how polarised the sentiment is (0-1).

    High polarisation = low neutral proportion AND balanced positive/negative.
    The most controversial case is 50% positive, 50% negative, 0% neutral.
    """
    neutral = sentiment.get("neutral", 1.0)
    positive = sentiment.get("positive", 0.0)
    negative = sentiment.get("negative", 0.0)

    # Polarisation increases as neutral decreases
    non_neutral = 1.0 - neutral

    # Balance factor: controversy is highest when positive and negative
    # are roughly equal. If everyone agrees (all positive or all negative),
    # that's not controversial, just famous-and-liked or famous-and-disliked.
    if positive + negative > 0:
        balance = 1.0 - abs(positive - negative) / (positive + negative)
    else:
        balance = 0.0

    # Combine: need both non-neutral sentiment AND balanced disagreement
    return non_neutral * balance
