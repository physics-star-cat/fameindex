"""
Institutional scores are cached because awards barely move.

The 2026 backfill made 896 SPARQL calls (7 months x 128 people) to learn 128
facts. It was the slowest signal and the main source of the intermittent
failures fill_gaps.py kept repairing.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from server.data.sources import wikidata_cache as wc


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(wc, "DB_PATH", tmp_path / "test.db")
    yield


class TestCaching:
    def test_second_call_does_not_hit_the_network(self):
        with patch("server.data.sources.wikidata.institutional_score",
                   return_value=42.0) as fetch:
            assert wc.institutional_score_cached("Someone") == 42.0
            assert wc.institutional_score_cached("Someone") == 42.0
            assert fetch.call_count == 1, "second call should be served from cache"

    def test_expired_entries_are_refetched(self):
        wc.put("Someone", 10.0)
        # Backdate the entry beyond the freshness window
        con = sqlite3.connect(wc.DB_PATH)
        old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        con.execute("UPDATE wikidata_cache SET fetched_at=?", (old,))
        con.commit(); con.close()

        with patch("server.data.sources.wikidata.institutional_score",
                   return_value=99.0) as fetch:
            assert wc.institutional_score_cached("Someone") == 99.0
            assert fetch.call_count == 1

    def test_falls_back_to_stale_when_refetch_fails(self):
        """
        A stale award count is far closer to the truth than no signal at all.

        Without a signal the person is missing an entire dimension, and the
        scoring engine then ranks them under different weightings from everyone
        else in the same table.
        """
        wc.put("Someone", 55.0)
        con = sqlite3.connect(wc.DB_PATH)
        old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        con.execute("UPDATE wikidata_cache SET fetched_at=?", (old,))
        con.commit(); con.close()

        with patch("server.data.sources.wikidata.institutional_score",
                   side_effect=RuntimeError("SPARQL timeout")):
            assert wc.institutional_score_cached("Someone") == 55.0

    def test_raises_when_there_is_nothing_usable(self):
        # No cache entry and the fetch failed: record no signal rather than
        # invent a zero.
        with patch("server.data.sources.wikidata.institutional_score",
                   side_effect=RuntimeError("SPARQL timeout")):
            with pytest.raises(RuntimeError):
                wc.institutional_score_cached("Nobody")

    def test_put_overwrites_rather_than_duplicating(self):
        wc.put("Someone", 1.0)
        wc.put("Someone", 2.0)
        assert wc.get_cached("Someone") == 2.0
        assert wc.stats()["total"] == 1
