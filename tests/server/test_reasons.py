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


class TestHeadline:
    """The number one must not also be named as the climber."""

    def test_top_person_is_not_reused_as_climber(self):
        from unittest.mock import MagicMock
        from server.blog.generator import _make_headline

        top = MagicMock()
        top.person_id = 1
        top.person.name = "Alice"

        # Alice is both number one and the biggest riser; Bob is next.
        movers = {"climbers": [(1, "Alice", 30.0), (2, "Bob", 20.0)], "fallers": []}
        headline = _make_headline(top, movers, [])
        assert headline.count("Alice") == 1, f"Alice named twice: {headline}"
        assert "Bob" in headline

    def test_falls_back_when_the_only_climber_is_the_top(self):
        from unittest.mock import MagicMock
        from server.blog.generator import _make_headline

        top = MagicMock()
        top.person_id = 1
        top.person.name = "Alice"
        movers = {"climbers": [(1, "Alice", 30.0)], "fallers": []}
        headline = _make_headline(top, movers, [])
        assert headline.count("Alice") == 1


class TestRosterDeduplication:
    """
    A person must not be promoted when we already track them under another name.

    "Vladimir Zelenskiy" was promoted alongside the existing "Volodymyr
    Zelenskyy" — the same Wikipedia article, the same human — and both were
    published, at #31 and #38 in the same month. Matching on the display name
    alone cannot catch that; the Wikipedia title is the real identity.
    """

    def test_normalisation_collapses_spelling_variants(self):
        import importlib.util, sys
        sys.path.insert(0, ".")
        spec = importlib.util.spec_from_file_location("roster", "scripts/roster.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

        # accents, punctuation and case must not create separate identities
        assert m._norm("Volodymyr Zelenskyy") == m._norm("volodymyr_zelenskyy")
        assert m._norm("Giorgia Meloni") == m._norm("Giorgia_Meloni")
        assert m._norm("Pedro Sánchez") == m._norm("Pedro Sanchez")
        assert m._norm("Charli D'Amelio") == m._norm("Charli Damelio")
        # genuinely different people must stay distinct
        assert m._norm("Mike Johnson") != m._norm("Boris Johnson")
        assert m._norm("Giorgia Meloni") != m._norm("Christopher Meloni")
