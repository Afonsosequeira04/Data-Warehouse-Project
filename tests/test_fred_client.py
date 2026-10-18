"""Unit tests for FRED economic series API client."""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest
import responses

from ingestion.api import fred_client as fred_client_module
from ingestion.api.fred_client import (
    DEFAULT_SERIES,
    FredAPIError,
    FredClient,
    FredConfig,
)

SERIES_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES_ID = "UNRATE"
API_KEY = "test_fred_key"


class FakeTime:
    """Minimal stand-in for the time module used by the rate limiter."""

    def __init__(self, now: float):
        self.now = now
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _expected_params(offset: int, **overrides: str | int) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "series_id": SERIES_ID,
        "api_key": API_KEY,
        "file_type": "json",
        "limit": 2,
        "offset": offset,
        "sort_order": "asc",
    }
    params.update(overrides)
    return params


def _matcher(offset: int, **overrides: str | int):
    return responses.matchers.query_param_matcher(
        _expected_params(offset, **overrides)
    )


def _register_page(body: dict, offset: int, **overrides: str | int) -> None:
    responses.get(SERIES_URL, json=body, match=[_matcher(offset, **overrides)])


def _observation(day: str, value: str = "1.0") -> dict:
    return {
        "date": day,
        "value": value,
        "realtime_start": "2024-01-01",
        "realtime_end": "2024-03-01",
    }


