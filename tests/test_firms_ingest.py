"""Tests for ingestion.firms.ingest using a fake client and fake raw writer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from ingestion.firms.client import (
    Availability,
    FirmsCredentials,
    FirmsHTTPError,
    FirmsPayloadError,
)
from ingestion.firms import ingest


BUCKET = "test-raw-bucket"
INGEST_DATE = "2026-11-08"
BATCH_ID = "nasa_firms_fires_20261108T003800Z_abc123def456"


class FakeAreaResponse:
    def __init__(self, *, data_id, date, day_range, body, row_count, url):
        self.data_id = data_id
        self.date = date
        self.day_range = day_range
        self.body = body
        self.row_count = row_count
        self.url = url


class FakeFirmsClient:
    """Injectable stand-in for FirmsClient. Never touches the network."""

    def __init__(self, credentials, *, availability=None, areas=None):
        self.credentials = credentials
        self.availability = availability or {}
        self.areas = areas or {}
        self.calls = []

    def get_data_availability(self, data_id):
        if data_id not in self.availability:
            raise FirmsPayloadError(
                f"no availability for {data_id}", url=f"https://example.com/{data_id}"
            )
        return self.availability[data_id]

    def fetch_area(self, data_id, *, day_range, date=None):
        self.calls.append((data_id, day_range, date))
        key = (data_id, date)
        if key in self.areas:
            entry = self.areas[key]
            if isinstance(entry, Exception):
                raise entry
            return entry
        return FakeAreaResponse(
            data_id=data_id,
            date=date,
            day_range=day_range,
            body=b"latitude,longitude,...\n",
            row_count=0,
            url=f"https://example.com/area/{data_id}/{date}",
        )


class FakeRawWriter:
    def __init__(
        self,
        *,
        raw_bucket=BUCKET,
        existing=None,
        fail_existing=False,
        fail_write_csv=False,
        fail_write_quarantine=False,
    ):
        self.config = MagicMock()
        self.config.raw_bucket = raw_bucket
        self.existing = existing or {}
        self.fail_existing = fail_existing
        self.fail_write_csv = fail_write_csv
        self.fail_write_quarantine = fail_write_quarantine
        self.written = []
        self.quarantined = []

    def existing_data_dates(self, data_id):
        if self.fail_existing:
            raise RuntimeError("list_objects_v2 denied")
        return set(self.existing.get(data_id, []))

    def write_csv(self, *, ingest_date, batch_id, data_id, data_date, body, row_count, metadata=None):
        if self.fail_write_csv:
            raise RuntimeError("put_object denied")
        self.written.append(
            {
                "ingest_date": ingest_date,
                "batch_id": batch_id,
                "data_id": data_id,
                "data_date": data_date,
                "row_count": row_count,
                "metadata": metadata,
            }
        )
        return MagicMock(key=f"{batch_id}/{data_id}_{data_date}.csv", size_bytes=len(body))

    def write_quarantine(self, *, ingest_date, batch_id, data_id, data_date, error_type, error_message, raw_data=None, response_metadata=None):
        if self.fail_write_quarantine:
            raise RuntimeError("put_object denied")
        self.quarantined.append(
            {
                "ingest_date": ingest_date,
                "batch_id": batch_id,
                "data_id": data_id,
                "data_date": data_date,
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        return MagicMock()


def _credentials():
    return FirmsCredentials(map_key="test-map-key-12345", base_url="https://example.com")


def _availability(data_id, min_date, max_date):
    return Availability(
        data_id=data_id,
        min_date=date.fromisoformat(min_date),
        max_date=date.fromisoformat(max_date),
    )


def _csv_with_rows(n_rows=2):
    header = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    rows = "".join(f"{i},{i+1},300,1,1,2026-11-07,1200,N20,VIIRS,n,1,1.0,300.0,D\n" for i in range(n_rows))
    return (header + rows).encode("utf-8")


def _header_only():
    return b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"


class TestSelectTargetDates:
    def test_daily_run_returns_only_max_date(self):
        dates = ingest.select_target_dates(
            date(2026, 11, 7), date(2026, 11, 1), backfill_days=0
        )
        assert dates == ["2026-11-07"]

    def test_backfill_clamped_to_window(self):
        dates = ingest.select_target_dates(
            date(2026, 11, 7), date(2026, 11, 5), backfill_days=5
        )
        # 7, 6, 5 are in window; 4, 3 are below min_date and excluded
        assert dates == ["2026-11-07", "2026-11-06", "2026-11-05"]

    def test_backfill_default_zero(self):
        dates = ingest.select_target_dates(date(2026, 11, 7), date(2026, 11, 1))
        assert dates == ["2026-11-07"]


class TestRunIngestion:
    def test_daily_run_all_header_only_writes_nothing(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_SNPP_NRT", "2026-11-02"): FakeAreaResponse(
                    data_id="VIIRS_SNPP_NRT", date="2026-11-02", day_range=1,
                    body=_header_only(), row_count=0,
                    url="https://example.com/area/VIIRS_SNPP_NRT/2026-11-02",
                ),
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_header_only(), row_count=0,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_header_only(), row_count=0,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["written_count"] == 0
        assert summary["quarantined_count"] == 0
        assert summary["error_count"] == 0
        assert summary["raw_bucket"] == BUCKET
        assert summary["backfill_days"] == 0
        assert summary["ingest_date"] == INGEST_DATE or summary["ingest_date"] == datetime.now(timezone.utc).date().isoformat()
        assert len(summary["satellites"]) == 3

    def test_writes_data_rows_for_each_satellite(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_SNPP_NRT", "2026-11-02"): FakeAreaResponse(
                    data_id="VIIRS_SNPP_NRT", date="2026-11-02", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_SNPP_NRT/2026-11-02",
                ),
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["written_count"] == 3
        assert summary["error_count"] == 0
        assert len(writer.written) == 3
        # day_range=1 with explicit date in every call
        for data_id, day_range, date in client.calls:
            assert day_range == 1
            assert date is not None

    def test_skips_dates_already_in_raw(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter(existing={"VIIRS_NOAA20_NRT": ["2026-11-07"]})

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        # SNPP: 2026-11-02 header-only -> not written; NOAA20: skipped (already in raw); NOAA21: written
        assert summary["written_count"] == 1
        assert summary["satellites"][1]["skipped_dates"] == ["2026-11-07"]
        # NOAA20 was never fetched
        fetched = [c for c in client.calls if c[0] == "VIIRS_NOAA20_NRT"]
        assert fetched == []

    def test_payload_error_quarantines_and_continues(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_SNPP_NRT", "2026-11-02"): FirmsPayloadError(
                    "bad header", sample="...", url="https://example.com/x"
                ),
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["quarantined_count"] == 1
        assert summary["written_count"] == 2
        assert summary["error_count"] == 0
        assert len(writer.quarantined) == 1
        assert writer.quarantined[0]["data_id"] == "VIIRS_SNPP_NRT"
        assert writer.quarantined[0]["data_date"] == "2026-11-02"

    def test_http_error_recorded_not_quarantined(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_SNPP_NRT", "2026-11-02"): FirmsHTTPError(
                    status_code=400, url="https://example.com/x", body_sample="bad"
                ),
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["error_count"] == 1
        assert summary["quarantined_count"] == 0
        assert summary["written_count"] == 2
        assert summary["satellites"][0]["status"] == "error"
        # Other satellites still processed
        assert summary["satellites"][1]["status"] == "ok"

    def test_availability_failure_does_not_abort_other_satellites(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            # SNPP missing -> get_data_availability raises
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["error_count"] == 1
        assert summary["written_count"] == 1
        assert summary["satellites"][0]["status"] == "error"

    def test_backfill_dates_outside_window_skipped(self):
        client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA20_NRT/2026-11-07",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/area/VIIRS_NOAA21_NRT/2026-11-07",
                ),
            },
        )
        writer = FakeRawWriter()

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=7)

        assert summary["backfill_days"] == 7
        # SNPP window is 2026-11-01..2026-11-02; backfill 7 from 2026-11-02
        # yields 2026-11-02 and 2026-11-01 (both inside the window)
        snpp = summary["satellites"][0]
        assert snpp["target_dates"] == ["2026-11-02", "2026-11-01"]

    def test_load_credentials_is_used_when_no_client(self, monkeypatch):
        called = {}

        def fake_load(secret_id=ingest.DEFAULT_SECRET_ID, *, client=None):
            called["secret_id"] = secret_id
            return _credentials()

        monkeypatch.setattr(ingest, "load_credentials", fake_load)

        fake_client = FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_header_only(), row_count=0,
                    url="https://example.com/x",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_header_only(), row_count=0,
                    url="https://example.com/x",
                ),
            },
        )
        monkeypatch.setattr(
            ingest, "FirmsClient", lambda credentials, session=None: fake_client
        )

        writer = FakeRawWriter()

        # No client and no credentials: run_ingestion must call module-level
        # load_credentials and build the client from the returned credentials.
        ingest.run_ingestion(raw_writer=writer, backfill_days=0)

        assert called["secret_id"] == ingest.DEFAULT_SECRET_ID


class TestFailureIsolation:
    def _three_satellites(self, *, areas):
        return FakeFirmsClient(
            credentials=_credentials(),
            availability={
                "VIIRS_SNPP_NRT": _availability("VIIRS_SNPP_NRT", "2026-11-01", "2026-11-02"),
                "VIIRS_NOAA20_NRT": _availability("VIIRS_NOAA20_NRT", "2026-11-01", "2026-11-07"),
                "VIIRS_NOAA21_NRT": _availability("VIIRS_NOAA21_NRT", "2026-11-01", "2026-11-07"),
            },
            areas=areas,
        )

    def test_raw_write_failure_is_recorded_not_raised(self):
        client = self._three_satellites(
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
            },
        )
        writer = FakeRawWriter(fail_write_csv=True)

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        # Both satellites with data fail to write, SNPP is header-only.
        assert summary["written_count"] == 0
        assert summary["error_count"] == 2
        assert summary["satellites"][1]["status"] == "error"
        assert summary["satellites"][2]["status"] == "error"
        assert "raw write failed" in summary["satellites"][1]["errors"][0]

    def test_quarantine_write_failure_is_recorded_not_raised(self):
        client = self._three_satellites(
            areas={
                ("VIIRS_SNPP_NRT", "2026-11-02"): FirmsPayloadError(
                    "bad header", sample="...", url="https://example.com/x"
                ),
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
            },
        )
        writer = FakeRawWriter(fail_write_quarantine=True)

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        assert summary["error_count"] == 1
        assert summary["quarantined_count"] == 0
        assert summary["written_count"] == 2
        assert summary["satellites"][0]["status"] == "error"
        assert "quarantine write failed" in summary["satellites"][0]["errors"][0]

    def test_existing_dates_failure_skips_satellite_without_fetching(self):
        client = self._three_satellites(
            areas={
                ("VIIRS_NOAA20_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA20_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
                ("VIIRS_NOAA21_NRT", "2026-11-07"): FakeAreaResponse(
                    data_id="VIIRS_NOAA21_NRT", date="2026-11-07", day_range=1,
                    body=_csv_with_rows(), row_count=2,
                    url="https://example.com/x",
                ),
            },
        )
        writer = FakeRawWriter(fail_existing=True)

        summary = ingest.run_ingestion(client=client, raw_writer=writer, backfill_days=0)

        # Every satellite fails the raw listing -> no requests, three errors.
        assert client.calls == []
        assert summary["written_count"] == 0
        assert summary["error_count"] == 3
        for satellite in summary["satellites"]:
            assert satellite["status"] == "error"
            assert "failed to list existing raw dates" in satellite["errors"][0]
