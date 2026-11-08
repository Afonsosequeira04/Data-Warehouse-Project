"""Immutable CSV raw storage for NASA FIRMS fires.

Wraps :class:`ingestion.core.s3_writer.RawS3Writer` and stores the original
area CSV byte for byte (not NDJSON) under
``api/nasa_firms_fires/ingest_date=YYYY-MM-DD/<batch_id>/<name>.csv``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ingestion.core.s3_writer import RawS3Writer, RawS3WriterConfig, WriteResult

logger = logging.getLogger(__name__)

RAW_SOURCE_SYSTEM = "nasa_firms_fires"
RAW_PREFIX = "api/nasa_firms_fires"


class FirmsRawWriter:
    """Thin CSV writer around the shared raw/quarantine S3 writer.

    The shared ``RawS3Writer.write_raw_page`` only supports NDJSON, so this
    writer calls ``s3.put_object`` directly with ``ContentType="text/csv"``
    while reusing ``RawS3Writer._build_raw_key`` (extension="csv") and
    ``RawS3Writer.write_quarantine``.
    """

    def __init__(self, config: RawS3WriterConfig, s3_client=None):
        self.config = config
        self._writer = RawS3Writer(config, s3_client=s3_client)

    @property
    def s3(self):
        return self._writer.s3

    @staticmethod
    def object_name(data_id: str, data_date: str) -> str:
        """Build the raw object name: ``<safe_token(data_id)>_<YYYY-MM-DD>``.

        No extension is included; the writer appends it based on the payload
        type (``.csv`` for raw, ``_<error>.json`` for quarantine).
        """
        from ingestion.core.ids import safe_token

        token = safe_token(data_id, lowercase=True)
        return f"{token}_{data_date}"

    @staticmethod
    def raw_batch_prefix(raw_prefix: str, ingest_date: str, batch_id: str) -> str:
        """Build ``<raw_prefix>/ingest_date=<date>/<batch_id>``."""
        return f"{raw_prefix}/ingest_date={ingest_date}/{batch_id}"

    def write_csv(
        self,
        *,
        ingest_date: str,
        batch_id: str,
        data_id: str,
        data_date: str,
        body: bytes,
        row_count: int,
        metadata: dict | None = None,
    ) -> WriteResult:
        """Store one raw CSV byte for byte and return the write result."""
        from ingestion.core.ids import validate_ingest_date

        validate_ingest_date(ingest_date)
        name = self.object_name(data_id, data_date)
        key = self._writer._build_raw_key(
            ingest_date, batch_id, name, extension="csv"
        )

        object_metadata = {
            "source": self.config.source_system,
            "data_id": data_id,
            "data_date": data_date,
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "row_count": str(row_count),
        }
        if metadata:
            for metadata_key, metadata_value in metadata.items():
                object_metadata[str(metadata_key).lower()] = str(metadata_value)

        try:
            response = self.s3.put_object(
                Bucket=self.config.raw_bucket,
                Key=key,
                Body=bytes(body),
                ContentType="text/csv",
                Metadata=object_metadata,
            )
        except Exception:  # botocore ClientError or any S3 failure
            logger.error("Failed to write raw CSV to S3: %s", key)
            raise

        return WriteResult(
            bucket=self.config.raw_bucket,
            key=key,
            size_bytes=len(body),
            etag=response["ETag"].strip('"'),
            record_count=row_count,
        )

    def write_quarantine(
        self,
        *,
        ingest_date: str,
        batch_id: str,
        data_id: str,
        data_date: str,
        error_type: str,
        error_message: str,
        raw_data=None,
        response_metadata: dict | None = None,
    ) -> WriteResult:
        """Write a structurally invalid payload to quarantine."""
        name = self.object_name(data_id, data_date)
        return self._writer.write_quarantine(
            ingest_date=ingest_date,
            batch_id=batch_id,
            name=name,
            error_type=error_type,
            error_message=error_message,
            raw_data=raw_data,
            response_metadata=response_metadata,
        )

    def existing_data_dates(self, data_id: str) -> set[str]:
        """Return the set of data dates already stored for ``data_id``.

        Paginates ``list_objects_v2`` across every ``ingest_date=`` prefix and
        keeps ``.csv`` keys whose filename starts with ``<token>_``.
        """
        from ingestion.core.ids import safe_token

        token = safe_token(data_id, lowercase=True)
        prefix = f"{self.config.raw_prefix}/ingest_date="

        dates: set[str] = set()
        continuation_token = None
        while True:
            kwargs = {
                "Bucket": self.config.raw_bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self.s3.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".csv"):
                    continue
                filename = key.rsplit("/", 1)[-1]
                if filename.startswith(f"{token}_"):
                    date_part = filename[len(token) + 1 : -len(".csv")]
                    dates.add(date_part)
            if not response.get("IsTruncated"):
                break
            continuation_token = response["NextContinuationToken"]
        return dates
