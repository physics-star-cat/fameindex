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
        ok = _resp(200, {"timeline": [{"data": [{"value": 7}, {"value": 3}]}]})
        mock_get.side_effect = [_resp(429), _resp(429), ok]
        assert fetch_news_count("Someone", "20260401", "20260630") == 10
        assert mock_get.call_count == 3

    @patch("server.data.sources.gdelt.time.sleep", lambda *_: None)
    @patch("server.data.sources.gdelt.requests.get")
    def test_genuine_zero_is_still_zero(self, mock_get):
        # An empty timeline is a real answer, not a failure.
        mock_get.return_value = _resp(200, {"timeline": []})
        assert fetch_news_count("Someone", "20260401", "20260630") == 0
