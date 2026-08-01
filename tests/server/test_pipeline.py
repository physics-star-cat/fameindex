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
    @patch("server.data.pipeline.institutional_score_cached", return_value=45.0)
    def test_collects_all_sources(self, *mocks):
        person = {"id": 1, "name": "Test", "wikipedia_title": "Test"}
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        # 6 sources: google_trends disabled, and news is supplied in bulk
        # by run_pipeline via BigQuery rather than fetched per person.
        assert len(signals) == 6
        assert errors == []

        sources = {s["source"] for s in signals}
        assert "wikipedia_pageviews" in sources
        # google_trends is deliberately absent — pytrends is blocked by Google
        # and returned 121/121 zeros. See pipeline.ENABLE_GOOGLE_TRENDS.
        assert "google_trends" not in sources
        assert "gdelt_count" not in sources  # bulk-supplied, see news_counts
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
    @patch("server.data.pipeline.institutional_score_cached", return_value=30.0)
    def test_includes_cultural_when_ids_present(self, *mocks):
        person = {
            "id": 1, "name": "Test", "wikipedia_title": "Test",
            "spotify_id": "abc123", "tmdb_id": 12345,
        }
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        # 10 sources (all including spotify + tmdb)
        assert len(signals) == 8  # google_trends disabled; news bulk-supplied
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
    @patch("server.data.pipeline.institutional_score_cached", return_value=0.0)
    def test_handles_source_failure(self, *mocks):
        person = {"id": 1, "name": "Test", "wikipedia_title": "Test"}
        errors = []
        signals = _fetch_all_dimensions(person, "2026-W04", errors)

        assert len(signals) == 5  # 6 - 1 failure
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
    @patch("server.data.pipeline.institutional_score_cached", return_value=20.0)
    @patch("server.data.pipeline.upsert_signal")
    @patch("server.data.pipeline.get_historical_signals", return_value=[])
    def test_end_to_end(self, mock_hist, mock_upsert, *source_mocks):
        persons = [
            {"id": 1, "name": "Alice", "wikipedia_title": "Alice_(singer)"},
            {"id": 2, "name": "Bob", "wikipedia_title": "Bob_(actor)"},
        ]

        result = run_pipeline("2026-W04", persons=persons)

        assert result["persons_processed"] == 2
        assert result["signals_collected"] == 14  # 2 persons x 7 sources
        assert result["errors"] == []
        assert mock_upsert.call_count == 14


class TestBulkNewsCounts:
    """
    News is fetched once for the whole roster, not per person.

    The GDELT DOC API rate-limits per request and cost roughly 60 seconds per
    person in exponential backoff. BigQuery answers for all 121 people in one
    ~1 GB query, so run_pipeline pre-fetches and passes the mapping down.
    """

    @patch("server.data.pipeline.institutional_score_cached", return_value=45.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 1.2})
    @patch("server.data.pipeline.wiki_pageviews", return_value=150000)
    def test_uses_supplied_count(self, *mocks):
        person = {"id": 1, "name": "Someone", "wikipedia_title": "Someone"}
        errors = []
        signals = _fetch_all_dimensions(
            person, "2026-Q2", errors, historical_only=True,
            news_counts={"Someone": 4321})
        news = [s for s in signals if s["source"] == "gdelt_count"]
        assert len(news) == 1
        assert news[0]["raw_value"] == 4321.0

    @patch("server.data.pipeline.institutional_score_cached", return_value=45.0)
    @patch("server.data.pipeline.fetch_mention_velocity", return_value={"velocity": 1.2})
    @patch("server.data.pipeline.wiki_pageviews", return_value=150000)
    def test_absent_name_records_no_signal(self, *mocks):
        # Not mentioned, or the bulk fetch failed — either way we must not
        # invent a zero. That fabrication is what made the first backfill
        # worthless.
        person = {"id": 1, "name": "Nobody", "wikipedia_title": "Nobody"}
        errors = []
        signals = _fetch_all_dimensions(
            person, "2026-Q2", errors, historical_only=True,
            news_counts={"Someone Else": 10})
        assert not [s for s in signals if s["source"] == "gdelt_count"]
