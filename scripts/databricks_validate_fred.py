#!/usr/bin/env python3
"""Databricks validation for FRED: run rendered SQL against a scratch table.

Uses the shared ingestion.databricks_sql module for SQL rendering, statement
splitting, and execution - the same code as the FRED DAG.

The FRED SQL template hard-codes the series id as a literal ('${series_id}')
and reads one NDJSON file per series
(s3://<bucket>/api/fred_economic_series/ingest_date=<date>/<batch>/<SERIES>.ndjson),
so the COPY INTO statement must be rendered and executed once per series while
the CREATE TABLE runs only once.
"""

from __future__ import annotations

import os
import sys

# Add project root to path so we can import ingestion.databricks_sql
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.databricks_sql import (
    execute_sql_batch,
    execute_statement,
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

# Configuration from the local FRED ingestion test (scripts/local_ingest_fred_test.py)
# BATCH_ID and INGEST_DATE must match the batch written by that script.
RAW_BUCKET = "dwh-raw-data-9015f2"
RAW_PREFIX = "api/fred_economic_series"
SERIES_IDS = ["UNRATE"]
BATCH_ID = "fred_20261018T000000Z_000000000000"
INGEST_DATE = "2026-10-18"
CATALOG = "dwh_dev"
SCHEMA = "bronze"
SOURCE_NAME = "fred_economic_series"
SCRATCH_TABLE = f"{CATALOG}.{SCHEMA}.{SOURCE_NAME}_p4test"
SQL_PATH = "ingestion/sql/bronze_fred_economic_series.sql"


def _render_series_sql(sql_template: str, series_id: str) -> str:
    """Render the FRED SQL template for one series.

    Points raw_path at that series' NDJSON file and substitutes the literal
    series id used by the COPY INTO SELECT.
    """
    raw_path = (
        f"s3://{RAW_BUCKET}/{RAW_PREFIX}/ingest_date={INGEST_DATE}/{BATCH_ID}/{series_id}.ndjson"
    )
    sql = render_sql_template(
        sql_template=sql_template,
        catalog=CATALOG,
        schema=SCHEMA,
        raw_path=raw_path,
        batch_id=BATCH_ID,
        batch_date=INGEST_DATE,
        extra_replacements={"${series_id}": series_id},
    )
    # Override table name for scratch table
    return sql.replace(f"{CATALOG}.{SCHEMA}.{SOURCE_NAME}", SCRATCH_TABLE)


def _parse_fred_verification_row(row: list[str]) -> tuple[int, int, str, str, int]:
    """Parse a FRED verification row.

    Databricks JSON_ARRAY format returns all values as strings.
    Expected row: [row_count, series_count, min_date, max_date, non_null_values]
    """
    if len(row) != 5:
        raise ValueError(f"Expected 5 columns, got {len(row)}: {row}")

    try:
        row_count = int(row[0])
        series_count = int(row[1])
        min_date = row[2] if row[2] is not None else ""
        max_date = row[3] if row[3] is not None else ""
        non_null_values = int(row[4]) if row[4] is not None else 0
    except (ValueError, TypeError) as e:
        raise ValueError(f"Failed to parse FRED verification row {row}: {e}")

    return row_count, series_count, min_date, max_date, non_null_values


def main():
    # Read SQL template
    with open(SQL_PATH) as f:
        sql_template = f.read()

    # Render one render per series; keep CREATE TABLE from the first render only,
    # then append each additional series' COPY INTO statement.
    statements: list[str] = []
    for index, series_id in enumerate(SERIES_IDS):
        rendered = _render_series_sql(sql_template, series_id)
        series_statements = split_sql_statements(rendered)
        if index == 0:
            print("Rendered SQL:")
            print("=" * 60)
            print(rendered)
            print("=" * 60)
            statements.extend(series_statements)
        else:
            statements.extend(series_statements[1:])

    print(f"\nExecuting {len(statements)} statements against scratch table {SCRATCH_TABLE}...")

    try:
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
            if result.get("result") and result["result"].get("data_array"):
                print(f"  Result data_array: {result['result']['data_array']}")

        # Verification query
        verify_sql = f"""
            SELECT
                COUNT(*) as row_count,
                COUNT(DISTINCT series_id) as series_count,
                MIN(`date`) as min_date,
                MAX(`date`) as max_date,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) as non_null_values
            FROM {SCRATCH_TABLE}
            WHERE _batch_id = '{BATCH_ID}'
        """

        print("\nRunning verification query...")
        result = execute_statement(
            host=normalize_host(DATABRICKS_HOST),
            token=DATABRICKS_TOKEN,
            warehouse_id=DATABRICKS_WAREHOUSE_ID,
            statement=verify_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )

        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row_count, series_count, min_date, max_date, non_null_values = (
            _parse_fred_verification_row(rows[0])
        )

        print("\nVerification Results:")
        print(f"  Row count: {row_count}")
        print(f"  Distinct series_ids: {series_count}")
        print(f"  Date range: {min_date} - {max_date}")
        print(f"  Non-null values: {non_null_values}")

        if row_count == 0:
            raise ValueError("No rows loaded into Bronze table")
        if series_count != len(SERIES_IDS):
            raise ValueError(
                f"Expected {len(SERIES_IDS)} distinct series_id, found {series_count}"
            )

        # Sample rows
        sample_sql = f"""
            SELECT series_id, `date`, value, realtime_start, realtime_end, _batch_id
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
        for sample_row in sample_result.get("result", {}).get("data_array", []):
            print(f"  {sample_row}")

        return 0

    finally:
        # Clean up: drop scratch table
        drop_sql = f"DROP TABLE IF EXISTS {SCRATCH_TABLE}"
        print(f"\nCleaning up: dropping scratch table {SCRATCH_TABLE}...")
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
