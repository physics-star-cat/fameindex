"""
GDELT must fail loudly rather than returning a fabricated zero.

A rate-limited fetch that returns 0 is indistinguishable from "nobody wrote
about this person". The pipeline stores it as fact and rankings move because of
it. Since the scoring engine re-normalises over whichever signals are present,
a missing signal is far cheaper than a false one.
"""

import time
from unittest.mock import patch, MagicMock

import pytest
import requests

from server.data.sources.gdelt import fetch_news_count


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400:
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(f"{status}")
    else:
        r.raise_for_status.return_value = None
    return r


class TestGdeltFailsLoudly:
    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_rate_limit_raises_rather_than_returning_zero(self, mock_get):
        mock_get.return_value = _resp(429)
        with pytest.raises(requests.exceptions.RequestException):
            fetch_news_count("Someone", "20260401", "20260630")

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_server_error_raises(self, mock_get):
        mock_get.return_value = _resp(503)
        with pytest.raises(requests.exceptions.RequestException):
            fetch_news_count("Someone", "20260401", "20260630")

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_retries_then_succeeds(self, mock_get):
        # MAX_ATTEMPTS is 2, so one failure then a success is the retry path.
        ok = _resp(200, {"timeline": [{"data": [{"value": 7}, {"value": 3}]}]})
        mock_get.side_effect = [_resp(429), ok]
        assert fetch_news_count("Someone", "20260401", "20260630") == 10
        assert mock_get.call_count == 2

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_genuine_zero_is_still_zero(self, mock_get):
        # An empty timeline is a real answer, not a failure.
        mock_get.return_value = _resp(200, {"timeline": []})
        assert fetch_news_count("Someone", "20260401", "20260630") == 0


class TestCircuitBreaker:
    """
    A blocked GDELT must not cost the whole run.

    When GDELT blocks an IP it stays blocked for a while. Without a breaker, a
    121-person backfill spends ~2 minutes per person in exponential backoff and
    then fails anyway — four hours of sleeping to collect nothing. After a run
    of consecutive failures we stop asking and let the scoring engine
    re-normalise over the signals that did arrive.
    """

    def setup_method(self):
        from server.data.sources import gdelt
        gdelt.reset_circuit()

    def teardown_method(self):
        from server.data.sources import gdelt
        gdelt.reset_circuit()

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_opens_after_repeated_failures_and_stops_calling(self, mock_get):
        from server.data.sources.gdelt import GdeltUnavailable
        mock_get.return_value = _resp(429)

        for _ in range(8):
            with pytest.raises(requests.exceptions.RequestException):
                fetch_news_count("Someone", "20260401", "20260630")
        calls_before = mock_get.call_count

        # Circuit is now open: further calls fail immediately without hitting the network
        with pytest.raises(GdeltUnavailable):
            fetch_news_count("Another", "20260401", "20260630")
        assert mock_get.call_count == calls_before

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_intermittent_success_does_not_reset_the_breaker(self, mock_get):
        """
        The counter is cumulative, not a streak.

        A streak counter is useless against an intermittently-blocked source:
        one lucky success resets it, the circuit never opens, and every other
        request still pays full backoff. That is what happened in the live
        backfill — two people processed in fifteen minutes.
        """
        from server.data.sources.gdelt import GdeltUnavailable
        ok = _resp(200, {"timeline": [{"data": [{"value": 4}]}]})
        # Each failed call burns MAX_ATTEMPTS (2) responses. Interleave a
        # success part-way through; the breaker must still open.
        mock_get.side_effect = ([_resp(429)] * 8 + [ok] + [_resp(429)] * 20)
        failures = 0
        for _ in range(4):
            with pytest.raises(requests.exceptions.RequestException):
                fetch_news_count("Someone", "20260401", "20260630")
            failures += 1
        assert fetch_news_count("Someone", "20260401", "20260630") == 4
        for _ in range(4):
            with pytest.raises(requests.exceptions.RequestException):
                fetch_news_count("Someone", "20260401", "20260630")
        # 8 cumulative failures reached — further calls short-circuit
        with pytest.raises(GdeltUnavailable):
            fetch_news_count("Another", "20260401", "20260630")
