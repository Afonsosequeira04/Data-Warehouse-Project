#!/usr/bin/env python3
"""Databricks validation: run rendered SQL against a scratch table.

Uses shared ingestion.databricks_sql module for SQL rendering, statement splitting,
and execution - same code as the DAG.
"""

from __future__ import annotations

import os
import sys

# Add project root to path so we can import ingestion.databricks_sql
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.databricks_sql import (
    execute_sql_batch,
    normalize_host,
    render_sql_template,
    split_sql_statements,
)

# Get Databricks credentials from environment (set from Secrets Manager)
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN")
DATABRICKS_WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID")

if not all([DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID]):
    print("ERROR: DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID must be set")
    sys.exit(1)

# Configuration from the local ingestion test
RAW_BUCKET = "dwh-raw-data-9015f2"
RAW_PREFIX = "api/world_bank_indicators"
BATCH_ID = "wb_20261014T114451Z_c823af23"
INGEST_DATE = "2026-10-14"
CATALOG = "dwh_dev"
SCHEMA = "bronze"
SOURCE_NAME = "world_bank_indicators"
SCRATCH_TABLE = f"{CATALOG}.{SCHEMA}.{SOURCE_NAME}_p3test"
RAW_PATH = f"s3://{RAW_BUCKET}/{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}/"


def main():
    # Read SQL template
    sql_path = "ingestion/sql/bronze_world_bank_indicators.sql"
    with open(sql_path) as f:
        sql_template = f.read()

    # Render SQL with batch parameters using shared utility
    sql = render_sql_template(
        sql_template=sql_template,
        catalog=CATALOG,
        schema=SCHEMA,
        raw_path=RAW_PATH,
        batch_id=BATCH_ID,
        batch_date=INGEST_DATE,
    )

    # Override table name for scratch table
    sql = sql.replace(
        f"{CATALOG}.{SCHEMA}.{SOURCE_NAME}",
        SCRATCH_TABLE
    )

    print("Rendered SQL:")
    print("=" * 60)
    print(sql)
    print("=" * 60)

    # Split into executable statements using shared utility
    statements = split_sql_statements(sql)

    print(f"\nExecuting {len(statements)} statements against scratch table {SCRATCH_TABLE}...")

    try:
        # Execute statements using shared utility
        results = execute_sql_batch(
            host=normalize_host(DATABRICKS_HOST),
            token=DATABRICKS_TOKEN,
            warehouse_id=DATABRICKS_WAREHOUSE_ID,
            statements=statements,
            wait_timeout="50s",
        )

        for i, result in enumerate(results, 1):
            print(f"\nStatement {i}/{len(results)}:")
            print(f"  Status: {result.get('status', {}).get('state')}")
            print(f"  Statement ID: {result.get('statement_id')}")
            if result.get("result"):
                if "data_array" in result["result"] and result["result"]["data_array"]:
                    print(f"  Result data_array: {result['result']['data_array']}")

        # Verification query
        verify_sql = f"""
            SELECT
                COUNT(*) as row_count,
                COUNT(DISTINCT _batch_id) as batch_count,
                MIN(year) as min_year,
                MAX(year) as max_year,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) as non_null_values
            FROM {SCRATCH_TABLE}
            WHERE _batch_id = '{BATCH_ID}'
        """

        print("\nRunning verification query...")
        from ingestion.databricks_sql import execute_statement, parse_verification_row

        result = execute_statement(
            host=normalize_host(DATABRICKS_HOST),
            token=DATABRICKS_TOKEN,
            warehouse_id=DATABRICKS_WAREHOUSE_ID,
            statement=verify_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )

        # Parse result
        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row = rows[0]

        # Parse verification row using shared utility (handles string->int casting)
        actual_count, batch_count, min_year, max_year, non_null_values = parse_verification_row(row)

        print("\nVerification Results:")
        print(f"  Row count: {actual_count}")
        print(f"  Distinct batch_ids: {batch_count}")
        print(f"  Year range: {min_year} - {max_year}")
        print(f"  Non-null values: {non_null_values}")

        if batch_count != 1:
            raise ValueError(f"Expected 1 distinct _batch_id, found {batch_count}")
        if actual_count == 0:
            raise ValueError("No rows loaded into Bronze table")

        # Sample rows
        sample_sql = f"""
            SELECT country_id, country_name, indicator_id, year, value, _batch_id
            FROM {SCRATCH_TABLE}
            WHERE _batch_id = '{BATCH_ID}'
            LIMIT 5
        """
        print("\nSample rows:")
        sample_result = execute_statement(
            host=normalize_host(DATABRICKS_HOST),
            token=DATABRICKS_TOKEN,
            warehouse_id=DATABRICKS_WAREHOUSE_ID,
            statement=sample_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )
        rows = sample_result.get("result", {}).get("data_array", [])
        for row in rows:
            print(f"  {row}")

        return 0

    finally:
        # Clean up: drop scratch table
        drop_sql = f"DROP TABLE IF EXISTS {SCRATCH_TABLE}"
        print(f"\nCleaning up: dropping scratch table {SCRATCH_TABLE}...")
        from ingestion.databricks_sql import execute_statement
        execute_statement(
            host=normalize_host(DATABRICKS_HOST),
            token=DATABRICKS_TOKEN,
            warehouse_id=DATABRICKS_WAREHOUSE_ID,
            statement=drop_sql,
            wait_timeout="10s",
        )
        print("  Done.")


if __name__ == "__main__":
    sys.exit(main())