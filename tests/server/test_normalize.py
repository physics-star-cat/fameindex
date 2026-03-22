"""
Tests for the data normalisation layer.
"""

from server.data.normalize import (
    normalize_signal, normalize_batch, get_dimension,
    _clamp, _log_scale, _log_ratio_scale,
)


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_range(self):
        assert _clamp(-10.0) == 0.0

    def test_above_range(self):
        assert _clamp(150.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


class TestLogScale:
    def test_zero_returns_zero(self):
        assert _log_scale(0, floor=100, ceiling=5_000_000) == 0.0

    def test_below_floor_returns_zero(self):
        assert _log_scale(50, floor=100, ceiling=5_000_000) == 0.0

    def test_at_ceiling_returns_100(self):
        assert _log_scale(5_000_000, floor=100, ceiling=5_000_000) == 100.0

    def test_above_ceiling_returns_100(self):
        assert _log_scale(10_000_000, floor=100, ceiling=5_000_000) == 100.0

    def test_mid_range_is_between_0_and_100(self):
        result = _log_scale(50_000, floor=100, ceiling=5_000_000)
        assert 0 < result < 100

    def test_higher_value_gives_higher_score(self):
        low = _log_scale(10_000, floor=100, ceiling=5_000_000)
        high = _log_scale(1_000_000, floor=100, ceiling=5_000_000)
        assert high > low

    def test_historical_adapts_ceiling(self):
        without_hist = _log_scale(3_000_000, floor=100, ceiling=5_000_000)
        with_hist = _log_scale(3_000_000, floor=100, ceiling=5_000_000,
                               historical=[10_000_000])
        assert with_hist < without_hist


class TestLogRatioScale:
    def test_neutral_returns_50(self):
        assert _log_ratio_scale(1.0, neutral=1.0, max_ratio=20.0) == 50.0

    def test_zero_returns_zero(self):
        assert _log_ratio_scale(0, neutral=1.0, max_ratio=20.0) == 0.0

    def test_max_ratio_returns_100(self):
        assert _log_ratio_scale(20.0, neutral=1.0, max_ratio=20.0) == 100.0

    def test_above_neutral_is_above_50(self):
        result = _log_ratio_scale(5.0, neutral=1.0, max_ratio=20.0)
        assert 50 < result < 100

    def test_below_neutral_is_below_50(self):
        result = _log_ratio_scale(0.5, neutral=1.0, max_ratio=20.0)
        assert 0 < result < 50

    def test_higher_ratio_gives_higher_score(self):
        low = _log_ratio_scale(2.0, neutral=1.0, max_ratio=20.0)
        high = _log_ratio_scale(10.0, neutral=1.0, max_ratio=20.0)
        assert high > low


class TestNormalizeSignal:
    def test_wikipedia_pageviews(self):
        result = normalize_signal(500_000, "wikipedia_pageviews")
        assert 0 < result < 100

    def test_google_trends_passthrough(self):
        assert normalize_signal(75.0, "google_trends") == 75.0

    def test_google_trends_clamps(self):
        assert normalize_signal(150.0, "google_trends") == 100.0

    def test_gdelt_count(self):
        result = normalize_signal(500, "gdelt_count")
        assert 0 < result < 100

    def test_google_news_count(self):
        result = normalize_signal(50, "google_news_count")
        assert 0 < result < 100

    def test_reddit_score(self):
        result = normalize_signal(200, "reddit_score")
        assert 0 < result < 100

    def test_wiki_edit_velocity_neutral(self):
        assert normalize_signal(1.0, "wiki_edit_velocity") == 50.0

    def test_youtube_score(self):
        result = normalize_signal(500, "youtube_score")
        assert 0 < result < 100

    def test_spotify_popularity_passthrough(self):
        assert normalize_signal(85.0, "spotify_popularity") == 85.0

    def test_tmdb_popularity(self):
        result = normalize_signal(50.0, "tmdb_popularity")
        assert 0 < result < 100

    def test_wikidata_recognition(self):
        result = normalize_signal(100, "wikidata_recognition")
        assert 0 < result < 100

    def test_unknown_type_returns_zero(self):
        assert normalize_signal(100.0, "unknown_source") == 0.0


class TestGetDimension:
    def test_search_sources(self):
        assert get_dimension("wikipedia_pageviews") == "search"
        assert get_dimension("google_trends") == "search"

    def test_news_sources(self):
        assert get_dimension("gdelt_count") == "news"
        assert get_dimension("google_news_count") == "news"

    def test_social_sources(self):
        assert get_dimension("reddit_score") == "social"
        assert get_dimension("wiki_edit_velocity") == "social"
        assert get_dimension("youtube_score") == "social"

    def test_cultural_sources(self):
        assert get_dimension("spotify_popularity") == "cultural"
        assert get_dimension("tmdb_popularity") == "cultural"

    def test_institutional_sources(self):
        assert get_dimension("wikidata_recognition") == "institutional"

    def test_unknown_source(self):
        assert get_dimension("fake_source") == "unknown"


class TestNormalizeBatch:
    def test_adds_normalised_value_and_dimension(self):
        signals = [
            {"person_id": 1, "source": "wikipedia_pageviews", "raw_value": 100_000.0},
            {"person_id": 1, "source": "google_trends", "raw_value": 60.0},
            {"person_id": 1, "source": "gdelt_count", "raw_value": 500.0},
        ]
        result = normalize_batch(signals)
        for sig in result:
            assert "normalised_value" in sig
            assert "dimension" in sig
            assert 0 <= sig["normalised_value"] <= 100

    def test_correct_dimensions_assigned(self):
        signals = [
            {"person_id": 1, "source": "wikipedia_pageviews", "raw_value": 50_000.0},
            {"person_id": 1, "source": "reddit_score", "raw_value": 100.0},
            {"person_id": 1, "source": "spotify_popularity", "raw_value": 80.0},
        ]
        result = normalize_batch(signals)
        assert result[0]["dimension"] == "search"
        assert result[1]["dimension"] == "social"
        assert result[2]["dimension"] == "cultural"
