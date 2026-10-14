#!/usr/bin/env python3
"""Databricks validation: run rendered SQL against a scratch table."""

from __future__ import annotations

import json
import os
import sys
import time

import requests

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


def execute_statement(statement: str, wait_timeout: str = "50s") -> dict:
    """Execute a single SQL statement via Databricks Statement Execution API."""
    url = f"https://{DATABRICKS_HOST}/api/2.0/sql/statements"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "statement": statement,
        "warehouse_id": DATABRICKS_WAREHOUSE_ID,
        "wait_timeout": wait_timeout,
        "disposition": "EXTERNAL_LINKS",
        "format": "JSON_ARRAY",
    }

    # Submit statement
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()

    statement_id = result.get("statement_id")
    if not statement_id:
        raise RuntimeError(f"No statement_id in response: {result}")

    # Poll for completion
    status_url = f"{url}/{statement_id}"
    status_headers = {"Authorization": f"Bearer {DATABRICKS_TOKEN}"}

    while True:
        status_resp = requests.get(status_url, headers=status_headers, timeout=30)
        status_resp.raise_for_status()
        status_data = status_resp.json()

        state = status_data.get("status", {}).get("state", "")
        if state in ("SUCCEEDED", "FAILED", "CANCELED"):
            break
        time.sleep(1)

    if state != "SUCCEEDED":
        error_msg = status_data.get("status", {}).get("error", {}).get("message", "Unknown error")
        raise RuntimeError(f"Statement {statement_id} failed: {error_msg}")

    return status_data


def main():
    # Read SQL template
    sql_path = "ingestion/sql/bronze_world_bank_indicators.sql"
    with open(sql_path) as f:
        sql_template = f.read()

    # Render SQL with batch parameters
    sql = sql_template.replace("${catalog}", CATALOG) \
                     .replace("${schema}", SCHEMA) \
                     .replace("${raw_path}", RAW_PATH) \
                     .replace("${batch_id}", BATCH_ID) \
                     .replace("${batch_date}", INGEST_DATE)

    # Override table name for scratch table
    sql = sql.replace(
        f"{CATALOG}.{SCHEMA}.{SOURCE_NAME}",
        SCRATCH_TABLE
    )

    print("Rendered SQL:")
    print("=" * 60)
    print(sql)
    print("=" * 60)

    # Split into individual statements, filtering out comment-only statements
    raw_statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
    # Filter out statements that are only comments or empty
    statements = [
        stmt for stmt in raw_statements
        if not all(line.strip().startswith("--") or not line.strip() for line in stmt.split("\n"))
    ]

    print(f"\nExecuting {len(statements)} statements against scratch table {SCRATCH_TABLE}...")

    try:
        for i, statement in enumerate(statements, 1):
            print(f"\nStatement {i}/{len(statements)}:")
            print(statement[:200] + "..." if len(statement) > 200 else statement)
            result = execute_statement(statement)
            print(f"  Status: {result.get('status', {}).get('state')}")
            print(f"  Statement ID: {result.get('statement_id')}")
            # Print full result for debugging
            if "result" in result:
                print(f"  Full result keys: {list(result['result'].keys())}")
                if "external_links" in result["result"]:
                    print(f"  external_links: {result['result']['external_links']}")
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

        print(f"\nRunning verification query...")
        result = execute_statement(verify_sql)

        # Parse result
        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row = rows[0]
        actual_count = row[0]
        batch_count = row[1]
        min_year = row[2]
        max_year = row[3]
        non_null_values = row[4]

        print(f"\nVerification Results:")
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
        print(f"\nSample rows:")
        result = execute_statement(sample_sql)
        rows = result.get("result", {}).get("data_array", [])
        for row in rows:
            print(f"  {row}")

        return 0

    finally:
        # Clean up: drop scratch table
        drop_sql = f"DROP TABLE IF EXISTS {SCRATCH_TABLE}"
        print(f"\nCleaning up: dropping scratch table {SCRATCH_TABLE}...")
        execute_statement(drop_sql, wait_timeout="10s")
        print("  Done.")


if __name__ == "__main__":
    sys.exit(main())