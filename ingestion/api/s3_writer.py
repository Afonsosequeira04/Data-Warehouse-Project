"""S3 writer utilities for raw data and quarantine storage."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3WriterConfig:
    """Configuration for S3 writer."""

    raw_bucket: str
    raw_prefix: str = "api/world_bank_indicators"
    quarantine_prefix: str = "quarantine/api/world_bank_indicators"


@dataclass
class WriteResult:
    """Result of an S3 write operation."""

    bucket: str
    key: str
    size_bytes: int
    etag: str
    written_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class S3Writer:
    """Writes raw API responses to S3 and handles quarantine for invalid data."""

    def __init__(self, config: S3WriterConfig, s3_client: Any | None = None):
        self.config = config
        self._s3 = s3_client or boto3.client("s3")

    def _build_raw_key(self, ingest_date: str, batch_id: str, indicator: str, page: int) -> str:
        """Build the S3 key for a raw API response page."""
        safe_indicator = indicator.replace(".", "_")
        return f"{self.config.raw_prefix}/ingest_date={ingest_date}/{batch_id}/{safe_indicator}_page_{page:04d}.json"

    def _build_quarantine_key(
        self, ingest_date: str, batch_id: str, indicator: str, page: int, error_type: str
    ) -> str:
        """Build the S3 key for a quarantined response."""
        safe_indicator = indicator.replace(".", "_")
        safe_error = error_type.replace(" ", "_").lower()
        return (
            f"{self.config.quarantine_prefix}/ingest_date={ingest_date}/"
            f"{batch_id}/{safe_indicator}_page_{page:04d}_{safe_error}.json"
        )

    def write_raw_page(
        self,
        ingest_date: str,
        batch_id: str,
        indicator: str,
        page: int,
        data: list[dict],
        metadata: dict | None = None,
    ) -> WriteResult:
        """Write a raw API response page to S3.

        Args:
            ingest_date: Ingestion date in YYYY-MM-DD format
            batch_id: Unique batch identifier
            indicator: World Bank indicator code
            page: Page number
            data: Raw API response data (list of observations)
            metadata: Optional additional metadata to include

        Returns:
            WriteResult with bucket, key, size, and etag
        """
        key = self._build_raw_key(ingest_date, batch_id, indicator, page)

        payload = {
            "source": "world_bank_indicators",
            "indicator": indicator,
            "page": page,
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(data),
            "data": data,
        }

        if metadata:
            payload["metadata"] = metadata

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        try:
            response = self._s3.put_object(
                Bucket=self.config.raw_bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                Metadata={
                    "source": "world_bank_indicators",
                    "indicator": indicator,
                    "batch_id": batch_id,
                    "ingest_date": ingest_date,
                    "page": str(page),
                },
            )
        except ClientError as e:
            logger.error(f"Failed to write raw page to S3: {e}")
            raise

        return WriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=response["ETag"].strip('"'),
        )

    def write_quarantine(
        self,
        ingest_date: str,
        batch_id: str,
        indicator: str,
        page: int,
        error_type: str,
        error_message: str,
        raw_data: list[dict] | None = None,
        response_metadata: dict | None = None,
    ) -> WriteResult:
        """Write a structurally invalid response to quarantine.

        Per ADR-002, structurally invalid responses (wrong schema, error payloads at HTTP 200, etc.)
        go to quarantine with error metadata, never to raw or Bronze.

        Args:
            ingest_date: Ingestion date in YYYY-MM-DD format
            batch_id: Unique batch identifier
            indicator: World Bank indicator code
            page: Page number
            error_type: Classification of error (e.g., "invalid_schema", "api_error_payload", "parse_error")
            error_message: Human-readable error description
            raw_data: Optional raw data that failed validation
            response_metadata: Optional response metadata (HTTP status, headers, etc.)

        Returns:
            WriteResult with bucket, key, size, and etag
        """
        key = self._build_quarantine_key(ingest_date, batch_id, indicator, page, error_type)

        payload = {
            "source": "world_bank_indicators",
            "indicator": indicator,
            "page": page,
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "raw_data": raw_data,
            "response_metadata": response_metadata or {},
        }

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        try:
            response = self._s3.put_object(
                Bucket=self.config.raw_bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                Metadata={
                    "source": "world_bank_indicators",
                    "indicator": indicator,
                    "batch_id": batch_id,
                    "ingest_date": ingest_date,
                    "page": str(page),
                    "error_type": error_type,
                    "quarantined": "true",
                },
            )
        except ClientError as e:
            logger.error(f"Failed to write quarantine object to S3: {e}")
            raise

        logger.warning(
            f"Quarantined {indicator} page {page} (batch {batch_id}): {error_type} - {error_message}"
        )

        return WriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=response["ETag"].strip('"'),
        )


def generate_batch_id() -> str:
    """Generate a unique batch identifier."""
    return f"wb_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def get_ingest_date() -> str:
    """Get the current ingestion date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")