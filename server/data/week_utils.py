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


# --- Quarterly periods -------------------------------------------------------
#
# The Fame Index publishes quarterly: fame moves too slowly for a weekly ranking
# to say much, and a quarter-long aggregate is far less noisy than a sampled
# week. Every data source resolves a period to a (start, end) range before
# querying, so supporting quarters here lets the whole pipeline fetch a quarter
# in one call per source instead of thirteen.

_QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def period_to_dates(period: str) -> tuple[date, date]:
    """
    Convert a period string to a (start_date, end_date) tuple.

    Accepts both quarters ("2026-Q2") and ISO weeks ("2026-W04"), so callers
    that still work in weeks keep working.

    Raises:
        ValueError: if the period is neither a valid quarter nor a valid week.
    """
    if "-M" in period:
        year_str, m_str = period.split("-M", 1)
        try:
            year, month = int(year_str), int(m_str)
        except ValueError:
            raise ValueError(f"Malformed month: {period!r}")
        if not 1 <= month <= 12:
            raise ValueError(f"Month must be 1-12, got {period!r}")
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return start, end

    if "-Q" in period:
        year_str, q_str = period.split("-Q", 1)
        try:
            year, quarter = int(year_str), int(q_str)
        except ValueError:
            raise ValueError(f"Malformed quarter: {period!r}")
        if quarter not in _QUARTER_MONTHS:
            raise ValueError(f"Quarter must be 1-4, got {period!r}")
        first_month, last_month = _QUARTER_MONTHS[quarter]
        start = date(year, first_month, 1)
        # First day of the following month, minus a day
        if last_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, last_month + 1, 1) - timedelta(days=1)
        return start, end

    if "-W" in period:
        return week_to_dates(period)

    raise ValueError(f"Unrecognised period: {period!r} (expected YYYY-Qn or YYYY-Wnn)")


def date_to_quarter(d: date) -> str:
    """Convert a date to its quarter string, e.g. '2026-Q3'."""
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def previous_quarter(period: str) -> str:
    """The quarter before the given one, rolling back across year boundaries."""
    year_str, q_str = period.split("-Q", 1)
    year, quarter = int(year_str), int(q_str)
    if quarter == 1:
        return f"{year - 1}-Q4"
    return f"{year}-Q{quarter - 1}"


def last_complete_quarter(today: date | None = None) -> str:
    """
    The most recent quarter that has fully elapsed.

    The current quarter is deliberately excluded: it is still accruing, and a
    partial quarter ranked as if complete would show everyone crashing.
    """
    d = today or date.today()
    return previous_quarter(date_to_quarter(d))


def previous_period(period: str) -> str:
    """
    The period preceding the given one, for either quarters or ISO weeks.

    Used wherever a source compares a period against its predecessor — notably
    wiki edit velocity, which is a ratio of this period's revisions to last
    period's.
    """
    if "-M" in period:
        return previous_month(period)
    if "-Q" in period:
        return previous_quarter(period)
    if "-W" in period:
        return previous_week(period)
    raise ValueError(f"Unrecognised period: {period!r}")


# --- Monthly periods -------------------------------------------------------
#
# The index publishes monthly. Quarterly proved too infrequent for a site whose
# appeal is watching fame move. The internal form is "2026-M07": it sorts
# correctly, cannot be confused with a week or a quarter, and matches the
# existing shape. It is shown to readers as "Jul-2026".

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def date_to_month(d: date) -> str:
    """Convert a date to its month period, e.g. '2026-M07'."""
    return f"{d.year}-M{d.month:02d}"


def previous_month(period: str) -> str:
    """The month before the given one, rolling back across year boundaries."""
    year_str, m_str = period.split("-M", 1)
    year, month = int(year_str), int(m_str)
    if month == 1:
        return f"{year - 1}-M12"
    return f"{year}-M{month - 1:02d}"


def last_complete_month(today: date | None = None) -> str:
    """
    The most recent month that has fully elapsed.

    The current month is excluded because it is still accruing; ranking a
    part-month as if complete would show everyone crashing. Running on the 1st
    therefore publishes the month that just ended, which is the intended cadence.
    """
    d = today or date.today()
    return previous_month(date_to_month(d))


def format_period(period: str) -> str:
    """
    Human form of a period identifier.

    Months render as "Jul-2026"; other period types are already readable and
    pass through unchanged.
    """
    if "-M" in period:
        year_str, m_str = period.split("-M", 1)
        try:
            return f"{_MONTH_ABBR[int(m_str) - 1]}-{year_str}"
        except (ValueError, IndexError):
            return period
    return period
