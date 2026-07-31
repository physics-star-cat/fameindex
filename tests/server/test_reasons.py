"""
Reasons must be derived from signals, never invented.

The previous generator drew commentary from random.choice pools, which put
"The streaming numbers don't lie" on two different people in the same post and
credited Spotify, a signal the pipeline does not collect.
"""

from unittest.mock import patch, MagicMock

from server.blog.reasons import biggest_mover, describe_move


def _sig(source, value):
    return MagicMock(source=source, raw_value=value)


def _mock_signals(now, before):
    """Return a side_effect that serves `now` for P2 and `before` for P1."""
    def _inner(person_id, period):
        data = now if period == "2026-Q2" else before
        return [_sig(s, v) for s, v in data.items()]
    return _inner


class TestBiggestMover:
    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_picks_the_largest_swing_not_the_first(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"wikipedia_pageviews": 300, "gdelt_count": 110},
            before={"wikipedia_pageviews": 100, "gdelt_count": 100},
        )
        assert biggest_mover(1, "2026-Q2", "2026-Q1")["source"] == "wikipedia_pageviews"

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_detects_large_falls_as_well_as_rises(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"gdelt_count": 10}, before={"gdelt_count": 100},
        )
        m = biggest_mover(1, "2026-Q2", "2026-Q1")
        assert m["source"] == "gdelt_count"
        assert m["ratio"] < 1

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_ignores_noise(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"gdelt_count": 103}, before={"gdelt_count": 100},
        )
        assert biggest_mover(1, "2026-Q2", "2026-Q1") is None

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_skips_signals_missing_from_either_period(self, mock_get):
        # reddit exists now but not before — backfilled periods omit it, and its
        # absence is not evidence of a change.
        mock_get.side_effect = _mock_signals(
            now={"reddit_score": 900, "gdelt_count": 100},
            before={"gdelt_count": 100},
        )
        assert biggest_mover(1, "2026-Q2", "2026-Q1") is None

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_ignores_division_by_zero(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"gdelt_count": 50}, before={"gdelt_count": 0},
        )
        assert biggest_mover(1, "2026-Q2", "2026-Q1") is None


class TestDescribeMove:
    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_names_the_actual_signal(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"wikipedia_pageviews": 300}, before={"wikipedia_pageviews": 100},
        )
        text = describe_move(1, "2026-Q2", "2026-Q1", rising=True)
        assert "Wikipedia traffic" in text
        assert "tripled" in text

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_describes_a_halving(self, mock_get):
        mock_get.side_effect = _mock_signals(
            now={"gdelt_count": 50}, before={"gdelt_count": 100},
        )
        assert describe_move(1, "2026-Q2", "2026-Q1", rising=False) == "news mentions halved"

    @patch("server.blog.reasons.get_signals_for_person_week")
    def test_silence_when_nothing_moved(self, mock_get):
        # The honest output is None. The old generator always produced a reason.
        mock_get.side_effect = _mock_signals(
            now={"gdelt_count": 101}, before={"gdelt_count": 100},
        )
        assert describe_move(1, "2026-Q2", "2026-Q1", rising=True) is None
