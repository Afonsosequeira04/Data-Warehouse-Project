#!/usr/bin/env python3
"""Local ingestion test: fetch one FRED series and write NDJSON to S3.

Requires a FRED API key in the environment; it is never printed or logged.

Usage: AWS_PROFILE=dwh FRED_API_KEY=... python scripts/local_ingest_fred_test.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")

from ingestion.api.fred_client import FredClient, FredConfig
from ingestion.api.fred_writer import (
    FredWriter,
    FredWriterConfig,
    generate_batch_id,
    get_ingest_date,
)


def main():
    # Configuration
    raw_bucket = "dwh-raw-data-9015f2"
    raw_prefix = "api/fred_economic_series"
    quarantine_prefix = "quarantine/api/fred_economic_series"
    series_id = "UNRATE"  # Unemployment rate
    max_pages = 1  # Just one page for testing

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("ERROR: FRED_API_KEY is not set in the environment.")
        return 1

    print(f"Fetching {series_id} (max {max_pages} page)...")

    # Initialize clients
    config = FredConfig(
        api_key=api_key,
        series_ids=(series_id,),
        max_pages=max_pages,
        rate_limit_rps=2.0,  # FRED allows 120 requests per minute
    )
    writer_config = FredWriterConfig(
        raw_bucket=raw_bucket,
        raw_prefix=raw_prefix,
        quarantine_prefix=quarantine_prefix,
    )
    writer = FredWriter(writer_config)
    client = FredClient(config)

    batch_id = generate_batch_id()
    ingest_date = get_ingest_date()

    print(f"Batch ID: {batch_id}")
    print(f"Ingest date: {ingest_date}")

    try:
        total_records = 0
        rejections = 0
        pages_written = 0

        for page in client.fetch_series(series_id):
            if page.quarantine_reason is not None:
                print(f"  Quarantining page at offset {page.offset}: {page.quarantine_reason}")
                writer.write_quarantine(
                    ingest_date=ingest_date,
                    batch_id=batch_id,
                    series_id=series_id,
                    error_type="page_error",
                    error_message=page.quarantine_reason,
                    raw_data=page.quarantine_raw,
                    response_metadata={"offset": page.offset, "count": page.count},
                )
                break

            rejections += len(page.rejections)
            if not page.observations:
                print(f"  Page offset {page.offset}: no observations")
                continue

            print(f"  Page offset {page.offset}: {len(page.observations)} observations")

            result = writer.write_series(
                ingest_date=ingest_date,
                batch_id=batch_id,
                series_id=series_id,
                observations=page.observations,
            )
            pages_written += 1
            total_records += len(page.observations)
            print(f"    Wrote to {result.key} ({len(page.observations)} records)")

            # Only do one page for testing
            break

        if pages_written == 0:
            print("ERROR: No pages written!")
            return 1

        raw_path = (
            f"s3://{raw_bucket}/{raw_prefix}/ingest_date={ingest_date}/"
            f"{batch_id}/{series_id}.ndjson"
        )
        print("\nSUCCESS!")
        print(f"  Batch ID: {batch_id}")
        print(f"  Raw path: {raw_path}")
        print(f"  Pages written: {pages_written}")
        print(f"  Total records: {total_records}")
        print(f"  Rejected rows: {rejections}")

        return 0

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
