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
