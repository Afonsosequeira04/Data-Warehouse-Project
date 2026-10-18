"""Unit tests for FRED S3 raw writer."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

import pytest
from botocore.exceptions import ClientError

from ingestion.api import fred_writer as fred_writer_module
from ingestion.api.fred_writer import (
    MAX_ERROR_TOKEN_LENGTH,
    SOURCE_SYSTEM,
    FredWriter,
    FredWriterConfig,
    generate_batch_id,
    get_ingest_date,
)

RAW_BUCKET = "test-raw-bucket"
SERIES_ID = "UNRATE"
BATCH_ID = "fred_20260101T000000Z_abc123"
INGEST_DATE = "2026-01-01"


class FakeS3Client:
    """Capture put_object calls and return a fixed ETag."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"ETag": '"fake-etag"'}


class FailingS3Client:
    """Raise ClientError for every put_object call."""

    def put_object(self, **kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "PutObject",
        )


def _writer(s3_client: FakeS3Client | None = None) -> FredWriter:
    return FredWriter(
        FredWriterConfig(raw_bucket=RAW_BUCKET),
        s3_client=s3_client or FakeS3Client(),
    )


def _observations() -> list[dict]:
    return [
        {
            "date": "2024-01-01",
            "value": "3.7",
            "realtime_start": "2024-01-01",
            "realtime_end": "2024-03-01",
        },
        {
            "date": "2024-02-01",
            "value": ".",
            "realtime_start": "2024-01-01",
            "realtime_end": "2024-03-01",
        },
    ]


class TestKeyBuilding:
    """Tests for raw and quarantine key layout."""

    def test_raw_key_uses_ingest_date_batch_and_series(self):
        writer = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, SERIES_ID)

        assert key == (
            f"api/fred_economic_series/ingest_date={INGEST_DATE}/"
            f"{BATCH_ID}/{SERIES_ID}.ndjson"
        )

    def test_raw_key_sanitizes_unsafe_tokens(self):
        writer = _writer()

        key = writer._build_raw_key(
            INGEST_DATE, "batch id/with spaces", "UN RATE?"
        )

        assert key == (
            f"api/fred_economic_series/ingest_date={INGEST_DATE}/"
            "batch_id_with_spaces/UN_RATE.ndjson"
        )

    def test_raw_key_respects_custom_prefix(self):
        writer = FredWriter(
            FredWriterConfig(raw_bucket=RAW_BUCKET, raw_prefix="raw/fred/"),
            s3_client=FakeS3Client(),
        )

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, SERIES_ID)

        assert key.startswith("raw/fred/ingest_date=")

    def test_quarantine_key_sanitizes_error_type(self):
        writer = _writer()

        key = writer._build_quarantine_key(
            INGEST_DATE, BATCH_ID, SERIES_ID, "API Error: Missing value"
        )

        assert key.endswith(f"{SERIES_ID}_api_error_missing_value.json")

    def test_quarantine_key_truncates_long_error_type(self):
        writer = _writer()

        key = writer._build_quarantine_key(
            INGEST_DATE, BATCH_ID, SERIES_ID, "x" * 100
        )

        filename = key.rsplit("/", 1)[-1]
        assert filename == f"{SERIES_ID}_{'x' * MAX_ERROR_TOKEN_LENGTH}.json"

    @pytest.mark.parametrize(
        "ingest_date", ["2026/01/01", "01-01-2026", "not-a-date", ""]
    )
    def test_invalid_ingest_date_is_rejected(self, ingest_date):
        writer = _writer()

        with pytest.raises(ValueError, match="ingest_date"):
            writer._build_raw_key(ingest_date, BATCH_ID, SERIES_ID)

    def test_blank_batch_id_is_rejected(self):
        writer = _writer()

        with pytest.raises(ValueError, match="batch_id"):
            writer._build_raw_key(INGEST_DATE, "   ", SERIES_ID)

    def test_blank_series_id_is_rejected(self):
        writer = _writer()

        with pytest.raises(ValueError, match="series_id"):
            writer._build_raw_key(INGEST_DATE, BATCH_ID, "   ")

    def test_blank_error_type_is_rejected(self):
        writer = _writer()

        with pytest.raises(ValueError, match="error_type"):
            writer._build_quarantine_key(INGEST_DATE, BATCH_ID, SERIES_ID, "")


