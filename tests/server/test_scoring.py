"""
Tests for the scoring engine.

Tests the dimension scoring and fame score calculation logic.
"""

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
