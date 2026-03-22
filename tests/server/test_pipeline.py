"""
Tests for the data pipeline orchestrator.

Uses mocked data sources to test the pipeline end-to-end without
making real API calls.
"""

from unittest.mock import patch, MagicMock

from server.data.pipeline import run_pipeline, _fetch_all_dimensions, _try_fetch


class TestTryFetch:
    def test_success_appends_signal(self):
        signals = []
        errors = []
        _try_fetch(signals, errors, "Test", "test_source", 1, "2026-W04",
                   lambda: 42.0)
        assert len(signals) == 1
        assert signals[0]["raw_value"] == 42.0
        assert signals[0]["source"] == "test_source"

    def test_failure_appends_error(self):
        signals = []
        errors = []
        _try_fetch(signals, errors, "Test", "test_source", 1, "2026-W04",
                   lambda: (_ for _ in ()).throw(Exception("boom")))
        assert len(signals) == 0
        assert len(errors) == 1
        assert "boom" in errors[0]


class TestFetchAllDimensions:
    @patch("server.data.pipeline.wiki_pageviews", return_value=150_000)
    @patch("server.data.pipeline.fetch_interest_for_week", return_value=45.0)
    @patch("server.data.pipeline.weekly_news_count", return_value=200)
    @patch("server.data.pipeline.weekly_article_count", return_value=30)
    @patch("server.data.pipeline.reddit_score", return_value=500.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 2.0})
    @patch("server.data.pipeline.weekly_youtube_score", return_value=100.0)
    @patch("server.data.pipeline.institutional_score", return_value=45.0)
    def test_collects_all_sources(self, *mocks):
        person = {"id": 1, "name": "Test", "wikipedia_title": "Test"}
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        # 8 sources (no spotify/tmdb without IDs)
        assert len(signals) == 8
        assert errors == []

        sources = {s["source"] for s in signals}
        assert "wikipedia_pageviews" in sources
        assert "google_trends" in sources
        assert "gdelt_count" in sources
        assert "reddit_score" in sources
        assert "wikidata_recognition" in sources

    @patch("server.data.pipeline.wiki_pageviews", return_value=150_000)
    @patch("server.data.pipeline.fetch_interest_for_week", return_value=45.0)
    @patch("server.data.pipeline.weekly_news_count", return_value=200)
    @patch("server.data.pipeline.weekly_article_count", return_value=30)
    @patch("server.data.pipeline.reddit_score", return_value=500.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 1.5})
    @patch("server.data.pipeline.weekly_youtube_score", return_value=50.0)
    @patch("server.data.pipeline.fetch_artist_popularity", return_value=85)
    @patch("server.data.pipeline.tmdb_popularity", return_value=120.0)
    @patch("server.data.pipeline.institutional_score", return_value=30.0)
    def test_includes_cultural_when_ids_present(self, *mocks):
        person = {
            "id": 1, "name": "Test", "wikipedia_title": "Test",
            "spotify_id": "abc123", "tmdb_id": 12345,
        }
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        # 10 sources (all including spotify + tmdb)
        assert len(signals) == 10
        sources = {s["source"] for s in signals}
        assert "spotify_popularity" in sources
        assert "tmdb_popularity" in sources

    @patch("server.data.pipeline.wiki_pageviews", side_effect=Exception("API down"))
    @patch("server.data.pipeline.fetch_interest_for_week", return_value=45.0)
    @patch("server.data.pipeline.weekly_news_count", return_value=200)
    @patch("server.data.pipeline.weekly_article_count", return_value=30)
    @patch("server.data.pipeline.reddit_score", return_value=500.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 1.0})
    @patch("server.data.pipeline.weekly_youtube_score", return_value=0.0)
    @patch("server.data.pipeline.institutional_score", return_value=0.0)
    def test_handles_source_failure(self, *mocks):
        person = {"id": 1, "name": "Test", "wikipedia_title": "Test"}
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        assert len(signals) == 7  # 8 - 1 failure
        assert len(errors) == 1
        assert "wikipedia_pageviews" in errors[0]


class TestRunPipeline:
    @patch("server.data.pipeline.init_db")
    @patch("server.data.pipeline.wiki_pageviews", return_value=100_000)
    @patch("server.data.pipeline.fetch_interest_for_week", return_value=50.0)
    @patch("server.data.pipeline.weekly_news_count", return_value=100)
    @patch("server.data.pipeline.weekly_article_count", return_value=20)
    @patch("server.data.pipeline.reddit_score", return_value=300.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 1.25})
    @patch("server.data.pipeline.weekly_youtube_score", return_value=50.0)
    @patch("server.data.pipeline.institutional_score", return_value=20.0)
    @patch("server.data.pipeline.upsert_signal")
    @patch("server.data.pipeline.get_historical_signals", return_value=[])
    def test_end_to_end(self, mock_hist, mock_upsert, *source_mocks):
        persons = [
            {"id": 1, "name": "Alice", "wikipedia_title": "Alice_(singer)"},
            {"id": 2, "name": "Bob", "wikipedia_title": "Bob_(actor)"},
        ]

        result = run_pipeline("2026-W04", persons=persons)

        assert result["persons_processed"] == 2
        assert result["signals_collected"] == 16  # 8 sources x 2 persons
        assert result["errors"] == []
        assert mock_upsert.call_count == 16
