"""Unit tests for S3 writer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock


class TestS3Writer:
    """Tests for S3Writer."""

    def test_write_raw_page_outputs_ndjson(self):
        """Test that write_raw_page outputs valid NDJSON with required fields."""
        from ingestion.api.s3_writer import S3Writer, S3WriterConfig

        config = S3WriterConfig(raw_bucket="test-bucket")
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"abc123"'}
        writer = S3Writer(config, s3_client=mock_s3)

        # Sample data as returned by World Bank API (original item dicts)
        data = [
            {
                "country": {"id": "ABW", "value": "Aruba"},
                "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
                "date": "2023",
                "value": 2.5,
                "unit": "",
                "obs_status": "E",
                "decimal": 1,
            },
            {
                "country": {"id": "AFG", "value": "Afghanistan"},
                "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
                "date": "2023",
                "value": -6.2,
                "unit": "",
                "obs_status": "E",
                "decimal": 1,
            },
        ]

        writer.write_raw_page(
            ingest_date="2025-01-15",
            batch_id="wb_test",
            indicator="NY.GDP.MKTP.KD.ZG",
            page=1,
            data=data,
        )

        # Verify S3 put_object was called
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        body = call_args.kwargs["Body"]

        # Verify body is bytes
        assert isinstance(body, bytes)

        # Decode and parse NDJSON lines
        lines = body.decode("utf-8").strip().split("\n")
        assert len(lines) == 2

        # Verify each line is valid JSON and contains required fields
        for line in lines:
            obs = json.loads(line)
            assert "country" in obs
            assert "id" in obs["country"]
            assert "indicator" in obs
            assert "id" in obs["indicator"]
            assert obs["country"]["id"] in ("ABW", "AFG")
            assert obs["indicator"]["id"] == "NY.GDP.MKTP.KD.ZG"

        # Verify content type
        assert call_args.kwargs["ContentType"] == "application/x-ndjson"

        # Verify metadata includes record_count
        metadata = call_args.kwargs["Metadata"]
        assert metadata["record_count"] == "2"

    def test_write_raw_page_empty_data(self):
        """Test write_raw_page with empty data list."""
        from ingestion.api.s3_writer import S3Writer, S3WriterConfig

        config = S3WriterConfig(raw_bucket="test-bucket")
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"abc123"'}
        writer = S3Writer(config, s3_client=mock_s3)

        writer.write_raw_page(
            ingest_date="2025-01-15",
            batch_id="wb_test",
            indicator="NY.GDP.MKTP.KD.ZG",
            page=1,
            data=[],
        )

        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        body = call_args.kwargs["Body"]
        lines = body.decode("utf-8").strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == ""  # Empty file

        metadata = call_args.kwargs["Metadata"]
        assert metadata["record_count"] == "0"

    def test_write_quarantine_outputs_json(self):
        """Test that write_quarantine outputs valid JSON."""
        from ingestion.api.s3_writer import S3Writer, S3WriterConfig

        config = S3WriterConfig(raw_bucket="test-bucket")
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"abc123"'}
        writer = S3Writer(config, s3_client=mock_s3)

        writer.write_quarantine(
            ingest_date="2025-01-15",
            batch_id="wb_test",
            indicator="NY.GDP.MKTP.KD.ZG",
            page=1,
            error_type="parse_error",
            error_message="Failed to parse",
            raw_data=[{"country": {"id": "XXX"}}],
        )

        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        body = call_args.kwargs["Body"]

        # Verify it's valid JSON (not NDJSON)
        payload = json.loads(body.decode("utf-8"))
        assert payload["error_type"] == "parse_error"
        assert payload["error_message"] == "Failed to parse"
        assert payload["raw_data"] == [{"country": {"id": "XXX"}}]
        assert call_args.kwargs["ContentType"] == "application/json"

    def test_s3_key_format(self):
        """Test that S3 keys follow the expected pattern."""
        from ingestion.api.s3_writer import S3Writer, S3WriterConfig

        config = S3WriterConfig(
            raw_bucket="test-bucket",
            raw_prefix="api/world_bank_indicators",
            quarantine_prefix="quarantine/api/world_bank_indicators",
        )
        writer = S3Writer(config, s3_client=MagicMock())

        raw_key = writer._build_raw_key("2025-01-15", "wb_abc123", "NY.GDP.MKTP.KD.ZG", 1)
        assert raw_key == "api/world_bank_indicators/ingest_date=2025-01-15/wb_abc123/NY_GDP_MKTP_KD_ZG_page_0001.json"

        quarantine_key = writer._build_quarantine_key("2025-01-15", "wb_abc123", "NY.GDP.MKTP.KD.ZG", 1, "parse_error")
        assert quarantine_key == "quarantine/api/world_bank_indicators/ingest_date=2025-01-15/wb_abc123/NY_GDP_MKTP_KD_ZG_page_0001_parse_error.json"


class TestS3WriterConfig:
    """Tests for S3WriterConfig."""

    def test_defaults(self):
        """Test default values."""
        from ingestion.api.s3_writer import S3WriterConfig

        config = S3WriterConfig(raw_bucket="test-bucket")
        assert config.raw_bucket == "test-bucket"
        assert config.raw_prefix == "api/world_bank_indicators"
        assert config.quarantine_prefix == "quarantine/api/world_bank_indicators"


class TestBatchIdAndIngestDate:
    """Tests for batch ID and ingest date generation."""

    def test_generate_batch_id_format(self):
        """Test batch ID format."""
        from ingestion.api.s3_writer import generate_batch_id

        batch_id = generate_batch_id()
        assert batch_id.startswith("wb_")
        # Format: wb_YYYYMMDDTHHMMSSZ_xxxxxxxx
        parts = batch_id.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 16  # YYYYMMDDTHHMMSSZ (16 chars)
        assert len(parts[2]) == 8   # uuid hex

    def test_get_ingest_date_format(self):
        """Test ingest date format."""
        from ingestion.api.s3_writer import get_ingest_date

        ingest_date = get_ingest_date()
        assert len(ingest_date) == 10  # YYYY-MM-DD
        assert ingest_date[4] == "-"
        assert ingest_date[7] == "-"