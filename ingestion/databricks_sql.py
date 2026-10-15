"""Shared Databricks SQL execution utilities.

This module provides common functionality for:
- Normalizing Databricks host URLs
- Rendering SQL templates with batch parameters
- Splitting SQL into executable statements (dropping comment-only chunks)
- Executing statements via Databricks Statement Execution API
- Parsing verification results (casting string values to int)
"""

from __future__ import annotations

import time
from typing import Any

import requests


def normalize_host(host: str) -> str:
    """Normalize Databricks host to a base URL without trailing slash.

    Accepts:
    - "https://dbc-x.cloud.databricks.com/"
    - "dbc-x.cloud.databricks.com"
    - "https://dbc-x.cloud.databricks.com"

    Returns:
    - "https://dbc-x.cloud.databricks.com"
    """
    host = host.strip()
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "https://" + host
    return host.rstrip("/")


def render_sql_template(
    sql_template: str,
    catalog: str,
    schema: str,
    raw_path: str,
    batch_id: str,
    batch_date: str,
) -> str:
    """Render SQL template with batch parameters."""
    return (
        sql_template.replace("${catalog}", catalog)
        .replace("${schema}", schema)
        .replace("${raw_path}", raw_path)
        .replace("${batch_id}", batch_id)
        .replace("${batch_date}", batch_date)
    )


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into executable statements, dropping comment-only chunks.

    Handles the case where the SQL file contains a commented verification query
    at the end that also contains a semicolon.
    """
    # Split by semicolon
    raw_statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]

    # Filter out statements that are only comments or empty
    executable = []
    for stmt in raw_statements:
        # Check if all non-empty lines are comments
        lines = [line.strip() for line in stmt.split("\n") if line.strip()]
        if not lines:
            continue
        if all(line.startswith("--") for line in lines):
            continue
        executable.append(stmt)

    return executable


def execute_statement(
    host: str,
    token: str,
    warehouse_id: str,
    statement: str,
    wait_timeout: str = "50s",
    disposition: str = "INLINE",
    format: str = "JSON_ARRAY",
) -> dict[str, Any]:
    """Execute a single SQL statement via Databricks Statement Execution API.

    Args:
        host: Databricks host (e.g., "dbc-x.cloud.databricks.com" or "https://dbc-x.cloud.databricks.com/")
        token: Databricks personal access token
        warehouse_id: SQL Warehouse ID
        statement: SQL statement to execute
        wait_timeout: Max time to wait for statement completion (e.g., "50s")
        disposition: Result disposition - "INLINE" for small results, "EXTERNAL_LINKS" for large
        format: Result format - "JSON_ARRAY" returns all values as strings

    Returns:
        Full response JSON with result.data_array on success

    Raises:
        RuntimeError: If statement fails or times out
        requests.HTTPError: If HTTP request fails
    """
    base_url = normalize_host(host)
    url = f"{base_url}/api/2.0/sql/statements"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "statement": statement,
        "warehouse_id": warehouse_id,
        "wait_timeout": wait_timeout,
        "disposition": disposition,
        "format": format,
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
    status_headers = {"Authorization": f"Bearer {token}"}

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


def parse_verification_row(row: list[str]) -> tuple[int, int, int, int, int]:
    """Parse a verification query result row, casting string values to int.

    Databricks JSON_ARRAY format returns all values as strings.
    Expected row: [row_count, batch_count, min_year, max_year, non_null_values]

    Returns:
        tuple of (row_count, batch_count, min_year, max_year, non_null_values) as ints
    """
    if len(row) != 5:
        raise ValueError(f"Expected 5 columns, got {len(row)}: {row}")

    try:
        row_count = int(row[0])
        batch_count = int(row[1])
        min_year = int(row[2]) if row[2] is not None else 0
        max_year = int(row[3]) if row[3] is not None else 0
        non_null_values = int(row[4]) if row[4] is not None else 0
    except (ValueError, TypeError) as e:
        raise ValueError(f"Failed to parse verification row {row}: {e}")

    return row_count, batch_count, min_year, max_year, non_null_values


def execute_sql_batch(
    host: str,
    token: str,
    warehouse_id: str,
    statements: list[str],
    wait_timeout: str = "50s",
) -> list[dict[str, Any]]:
    """Execute multiple SQL statements sequentially.

    Returns list of statement results.
    """
    results = []
    for i, statement in enumerate(statements, 1):
        result = execute_statement(
            host=host,
            token=token,
            warehouse_id=warehouse_id,
            statement=statement,
            wait_timeout=wait_timeout,
        )
        results.append(result)
    return results