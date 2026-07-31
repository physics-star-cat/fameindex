"""
Tests for ISO week date utilities.
"""

from datetime import date

from server.data.week_utils import week_to_dates, date_to_week, previous_week, format_yyyymmdd


class TestWeekToDates:
    def test_known_week(self):
        # 2026-W04 should start on Monday 2026-01-19
        monday, sunday = week_to_dates("2026-W04")
        assert monday == date(2026, 1, 19)
        assert sunday == date(2026, 1, 25)

    def test_first_week(self):
        monday, sunday = week_to_dates("2026-W01")
        assert monday.weekday() == 0  # Monday
        assert sunday.weekday() == 6  # Sunday
        assert (sunday - monday).days == 6

    def test_week_53(self):
        # 2020 has 53 weeks
        monday, sunday = week_to_dates("2020-W53")
        assert monday.weekday() == 0
        assert (sunday - monday).days == 6


class TestDateToWeek:
    def test_roundtrip(self):
        monday, _ = week_to_dates("2026-W04")
        assert date_to_week(monday) == "2026-W04"

    def test_mid_week(self):
        # Wednesday of week 4, 2026
        wednesday = date(2026, 1, 21)
        assert date_to_week(wednesday) == "2026-W04"

    def test_sunday(self):
        # Sunday of week 4, 2026
        sunday = date(2026, 1, 25)
        assert date_to_week(sunday) == "2026-W04"


class TestPreviousWeek:
    def test_simple(self):
        assert previous_week("2026-W04") == "2026-W03"

    def test_year_boundary(self):
        result = previous_week("2026-W01")
        # 2025-W52 or 2025-W53 depending on the year
        assert result.startswith("2025-W")


class TestFormatYyyymmdd:
    def test_format(self):
        d = date(2026, 1, 19)
        assert format_yyyymmdd(d) == "20260119"

    def test_zero_padding(self):
        d = date(2026, 3, 5)
        assert format_yyyymmdd(d) == "20260305"


class TestPeriodToDates:
    """
    Periods generalise ISO weeks to quarters.

    The Fame Index publishes quarterly — fame moves too slowly for a weekly
    ranking to say much. Every data source already resolves a period to a
    (start, end) range before querying, so teaching this one function about
    quarters lets the whole pipeline fetch a quarter in a single call per
    source rather than thirteen.
    """

    def test_quarter_boundaries(self):
        from server.data.week_utils import period_to_dates
        from datetime import date
        assert period_to_dates("2026-Q1") == (date(2026, 1, 1), date(2026, 3, 31))
        assert period_to_dates("2026-Q2") == (date(2026, 4, 1), date(2026, 6, 30))
        assert period_to_dates("2026-Q3") == (date(2026, 7, 1), date(2026, 9, 30))
        assert period_to_dates("2026-Q4") == (date(2026, 10, 1), date(2026, 12, 31))

    def test_leap_year_q1(self):
        from server.data.week_utils import period_to_dates
        from datetime import date
        # 2024 is a leap year; Q1 still ends 31 March
        assert period_to_dates("2024-Q1") == (date(2024, 1, 1), date(2024, 3, 31))

    def test_still_accepts_iso_weeks(self):
        from server.data.week_utils import period_to_dates, week_to_dates
        assert period_to_dates("2026-W04") == week_to_dates("2026-W04")

    def test_rejects_nonsense(self):
        import pytest
        from server.data.week_utils import period_to_dates
        for bad in ["2026-Q5", "2026-Q0", "2026", "Q2-2026", "2026-X1"]:
            with pytest.raises(ValueError):
                period_to_dates(bad)


class TestQuarterHelpers:
    def test_date_to_quarter(self):
        from server.data.week_utils import date_to_quarter
        from datetime import date
        assert date_to_quarter(date(2026, 1, 1)) == "2026-Q1"
        assert date_to_quarter(date(2026, 3, 31)) == "2026-Q1"
        assert date_to_quarter(date(2026, 7, 31)) == "2026-Q3"
        assert date_to_quarter(date(2026, 12, 31)) == "2026-Q4"

    def test_previous_quarter(self):
        from server.data.week_utils import previous_quarter
        assert previous_quarter("2026-Q2") == "2026-Q1"
        assert previous_quarter("2026-Q1") == "2025-Q4"

    def test_last_complete_quarter_excludes_current(self):
        from server.data.week_utils import last_complete_quarter
        from datetime import date
        # Mid-Q3: the latest quarter that has fully elapsed is Q2
        assert last_complete_quarter(date(2026, 7, 31)) == "2026-Q2"
        # First day of Q1: previous year's Q4
        assert last_complete_quarter(date(2026, 1, 1)) == "2025-Q4"
        # Last day of Q2: Q2 is not yet over, so Q1
        assert last_complete_quarter(date(2026, 6, 30)) == "2026-Q1"