class TestWriteSeries:
    """Tests for writing raw observations as NDJSON."""

    def test_writes_ndjson_with_metadata(self):
        fake = FakeS3Client()
        writer = _writer(fake)
        observations = _observations()

        result = writer.write_series(
            INGEST_DATE, BATCH_ID, SERIES_ID, observations
        )

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["Bucket"] == RAW_BUCKET
        assert call["Key"] == (
            f"api/fred_economic_series/ingest_date={INGEST_DATE}/"
            f"{BATCH_ID}/{SERIES_ID}.ndjson"
        )
        assert call["ContentType"] == "application/x-ndjson"
        assert call["Metadata"] == {
            "source-system": SOURCE_SYSTEM,
            "batch-id": BATCH_ID,
            "series-id": SERIES_ID,
            "record-count": "2",
        }

    def test_body_is_one_json_object_per_line(self):
        fake = FakeS3Client()
        writer = _writer(fake)
        observations = _observations()

        writer.write_series(INGEST_DATE, BATCH_ID, SERIES_ID, observations)

        body = fake.calls[0]["Body"]
        assert isinstance(body, bytes)
        text = body.decode("utf-8")
        assert text.endswith("\n")
        lines = text.splitlines()
        assert len(lines) == 2
        assert [json.loads(line) for line in lines] == observations

    def test_dot_values_are_preserved_in_raw(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        writer.write_series(INGEST_DATE, BATCH_ID, SERIES_ID, _observations())

        records = [
            json.loads(line)
            for line in fake.calls[0]["Body"].decode("utf-8").splitlines()
        ]
        assert records[1]["value"] == "."

    def test_accepts_observation_iterator(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        result = writer.write_series(
            INGEST_DATE,
            BATCH_ID,
            SERIES_ID,
            (observation for observation in _observations()),
        )

        assert result.record_count == 2

    def test_result_fields(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        result = writer.write_series(
            INGEST_DATE, BATCH_ID, SERIES_ID, _observations()
        )

        body = fake.calls[0]["Body"]
        assert result.bucket == RAW_BUCKET
        assert result.key == fake.calls[0]["Key"]
        assert result.size_bytes == len(body)
        assert result.etag == "fake-etag"
        assert result.record_count == 2
        assert result.written_at.tzinfo is not None

    def test_empty_observations_are_rejected(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        with pytest.raises(ValueError, match="No observations"):
            writer.write_series(INGEST_DATE, BATCH_ID, SERIES_ID, [])

        assert fake.calls == []

    def test_client_errors_propagate(self):
        writer = FredWriter(
            FredWriterConfig(raw_bucket=RAW_BUCKET),
            s3_client=FailingS3Client(),
        )

        with pytest.raises(ClientError):
            writer.write_series(
                INGEST_DATE, BATCH_ID, SERIES_ID, _observations()
            )


class TestWriteQuarantine:
    """Tests for writing quarantine payloads."""

    def test_writes_required_payload_fields(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        result = writer.write_quarantine(
            INGEST_DATE,
            BATCH_ID,
            SERIES_ID,
            "api_error",
            "FRED returned an error payload",
        )

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["ContentType"] == "application/json"
        assert call["Key"].endswith(f"{SERIES_ID}_api_error.json")
        assert call["Metadata"] == {
            "source-system": SOURCE_SYSTEM,
            "batch-id": BATCH_ID,
            "series-id": SERIES_ID,
            "error-type": "api_error",
        }

        payload = json.loads(call["Body"].decode("utf-8"))
        assert payload["source_system"] == SOURCE_SYSTEM
        assert payload["series_id"] == SERIES_ID
        assert payload["batch_id"] == BATCH_ID
        assert payload["ingest_date"] == INGEST_DATE
        assert payload["error_type"] == "api_error"
        assert payload["error_message"] == "FRED returned an error payload"
        assert datetime.fromisoformat(payload["quarantined_at"]).tzinfo is not None
        assert "raw_data" not in payload
        assert "response_metadata" not in payload
        assert result.record_count is None

    def test_includes_optional_context(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        writer.write_quarantine(
            INGEST_DATE,
            BATCH_ID,
            SERIES_ID,
            "invalid_json",
            "Response was not valid JSON",
            raw_data="not-json",
            response_metadata={"status_code": 200},
        )

        payload = json.loads(fake.calls[0]["Body"].decode("utf-8"))
        assert payload["raw_data"] == "not-json"
        assert payload["response_metadata"] == {"status_code": 200}

    def test_quarantine_key_uses_custom_prefix(self):
        fake = FakeS3Client()
        writer = FredWriter(
            FredWriterConfig(
                raw_bucket=RAW_BUCKET,
                quarantine_prefix="quarantine/custom/",
            ),
            s3_client=fake,
        )

        result = writer.write_quarantine(
            INGEST_DATE, BATCH_ID, SERIES_ID, "api_error", "boom"
        )

        assert result.key.startswith("quarantine/custom/ingest_date=")

    def test_blank_error_message_is_allowed(self):
        fake = FakeS3Client()
        writer = _writer(fake)

        writer.write_quarantine(
            INGEST_DATE, BATCH_ID, SERIES_ID, "api_error", ""
        )

        payload = json.loads(fake.calls[0]["Body"].decode("utf-8"))
        assert payload["error_message"] == ""


class TestHelpers:
    """Tests for batch id, ingest date, and client wiring."""

    def test_generate_batch_id_format(self):
        batch_id = generate_batch_id()

        assert re.fullmatch(r"fred_\d{8}T\d{6}Z_[0-9a-f]{12}", batch_id)

    def test_generate_batch_id_is_unique(self):
        assert generate_batch_id() != generate_batch_id()

    def test_get_ingest_date_is_iso(self):
        ingest_date = get_ingest_date()

        assert date.fromisoformat(ingest_date).isoformat() == ingest_date

    def test_lazy_client_is_created_once(self, monkeypatch):
        created: list[str] = []
        fake = FakeS3Client()

        def fake_client(name: str):
            created.append(name)
            return fake

        monkeypatch.setattr(fred_writer_module.boto3, "client", fake_client)
        writer = FredWriter(FredWriterConfig(raw_bucket=RAW_BUCKET))

        assert writer._client() is fake
        assert writer._client() is fake
        assert created == ["s3"]

    def test_injected_client_is_reused(self, monkeypatch):
        fake = FakeS3Client()
        writer = _writer(fake)

        assert writer._client() is fake


class TestConfig:
    """Tests for FredWriterConfig validation."""

    def test_default_prefixes(self):
        config = FredWriterConfig(raw_bucket=RAW_BUCKET)

        assert config.raw_prefix == "api/fred_economic_series"
        assert config.quarantine_prefix == "quarantine/api/fred_economic_series"

    @pytest.mark.parametrize(
        "field", ["raw_bucket", "raw_prefix", "quarantine_prefix"]
    )
    def test_blank_fields_are_rejected(self, field):
        kwargs = {"raw_bucket": RAW_BUCKET, field: "   "}

        with pytest.raises(ValueError, match=field):
            FredWriterConfig(**kwargs)
