"""Tests for ingestion.firms.raw_writer (MagicMock S3)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from ingestion.firms.raw_writer import (
    FirmsRawWriter,
    RAW_PREFIX,
    RAW_SOURCE_SYSTEM,
)

BUCKET = "test-raw-bucket"
BATCH_ID = "nasa_firms_fires_20261107T001122Z_abc123def456"
INGEST_DATE = "2026-11-07"
DATA_ID = "VIIRS_NOAA20_NRT"
DATA_DATE = "2026-11-07"
ETAG = '"abc123"'


def _config(**overrides):
    values = {
        "raw_bucket": BUCKET,
        "raw_prefix": RAW_PREFIX,
        "quarantine_prefix": "quarantine/stream/nasa_firms_fires",
        "source_system": RAW_SOURCE_SYSTEM,
    }
    values.update(overrides)
    from ingestion.core.s3_writer import RawS3WriterConfig

    return RawS3WriterConfig(**values)


def _writer():
    s3 = MagicMock()
    s3.put_object.return_value = {"ETag": ETAG}
    return FirmsRawWriter(_config(), s3_client=s3), s3


def _client_error():
    return ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
    )


def test_object_name_is_token_and_date():
    writer, _ = _writer()

    assert (
        FirmsRawWriter.object_name("VIIRS_NOAA20_NRT", "2026-11-07")
        == "viirs_noaa20_nrt_2026-11-07"
    )


def test_raw_batch_prefix():
    writer, _ = _writer()

    assert (
        FirmsRawWriter.raw_batch_prefix(RAW_PREFIX, INGEST_DATE, BATCH_ID)
        == f"{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}"
    )


def test_write_csv_stores_body_byte_for_byte():
    writer, s3 = _writer()
    body = b"latitude,longitude,...\n1.0,2.0,...\n"

    result = writer.write_csv(
        ingest_date=INGEST_DATE,
        batch_id=BATCH_ID,
        data_id=DATA_ID,
        data_date=DATA_DATE,
        body=body,
        row_count=1,
    )

    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == BUCKET
    assert kwargs["Key"] == (
        f"{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}/"
        f"viirs_noaa20_nrt_2026-11-07.csv"
    )
    assert kwargs["Body"] == body
    assert kwargs["ContentType"] == "text/csv"
    metadata = kwargs["Metadata"]
    assert metadata["source"] == RAW_SOURCE_SYSTEM
    assert metadata["data_id"] == DATA_ID
    assert metadata["data_date"] == DATA_DATE
    assert metadata["batch_id"] == BATCH_ID
    assert metadata["ingest_date"] == INGEST_DATE
    assert metadata["row_count"] == "1"

    assert result.bucket == BUCKET
    assert result.size_bytes == len(body)
    assert result.etag == "abc123"
    assert result.record_count == 1


def test_write_csv_uses_extra_metadata():
    writer, s3 = _writer()

    writer.write_csv(
        ingest_date=INGEST_DATE,
        batch_id=BATCH_ID,
        data_id=DATA_ID,
        data_date=DATA_DATE,
        body=b"header\n",
        row_count=0,
        metadata={"SomeKey": "Value"},
    )

    metadata = s3.put_object.call_args.kwargs["Metadata"]
    assert metadata["somekey"] == "Value"


def test_client_error_is_logged_and_propagated(caplog):
    writer, s3 = _writer()
    s3.put_object.side_effect = _client_error()

    with caplog.at_level(logging.ERROR, logger="ingestion.firms.raw_writer"):
        with pytest.raises(ClientError):
            writer.write_csv(
                ingest_date=INGEST_DATE,
                batch_id=BATCH_ID,
                data_id=DATA_ID,
                data_date=DATA_DATE,
                body=b"header\n",
                row_count=0,
            )

    assert "Failed to write raw CSV to S3" in caplog.text


def test_write_quarantine_routes_to_shared_writer():
    writer, s3 = _writer()

    writer.write_quarantine(
        ingest_date=INGEST_DATE,
        batch_id=BATCH_ID,
        data_id=DATA_ID,
        data_date=DATA_DATE,
        error_type="payload_error",
        error_message="bad header",
        raw_data={"sample": "truncated"},
    )

    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Key"].startswith(
        f"quarantine/stream/{RAW_SOURCE_SYSTEM}/ingest_date={INGEST_DATE}/"
        f"{BATCH_ID}/viirs_noaa20_nrt_2026-11-07_"
    )
    assert kwargs["ContentType"] == "application/json"
    payload = kwargs["Body"]
    assert b'"error_type": "payload_error"' in payload
    assert b'"error_message": "bad header"' in payload


def test_existing_data_dates_paginates_all_prefixes():
    writer, s3 = _writer()

    token = "viirs_noaa20_nrt_"
    all_keys = [
        {"Key": f"api/nasa_firms_fires/ingest_date=2026-11-06/batch_a/{token}2026-11-06.csv"},
        {"Key": f"api/nasa_firms_fires/ingest_date=2026-11-06/batch_b/{token}2026-11-05.csv"},
        {"Key": f"api/nasa_firms_fires/ingest_date=2026-11-07/batch_c/{token}2026-11-07.csv"},
    ]

    def list_side_effect(**kwargs):
        prefix = kwargs["Prefix"]
        token = "viirs_noaa20_nrt_"
        keys = [k for k in all_keys if k["Key"].startswith(prefix)]
        return {
            "Contents": keys,
            "IsTruncated": False,
        }

    s3.list_objects_v2.side_effect = list_side_effect

    dates = writer.existing_data_dates(DATA_ID)

    assert dates == {"2026-11-06", "2026-11-05", "2026-11-07"}


def test_existing_data_dates_ignores_other_files_and_satellites():
    writer, s3 = _writer()

    def list_side_effect(**kwargs):
        prefix = kwargs["Prefix"]
        return {
            "Contents": [
                {"Key": f"{prefix}/batch_a/viirs_noaa20_nrt_2026-11-07.csv"},
                {"Key": f"{prefix}/batch_a/viirs_snpp_nrt_2026-11-07.csv"},
                {"Key": f"{prefix}/batch_a/other_viirs_noaa20_nrt_2026-11-07.csv"},
                {"Key": f"{prefix}/batch_a/viirs_noaa20_nrt_2026-11-07.ndjson"},
            ],
            "IsTruncated": False,
        }

    s3.list_objects_v2.side_effect = list_side_effect

    dates = writer.existing_data_dates(DATA_ID)

    assert dates == {"2026-11-07"}
