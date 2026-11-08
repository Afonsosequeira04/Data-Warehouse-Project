"""Tests for ingestion.firms.client using real fixtures and mocked HTTP.

The NASA FIRMS MAP_KEY never appears in this file: every test uses a fake
key and asserts it is redacted from URLs, exception messages and logs.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pytest
import responses

from ingestion.firms.client import (
    DEFAULT_BASE_URL,
    DEFAULT_SECRET_ID,
    AreaResponse,
    Availability,
    FirmsClient,
    FirmsCredentials,
    FirmsHTTPError,
    FirmsPayloadError,
    FirmsRequestError,
    load_credentials,
    validate_area_body,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nasa_firms_fires"
FAKE_KEY = "test-map-key-12345"


@pytest.fixture
def resps():
    with responses.RequestsMock() as rsps:
        yield rsps


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _credentials():
    return FirmsCredentials(map_key=FAKE_KEY, base_url="https://example.com")


def _client():
    return FirmsClient(_credentials())


def _register(resps, method, path, body, status=200, content_type="text/csv"):
    url = f"https://example.com{path}"
    resps.add(method, url, body=body, status=status, content_type=content_type)
    return url


class TestAvailability:
    def test_availability_parses_all_satellites(self, resps):
        for data_id, fixture in [
            ("VIIRS_SNPP_NRT", "availability_snpp.csv"),
            ("VIIRS_NOAA20_NRT", "availability_noaa20.csv"),
            ("VIIRS_NOAA21_NRT", "availability_noaa21.csv"),
        ]:
            path = f"/api/data_availability/csv/{FAKE_KEY}/{data_id}"
            _register(resps, responses.GET, path, _fixture(fixture))

        client = _client()
        snpp = client.get_data_availability("VIIRS_SNPP_NRT")
        noaa20 = client.get_data_availability("VIIRS_NOAA20_NRT")
        noaa21 = client.get_data_availability("VIIRS_NOAA21_NRT")

        assert snpp == Availability("VIIRS_SNPP_NRT", date(2026, 8, 1), date(2026, 11, 2))
        assert noaa20 == Availability("VIIRS_NOAA20_NRT", date(2026, 8, 1), date(2026, 11, 7))
        assert noaa21 == Availability("VIIRS_NOAA21_NRT", date(2024, 1, 17), date(2026, 11, 7))


class TestFetchArea:
    def test_fetch_area_with_data_rows(self, resps):
        body = _fixture("world_5_noaa20_head.csv")
        url = _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-04",
            body,
        )

        response = _client().fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-04")

        assert isinstance(response, AreaResponse)
        assert response.data_id == "VIIRS_NOAA20_NRT"
        assert response.date == "2026-11-04"
        assert response.day_range == 1
        assert response.row_count == 1
        assert response.body == body
        assert response.url == url.replace(FAKE_KEY, "***")
        assert FAKE_KEY not in response.url

    def test_fetch_area_header_only_is_valid(self, resps):
        body = _fixture("world_1_noaa20.csv")
        url = _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            body,
        )

        response = _client().fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")

        assert response.row_count == 0
        assert response.body == body
        assert response.url == url.replace(FAKE_KEY, "***")

    def test_fetch_area_uses_explicit_date_in_url(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_SNPP_NRT/world/1/2026-11-02",
            _fixture("world_1_snpp.csv"),
        )

        _client().fetch_area("VIIRS_SNPP_NRT", day_range=1, date="2026-11-02")

        # The exact date must be in the request URL, never a relative range.
        assert resps.calls[0].request.url.endswith(
            "/VIIRS_SNPP_NRT/world/1/2026-11-02"
        )

    def test_invalid_day_range_raises_before_http(self):
        client = _client()
        with pytest.raises(ValueError, match="day_range must be between"):
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=7, date="2026-11-07")
        with pytest.raises(ValueError, match="day_range must be between"):
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=0, date="2026-11-07")

    def test_http_400_raises_firms_http_error(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            _fixture("error_invalid_day_range.txt"),
            status=400,
        )
        client = _client()
        with pytest.raises(FirmsHTTPError) as exc:
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
        assert exc.value.status_code == 400
        assert FAKE_KEY not in str(exc.value)
        assert FAKE_KEY not in exc.value.url

    def test_wrong_header_raises_payload_error(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            b"wrong,header\n",
        )
        client = _client()
        with pytest.raises(FirmsPayloadError) as exc:
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
        assert exc.value.error_type == "payload_error"
        assert FAKE_KEY not in str(exc.value)
        assert exc.value.url is not None and FAKE_KEY not in exc.value.url

    def test_wrong_column_count_raises_payload_error(self, resps):
        body = b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n1.0,2.0,300\n"
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            body,
        )
        client = _client()
        with pytest.raises(FirmsPayloadError) as exc:
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
        assert "3 fields" in str(exc.value) or "expected 14" in str(exc.value)
        assert FAKE_KEY not in str(exc.value)

    def test_empty_body_raises_payload_error(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            b"",
        )
        client = _client()
        with pytest.raises(FirmsPayloadError):
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")

    def test_non_utf8_body_raises_payload_error(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            b"\xff\xfe\x00bad",
        )
        client = _client()
        with pytest.raises(FirmsPayloadError) as exc:
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
        assert FAKE_KEY not in str(exc.value)

    def test_network_error_raises_firms_request_error(self):
        from unittest.mock import patch

        import requests

        client = _client()
        with patch.object(
            client._session, "get", side_effect=requests.ConnectionError("boom")
        ):
            with pytest.raises(FirmsRequestError):
                client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")


class TestRedaction:
    def test_fake_key_never_in_exception_text(self, resps):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            _fixture("error_invalid_day_range.txt"),
            status=400,
        )
        client = _client()
        try:
            client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
        except FirmsHTTPError as exc:
            text = f"{exc} {exc.url} {exc.body_sample or ''}"
        else:
            raise AssertionError("expected FirmsHTTPError")
        assert FAKE_KEY not in text

    def test_fake_key_never_in_logs(self, resps, caplog):
        _register(
            resps,
            responses.GET,
            f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/world/1/2026-11-07",
            _fixture("error_invalid_day_range.txt"),
            status=400,
        )
        client = _client()
        with caplog.at_level(logging.ERROR, logger="ingestion.firms.client"):
            try:
                client.fetch_area("VIIRS_NOAA20_NRT", day_range=1, date="2026-11-07")
            except FirmsHTTPError:
                pass
        assert FAKE_KEY not in caplog.text


class TestLoadCredentials:
    def test_load_credentials_parses_secret(self):
        class FakeSecrets:
            def get_secret_value(self, *, SecretId):
                return {"SecretString": '{"map_key": "k1", "base_url": "https://x"}'}

        creds = load_credentials(client=FakeSecrets())
        assert creds.map_key == "k1"
        assert creds.base_url == "https://x"

    def test_load_credentials_missing_key_raises(self):
        class FakeSecrets:
            def get_secret_value(self, *, SecretId):
                return {"SecretString": '{"base_url": "https://x"}'}

        from ingestion.firms.client import FirmsError

        with pytest.raises(FirmsError):
            load_credentials(client=FakeSecrets())


class TestValidateAreaBody:
    def test_valid_body_returns_row_count(self):
        body = (
            b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
            b"instrument,confidence,version,bright_ti5,frp,daynight\n"
            b"1.0,2.0,300.0,1,1,2026-11-04,7,N20,VIIRS,n,2.0NRT,256.66,5.2,N\n"
        )
        assert validate_area_body(body) == 1

    def test_header_only_returns_zero(self):
        assert validate_area_body(_fixture("world_1_noaa20.csv")) == 0

    def test_wrong_header_raises(self):
        with pytest.raises(FirmsPayloadError):
            validate_area_body(b"wrong,header\n")

    def test_empty_body_raises(self):
        with pytest.raises(FirmsPayloadError):
            validate_area_body(b"")
