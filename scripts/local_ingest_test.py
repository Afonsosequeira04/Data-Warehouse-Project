#!/usr/bin/env python3
"""Local ingestion test: fetch one indicator page from World Bank API and write NDJSON to S3.

Usage: AWS_PROFILE=dwh python scripts/local_ingest_test.py
"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

from ingestion.api.world_bank_client import WorldBankClient, WorldBankConfig
from ingestion.api.s3_writer import S3Writer, S3WriterConfig, generate_batch_id, get_ingest_date


def main():
    # Configuration
    raw_bucket = "dwh-raw-data-9015f2"
    raw_prefix = "api/world_bank_indicators"
    quarantine_prefix = "quarantine/api/world_bank_indicators"
    indicator = "NY.GDP.MKTP.KD.ZG"  # GDP growth
    max_pages = 1  # Just one page for testing

    print(f"Fetching {indicator} (max {max_pages} page)...")

    # Initialize clients
    config = WorldBankConfig(
        indicators=(indicator,),
        max_pages=max_pages,
        rate_limit_rps=10.0,  # Be respectful
    )
    s3_config = S3WriterConfig(
        raw_bucket=raw_bucket,
        raw_prefix=raw_prefix,
        quarantine_prefix=quarantine_prefix,
    )
    s3_writer = S3Writer(s3_config)
    client = WorldBankClient(config)

    batch_id = generate_batch_id()
    ingest_date = get_ingest_date()

    print(f"Batch ID: {batch_id}")
    print(f"Ingest date: {ingest_date}")

    try:
        total_records = 0
        pages_written = 0

        for page, raw_data in client.fetch_raw_pages(indicator):
            print(f"  Page {page}: {len(raw_data)} records")

            # Validate by attempting to parse
            parsed_count = 0
            for item in raw_data:
                obs = client._parse_observation(item, indicator)
                if obs is not None:
                    parsed_count += 1

            if parsed_count == 0 and raw_data:
                print(f"    WARNING: No records parsed, quarantining...")
                s3_writer.write_quarantine(
                    ingest_date=ingest_date,
                    batch_id=batch_id,
                    indicator=indicator,
                    page=page,
                    error_type="parse_error",
                    error_message="All records in page failed to parse",
                    raw_data=raw_data,
                )
                continue

            # Write valid raw page to S3 as NDJSON
            result = s3_writer.write_raw_page(
                ingest_date=ingest_date,
                batch_id=batch_id,
                indicator=indicator,
                page=page,
                data=raw_data,
                metadata={"parsed_count": parsed_count},
            )
            pages_written += 1
            total_records += parsed_count
            print(f"    Wrote to {result.key} ({parsed_count} records)")

            # Only do one page for testing
            break

        if pages_written == 0:
            print("ERROR: No pages written!")
            return 1

        raw_path = f"s3://{raw_bucket}/{raw_prefix}/ingest_date={ingest_date}/{batch_id}/"
        print(f"\nSUCCESS!")
        print(f"  Batch ID: {batch_id}")
        print(f"  Raw path: {raw_path}")
        print(f"  Pages written: {pages_written}")
        print(f"  Total records: {total_records}")

        return 0

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())