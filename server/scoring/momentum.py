"""
Momentum calculation for the Fame Index.

Momentum measures the week-on-week change in a person's fame score.
High momentum indicates someone is rapidly gaining or losing public attention,
regardless of their absolute fame level.

Note: The primary momentum calculation now lives in engine.py.
This module provides the "biggest movers" analysis used by the blog generator.
"""

from server.db.queries import get_scores_for_week, get_all_persons, get_person_history


def biggest_movers(week: str, n: int = 10) -> dict:
    """
    Find the biggest climbers and fallers for a given week.

    Args:
        week: ISO week string.
        n: Number of movers to return in each direction.

    Returns:
        Dict with keys "climbers" and "fallers", each containing a list
        of (person_id, name, momentum) tuples sorted by magnitude.
    """
    # Read the stored momentum for this period directly.
    #
    # This previously walked get_person_history(num_weeks=2) and required
    # history[0].week == week. That ordering is week DESCENDING AS A STRING, so
    # with both weeks and quarters in the table "2026-W13" sorts above
    # "2026-Q2" ('W' follows 'Q'). history[0] was therefore never the requested
    # period, every person was skipped, and the climbers and fallers sections
    # vanished from every post without any error being raised.
    movers = [
        (sc.person_id, sc.person.name, sc.momentum)
        for sc in get_scores_for_week(week)
        if sc.momentum
    ]

    # Sort by momentum
    movers.sort(key=lambda x: x[2], reverse=True)

    climbers = [(pid, name, m) for pid, name, m in movers if m > 0][:n]
    fallers = [(pid, name, m) for pid, name, m in movers if m < 0]
    fallers.sort(key=lambda x: x[2])  # Most negative first
    fallers = fallers[:n]

    return {"climbers": climbers, "fallers": fallers}
