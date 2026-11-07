"""Tests for the shared raw and quarantine S3 writer."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from ingestion.core.s3_writer import (
    MAX_ERROR_TOKEN_LENGTH,
    QUARANTINE_CONTENT_TYPE,
    RAW_CONTENT_TYPE,
    RawS3Writer,
    RawS3WriterConfig,
)

BUCKET = "test-raw-bucket"
BATCH_ID = "emsc_20261107T001122Z_abc123def456"
INGEST_DATE = "2026-11-07"
ETAG = '"abc123"'


def _config(**overrides) -> RawS3WriterConfig:
    values = {
        "raw_bucket": BUCKET,
        "raw_prefix": "api/emsc",
        "quarantine_prefix": "quarantine/stream/emsc",
        "source_system": "emsc",
    }
    values.update(overrides)
    return RawS3WriterConfig(**values)


def _writer() -> tuple[RawS3Writer, MagicMock]:
    s3 = MagicMock()
    s3.put_object.return_value = {"ETag": ETAG}
    return RawS3Writer(_config(), s3_client=s3), s3


def _client_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
    )


class TestConfig:
    def test_config_accepts_valid_values(self):
        config = _config()

        assert config.raw_bucket == BUCKET
        assert config.raw_prefix == "api/emsc"
        assert config.quarantine_prefix == "quarantine/stream/emsc"
        assert config.source_system == "emsc"

    @pytest.mark.parametrize(
        "field", ["raw_bucket", "raw_prefix", "quarantine_prefix", "source_system"]
    )
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_config_rejects_blank_fields(self, field, blank):
        with pytest.raises(ValueError, match=f"{field} must be a non-empty string"):
            _config(**{field: blank})


class TestRawKey:
    def test_key_includes_date_batch_name_and_page(self):
        writer, _ = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, "chunk", page=0)

        assert key == (
            f"api/emsc/ingest_date={INGEST_DATE}/{BATCH_ID}/chunk_page_0000.ndjson"
        )

    def test_key_without_page_has_no_page_suffix(self):
        writer, _ = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, "chunk")

        assert key == f"api/emsc/ingest_date={INGEST_DATE}/{BATCH_ID}/chunk.ndjson"

    def test_name_is_sanitised(self):
        writer, _ = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, "world bank/indicators")

        assert key.endswith(f"/{BATCH_ID}/world_bank_indicators.ndjson")

    def test_extension_is_lowercased(self):
        writer, _ = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, "chunk", extension="JSON")

        assert key.endswith("/chunk.json")

    def test_large_page_number_is_zero_padded(self):
        writer, _ = _writer()

        key = writer._build_raw_key(INGEST_DATE, BATCH_ID, "chunk", page=12)

        assert key.endswith("/chunk_page_0012.ndjson")

    @pytest.mark.parametrize("page", [True, False, -1])
    def test_invalid_page_is_rejected(self, page):
        writer, _ = _writer()

        with pytest.raises(ValueError, match="page must be a non-negative integer"):
            writer._build_raw_key(INGEST_DATE, BATCH_ID, "chunk", page=page)

    def test_invalid_ingest_date_is_rejected(self):
        writer, _ = _writer()

        with pytest.raises(ValueError, match="ingest_date must be ISO-8601"):
            writer._build_raw_key("20261107", BATCH_ID, "chunk")

    def test_blank_name_is_rejected(self):
        writer, _ = _writer()

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            writer._build_raw_key(INGEST_DATE, BATCH_ID, "   ")


class TestQuarantineKey:
    def test_key_includes_sanitised_error_type(self):
        writer, _ = _writer()

        key = writer._build_quarantine_key(
            INGEST_DATE, BATCH_ID, "payload", "schema error/bad"
        )

        assert key == (
            f"quarantine/stream/emsc/ingest_date={INGEST_DATE}/{BATCH_ID}"
            "/payload_schema_error_bad.json"
        )

    def test_error_type_is_truncated(self):
        writer, _ = _writer()

        key = writer._build_quarantine_key(
            INGEST_DATE, BATCH_ID, "payload", "E" * 100
        )

        expected = f"/payload_{'e' * MAX_ERROR_TOKEN_LENGTH}.json"
        assert key.endswith(expected)


class TestWriteRawPage:
    def test_body_is_ndjson(self):
        writer, s3 = _writer()

        writer.write_raw_page(
            INGEST_DATE, BATCH_ID, "chunk", [{"a": 1}, {"b": 2}], page=1
        )

        kwargs = s3.put_object.call_args.kwargs
        assert kwargs["Body"] == b'{"a": 1}\n{"b": 2}'
        assert kwargs["ContentType"] == RAW_CONTENT_TYPE

    def test_metadata_describes_the_write(self):
        writer, s3 = _writer()

        writer.write_raw_page(
            INGEST_DATE,
            BATCH_ID,
            "chunk",
            [{"a": 1}],
            page=3,
            metadata={"per_page": 500, "SomeKey": "Value"},
        )

        metadata = s3.put_object.call_args.kwargs["Metadata"]
        assert metadata["source"] == "emsc"
        assert metadata["name"] == "chunk"
        assert metadata["batch_id"] == BATCH_ID
        assert metadata["ingest_date"] == INGEST_DATE
        assert metadata["record_count"] == "1"
        assert metadata["page"] == "3"
        assert metadata["per_page"] == "500"
        assert metadata["somekey"] == "Value"

    def test_empty_data_writes_an_empty_body(self):
        writer, s3 = _writer()

        result = writer.write_raw_page(INGEST_DATE, BATCH_ID, "chunk", [])

        kwargs = s3.put_object.call_args.kwargs
        assert kwargs["Body"] == b""
        assert kwargs["Metadata"]["record_count"] == "0"
        assert "page" not in kwargs["Metadata"]
        assert result.record_count == 0

    def test_result_describes_the_write(self):
        writer, _ = _writer()

        result = writer.write_raw_page(
            INGEST_DATE, BATCH_ID, "chunk", [{"a": 1}, {"b": 2}]
        )

        assert result.bucket == BUCKET
        assert result.key == f"api/emsc/ingest_date={INGEST_DATE}/{BATCH_ID}/chunk.ndjson"
        assert result.size_bytes == len(b'{"a": 1}\n{"b": 2}')
        assert result.etag == "abc123"
        assert result.record_count == 2

    def test_client_error_is_logged_and_propagated(self, caplog):
        writer, s3 = _writer()
        s3.put_object.side_effect = _client_error()

        with caplog.at_level(logging.ERROR, logger="ingestion.core.s3_writer"):
            with pytest.raises(ClientError):
                writer.write_raw_page(INGEST_DATE, BATCH_ID, "chunk", [{"a": 1}])

        assert "Failed to write raw page to S3" in caplog.text


class TestWriteQuarantine:
    def test_payload_describes_the_rejection(self):
        writer, s3 = _writer()

        writer.write_quarantine(
            INGEST_DATE,
            BATCH_ID,
            "payload",
            "schema_error",
            "missing field",
            raw_data=[{"a": 1}],
            response_metadata={"status": 200},
            page=2,
        )

        kwargs = s3.put_object.call_args.kwargs
        assert kwargs["ContentType"] == QUARANTINE_CONTENT_TYPE
        payload = json.loads(kwargs["Body"])
        assert payload["source"] == "emsc"
        assert payload["name"] == "payload"
        assert payload["page"] == 2
        assert payload["batch_id"] == BATCH_ID
        assert payload["ingest_date"] == INGEST_DATE
        assert payload["error_type"] == "schema_error"
        assert payload["error_message"] == "missing field"
        assert payload["raw_data"] == [{"a": 1}]
        assert payload["response_metadata"] == {"status": 200}

    def test_metadata_marks_the_object_as_quarantined(self):
        writer, s3 = _writer()

        writer.write_quarantine(
            INGEST_DATE, BATCH_ID, "payload", "schema_error", "missing field"
        )

        metadata = s3.put_object.call_args.kwargs["Metadata"]
        assert metadata["source"] == "emsc"
        assert metadata["name"] == "payload"
        assert metadata["batch_id"] == BATCH_ID
        assert metadata["ingest_date"] == INGEST_DATE
        assert metadata["error_type"] == "schema_error"
        assert metadata["quarantined"] == "true"
        assert "page" not in metadata

    def test_result_counts_list_records(self):
        writer, _ = _writer()

        result = writer.write_quarantine(
            INGEST_DATE,
            BATCH_ID,
            "payload",
            "schema_error",
            "missing field",
            raw_data=[{"a": 1}, {"b": 2}],
        )

        assert result.bucket == BUCKET
        assert result.key == (
            f"quarantine/stream/emsc/ingest_date={INGEST_DATE}/{BATCH_ID}"
            "/payload_schema_error.json"
        )
        assert result.record_count == 2

    def test_result_has_no_record_count_for_non_list_data(self):
        writer, _ = _writer()

        result = writer.write_quarantine(
            INGEST_DATE,
            BATCH_ID,
            "payload",
            "schema_error",
            "missing field",
            raw_data={"a": 1},
        )

        assert result.record_count is None

    def test_warning_is_logged_after_the_write(self, caplog):
        writer, _ = _writer()

        with caplog.at_level(logging.WARNING, logger="ingestion.core.s3_writer"):
            writer.write_quarantine(
                INGEST_DATE, BATCH_ID, "payload", "schema_error", "missing field"
            )

        assert "Quarantined payload" in caplog.text
        assert "schema_error" in caplog.text
        assert "missing field" in caplog.text

    def test_client_error_is_logged_and_propagated(self, caplog):
        writer, s3 = _writer()
        s3.put_object.side_effect = _client_error()

        with caplog.at_level(logging.ERROR, logger="ingestion.core.s3_writer"):
            with pytest.raises(ClientError):
                writer.write_quarantine(
                    INGEST_DATE, BATCH_ID, "payload", "schema_error", "missing field"
                )

        assert "Failed to write quarantine object to S3" in caplog.text


class TestLazyClient:
    def test_client_is_created_once_on_first_use(self, monkeypatch):
        created = []
        fake_client = MagicMock()

        def fake_boto_client(service_name):
            created.append(service_name)
            return fake_client

        monkeypatch.setattr(
            "ingestion.core.s3_writer.boto3.client", fake_boto_client
        )
        writer = RawS3Writer(_config())

        assert created == []
        assert writer.s3 is fake_client
        assert writer.s3 is fake_client
        assert created == ["s3"]
