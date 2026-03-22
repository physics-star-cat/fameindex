"""
Momentum calculation for the Fame Index.

Momentum measures the week-on-week change in a person's fame score.
High momentum indicates someone is rapidly gaining or losing public attention,
regardless of their absolute fame level.

Note: The primary momentum calculation now lives in engine.py.
This module provides the "biggest movers" analysis used by the blog generator.
"""

from server.db.queries import get_all_persons, get_person_history


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
    persons = get_all_persons(active_only=True)
    movers = []

    for person in persons:
        history = get_person_history(person.id, num_weeks=2)
        if len(history) < 2:
            continue

        current = history[0]
        previous = history[1]

        if current.week != week:
            continue

        momentum = current.fame_score - previous.fame_score
        movers.append((person.id, person.name, momentum))

    # Sort by momentum
    movers.sort(key=lambda x: x[2], reverse=True)

    climbers = [(pid, name, m) for pid, name, m in movers if m > 0][:n]
    fallers = [(pid, name, m) for pid, name, m in movers if m < 0]
    fallers.sort(key=lambda x: x[2])  # Most negative first
    fallers = fallers[:n]

    return {"climbers": climbers, "fallers": fallers}
