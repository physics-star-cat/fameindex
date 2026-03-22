"""
ISO week date utilities.

Converts between ISO week strings (e.g. "2026-W04") and date ranges
needed by the various data source APIs.
"""

from datetime import date, timedelta


def week_to_dates(week: str) -> tuple[date, date]:
    """
    Convert an ISO week string to a (start_date, end_date) tuple.

    The week starts on Monday and ends on Sunday.

    Args:
        week: ISO week string, e.g. "2026-W04".

    Returns:
        Tuple of (monday, sunday) as date objects.
    """
    year, week_num = week.split("-W")
    year = int(year)
    week_num = int(week_num)

    # Jan 4 is always in ISO week 1
    jan4 = date(year, 1, 4)
    # Find the Monday of week 1
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    # Offset to target week
    monday = week1_monday + timedelta(weeks=week_num - 1)
    sunday = monday + timedelta(days=6)

    return monday, sunday


def date_to_week(d: date) -> str:
    """
    Convert a date to its ISO week string.

    Args:
        d: A date object.

    Returns:
        ISO week string, e.g. "2026-W04".
    """
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def previous_week(week: str) -> str:
    """Get the ISO week string for the week before the given one."""
    monday, _ = week_to_dates(week)
    prev_monday = monday - timedelta(weeks=1)
    return date_to_week(prev_monday)


def format_yyyymmdd(d: date) -> str:
    """Format a date as YYYYMMDD (used by Wikimedia API)."""
    return d.strftime("%Y%m%d")