class TestFredClient:
    """Tests for FredClient."""

    @responses.activate
    def test_builds_expected_request(self, mock_fred_config):
        """Test URL, query parameters, and api_key redaction."""
        _register_page({"count": 0, "offset": 0, "observations": []}, offset=0)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        assert len(responses.calls) == 1

        request_url = responses.calls[0].request.url
        assert request_url.startswith(SERIES_URL)
        assert "series_id=UNRATE" in request_url
        assert f"api_key={API_KEY}" in request_url
        assert "file_type=json" in request_url
        assert "limit=2" in request_url
        assert "offset=0" in request_url
        assert "sort_order=asc" in request_url

        assert API_KEY not in pages[0].request_url
        assert "api_key=***" in pages[0].request_url

    @responses.activate
    def test_fetch_series_paginates(
        self, mock_fred_config, fred_unrate_page1, fred_unrate_page2
    ):
        """Test fetching two pages and preserving missing values as '.'."""
        _register_page(fred_unrate_page1, offset=0)
        _register_page(fred_unrate_page2, offset=2)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert [page.offset for page in pages] == [0, 2]
        observations = [obs for page in pages for obs in page.observations]
        assert [obs["date"] for obs in observations] == [
            "2024-01-01",
            "2024-02-01",
            "2024-03-01",
        ]
        assert [obs["value"] for obs in observations] == ["3.7", ".", "3.8"]
        assert all(page.quarantine_reason is None for page in pages)
        assert len(responses.calls) == 2

    @responses.activate
    def test_fetch_series_http_error_is_redacted(self, mock_fred_config):
        """Test that HTTP errors raise and never expose the api_key."""
        responses.get(SERIES_URL, status=500, body=f"boom {API_KEY}")

        client = FredClient(mock_fred_config)
        with pytest.raises(FredAPIError) as exc_info:
            list(client.fetch_series(SERIES_ID))

        message = str(exc_info.value)
        assert "HTTP 500" in message
        assert API_KEY not in message
        assert "***" in message

    @responses.activate
    def test_api_error_payload_is_quarantined(
        self, mock_fred_config, fred_api_error_payload
    ):
        """Test FRED error payload returned with HTTP 200 is quarantined."""
        _register_page(fred_api_error_payload, offset=0)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        page = pages[0]
        assert page.quarantine_reason.startswith("api_error:")
        assert "400" in page.quarantine_reason
        assert "not registered" in page.quarantine_raw
        assert len(responses.calls) == 1

    @responses.activate
    def test_invalid_json_is_quarantined(self, mock_fred_config):
        """Test invalid JSON is quarantined and stops pagination."""
        responses.get(SERIES_URL, body="not-json", status=200)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        page = pages[0]
        assert page.quarantine_reason.startswith("invalid_json:")
        assert page.quarantine_raw == "not-json"
        assert API_KEY not in page.request_url
        assert "api_key=***" in page.request_url
        assert len(responses.calls) == 1

    @responses.activate
    def test_missing_fields_page_separates_rejections(
        self, mock_fred_config, fred_missing_fields_page
    ):
        """Test observations missing required fields are rejected individually."""
        _register_page(fred_missing_fields_page, offset=0)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        page = pages[0]
        assert len(page.observations) == 1
        assert len(page.rejections) == 1
        assert (
            page.rejections[0].reason
            == "missing required field(s): value, realtime_end"
        )

    @responses.activate
    def test_empty_page_stops_pagination(self, mock_fred_config):
        """Test a zero-count page ends pagination after one request."""
        _register_page({"count": 0, "offset": 0, "observations": []}, offset=0)

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        assert len(responses.calls) == 1

    @responses.activate
    def test_short_page_without_count_stops_pagination(self, mock_fred_config):
        """Test a short page without a count ends pagination."""
        _register_page(
            {"observations": [_observation("2024-01-01")]}, offset=0
        )

        client = FredClient(mock_fred_config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        assert pages[0].count is None
        assert len(responses.calls) == 1

    @responses.activate
    def test_max_pages_limit(self, mock_fred_config):
        """Test the max_pages guard stops pagination."""
        config = replace(mock_fred_config, max_pages=1)
        _register_page(
            {
                "count": 100,
                "offset": 0,
                "observations": [
                    _observation("2024-01-01"),
                    _observation("2024-02-01"),
                ],
            },
            offset=0,
        )

        client = FredClient(config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        assert len(responses.calls) == 1

    @responses.activate
    def test_observation_window_is_sent_as_params(self, mock_fred_config):
        """Test observation_start and observation_end are sent when configured."""
        config = replace(
            mock_fred_config,
            observation_start="2024-01-01",
            observation_end="2024-03-01",
        )
        _register_page(
            {
                "count": 1,
                "offset": 0,
                "observations": [_observation("2024-01-01")],
            },
            offset=0,
            observation_start="2024-01-01",
            observation_end="2024-03-01",
        )

        client = FredClient(config)
        pages = list(client.fetch_series(SERIES_ID))

        assert len(pages) == 1
        assert len(responses.calls) == 1

    def test_rate_limit_sleeps_when_needed(
        self, mock_fred_config, monkeypatch
    ):
        """Test the rate limiter sleeps for the remaining interval."""
        fake_time = FakeTime(now=100.1)
        monkeypatch.setattr(fred_client_module, "time", fake_time)

        config = replace(mock_fred_config, rate_limit_rps=2.0)
        client = FredClient(config)
        client._last_request_time = 100.0
        client._rate_limit()

        assert len(fake_time.sleeps) == 1
        assert fake_time.sleeps[0] == pytest.approx(0.4)

    def test_rate_limit_skips_sleep_when_within_limit(
        self, mock_fred_config, monkeypatch
    ):
        """Test the rate limiter does not sleep after enough elapsed time."""
        fake_time = FakeTime(now=100.0)
        monkeypatch.setattr(fred_client_module, "time", fake_time)

        client = FredClient(mock_fred_config)
        client._last_request_time = 0.0
        client._rate_limit()

        assert fake_time.sleeps == []

    def test_api_key_is_redacted_in_logs(self, mock_fred_config, caplog):
        """Test the logging filter masks the api_key in log output."""
        FredClient(mock_fred_config)

        with caplog.at_level(logging.DEBUG):
            fred_client_module.logger.warning("test message with %s", API_KEY)

        assert API_KEY not in caplog.text
        assert "***" in caplog.text

    def test_empty_api_key_is_rejected(self):
        """Test the client refuses to run without an api_key."""
        with pytest.raises(ValueError, match="api_key"):
            FredClient(FredConfig())

    def test_invalid_observation_start_is_rejected(self):
        """Test observation_start must be an ISO date."""
        config = FredConfig(api_key=API_KEY, observation_start="2024/01/01")
        with pytest.raises(ValueError, match="observation_start"):
            FredClient(config)

    def test_context_manager_closes_session(self, mock_fred_config):
        """Test the client closes its session on exit."""
        closed: list[bool] = []
        with FredClient(mock_fred_config) as client:
            client._session.close = lambda: closed.append(True)

        assert closed == [True]


class TestFredConfig:
    """Tests for FredConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = FredConfig(api_key=API_KEY)
        assert config.base_url == "https://api.stlouisfed.org/fred"
        assert config.series_ids == DEFAULT_SERIES
        assert config.limit == 1000
        assert config.max_pages == 100
        assert config.observation_start is None
        assert config.observation_end is None
        assert config.rate_limit_rps == 2.0
        assert config.max_retries == 3
        assert config.timeout_seconds == 30
