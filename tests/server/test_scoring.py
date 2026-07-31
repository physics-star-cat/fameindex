"""
Tests for the scoring engine.

Tests the dimension scoring and fame score calculation logic.
"""

import pytest
from unittest.mock import patch, MagicMock

from server.scoring.engine import calculate_dimension_scores, calculate_fame_score, rank


class TestCalculateDimensionScores:
    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_averages_signals_per_dimension(self, mock_signals):
        # Create mock signals
        sig1 = MagicMock(dimension="search", normalised_value=80.0)
        sig2 = MagicMock(dimension="search", normalised_value=60.0)
        sig3 = MagicMock(dimension="news", normalised_value=50.0)
        mock_signals.return_value = [sig1, sig2, sig3]

        scores = calculate_dimension_scores(1, "2026-W04")

        assert scores["search"] == 70.0  # avg(80, 60)
        assert scores["news"] == 50.0
        assert scores["social"] == 0.0  # no signals
        assert scores["cultural"] == 0.0
        assert scores["institutional"] == 0.0

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_empty_signals_returns_zeros(self, mock_signals):
        mock_signals.return_value = []
        scores = calculate_dimension_scores(1, "2026-W04")
        for dim in scores.values():
            assert dim == 0.0


class TestCalculateFameScore:
    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_fame_score_within_bounds(self, mock_signals):
        # All dimensions at 100
        sigs = []
        for dim in ["search", "news", "social", "cultural", "institutional"]:
            sig = MagicMock(dimension=dim, normalised_value=100.0)
            sigs.append(sig)
        mock_signals.return_value = sigs

        result = calculate_fame_score(1, "2026-W04")
        assert 0 <= result["fame_score"] <= 100

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_all_100_gives_100(self, mock_signals):
        sigs = []
        for dim in ["search", "news", "social", "cultural", "institutional"]:
            sig = MagicMock(dimension=dim, normalised_value=100.0)
            sigs.append(sig)
        mock_signals.return_value = sigs

        result = calculate_fame_score(1, "2026-W04")
        assert result["fame_score"] == 100.0

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_all_zero_gives_zero(self, mock_signals):
        mock_signals.return_value = []
        result = calculate_fame_score(1, "2026-W04")
        assert result["fame_score"] == 0.0

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_returns_dimension_breakdown(self, mock_signals):
        sig = MagicMock(dimension="search", normalised_value=75.0)
        mock_signals.return_value = [sig]

        result = calculate_fame_score(1, "2026-W04")
        assert "dim_search" in result
        assert "dim_news" in result
        assert "dim_social" in result
        assert "dim_cultural" in result
        assert "dim_institutional" in result
        assert result["dim_search"] == 75.0


class TestRank:
    def test_ranks_by_score_descending(self):
        scores = [
            {"person_id": 1, "fame_score": 50.0},
            {"person_id": 2, "fame_score": 80.0},
            {"person_id": 3, "fame_score": 65.0},
        ]
        ranked = rank(scores)
        assert ranked[0] == (2, 80.0, 1)
        assert ranked[1] == (3, 65.0, 2)
        assert ranked[2] == (1, 50.0, 3)

    def test_empty_list(self):
        assert rank([]) == []


class TestWeightRenormalisation:
    """
    Dimension weights are re-normalised across dimensions that actually carry
    signals.

    Two reasons this matters:

    1. `cultural` has never had a single signal in the database — Spotify and
       TMDB were never collected — so 15% of every fame score was silently zero.
    2. Backfilled weeks omit Reddit and YouTube, which cannot be fetched
       retroactively. Without re-normalisation those weeks would score lower
       than live weeks purely because of missing inputs, and every person would
       appear to crash in W14 and recover in W31.
    """

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_missing_dimension_does_not_deflate_score(self, mock_signals):
        # Only search and news present, both perfect. Present dimensions are
        # perfect, so the score should be 100 — not 55 (0.30 + 0.25).
        sigs = [
            MagicMock(dimension="search", normalised_value=100.0),
            MagicMock(dimension="news", normalised_value=100.0),
        ]
        mock_signals.return_value = sigs
        result = calculate_fame_score(1, "2026-W18")
        assert result["fame_score"] == 100.0

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_relative_standing_preserved_across_signal_sets(self, mock_signals):
        # A person scoring 80 on every available dimension should score 80
        # whether six signals or eight were collected. This is the property
        # that makes backfilled weeks comparable to live ones.
        full = [MagicMock(dimension=d, normalised_value=80.0)
                for d in ["search", "news", "social", "cultural", "institutional"]]
        mock_signals.return_value = full
        full_score = calculate_fame_score(1, "2026-W31")["fame_score"]

        partial = [MagicMock(dimension=d, normalised_value=80.0)
                   for d in ["search", "news", "institutional"]]
        mock_signals.return_value = partial
        partial_score = calculate_fame_score(1, "2026-W18")["fame_score"]

        assert full_score == pytest.approx(80.0)
        assert partial_score == pytest.approx(80.0)

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_weights_still_apply_between_present_dimensions(self, mock_signals):
        # Re-normalisation must not flatten the weighting. search (0.30) and
        # institutional (0.10) re-normalise to 0.75 / 0.25.
        sigs = [
            MagicMock(dimension="search", normalised_value=100.0),
            MagicMock(dimension="institutional", normalised_value=0.0),
        ]
        mock_signals.return_value = sigs
        result = calculate_fame_score(1, "2026-W18")
        assert result["fame_score"] == pytest.approx(75.0)

    @patch("server.scoring.engine.get_signals_for_person_week")
    def test_no_signals_still_zero(self, mock_signals):
        # Nothing present means nothing to re-normalise; must not divide by zero.
        mock_signals.return_value = []
        result = calculate_fame_score(1, "2026-W18")
        assert result["fame_score"] == 0.0
