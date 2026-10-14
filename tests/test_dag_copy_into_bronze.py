"""Task-level tests for copy_into_bronze and verify_bronze_load in the ingest_world_bank DAG."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import responses


def _load_ingest_world_bank_dag():
    """Load the ingest_world_bank DAG from the real file."""
    repo_root = Path(__file__).parent.parent
    dag_file = repo_root / "orchestration" / "dags" / "ingest_world_bank.py"
    namespace = {"__file__": str(dag_file)}
    with open(dag_file) as f:
        code = compile(f.read(), str(dag_file), "exec")
        exec(code, namespace)
    return namespace["dag"]


def _make_fetch_result(batch_id: str = "wb_test_123") -> dict:
    """Create a standard fetch_result dict for testing."""
    return {
        "batch_id": batch_id,
        "ingest_date": "2025-01-15",
        "raw_bucket": "test-bucket",
        "raw_path": f"s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/{batch_id}/",
        "catalog": "dwh_dev",
        "schema": "bronze",
        "total_pages_written": 2,
        "total_records": 500,
        "quarantined_pages": 0,
        "errors": [],
        "table_name": "dwh_dev.bronze.world_bank_indicators",
    }


def _make_copy_result(fetch_result: dict) -> dict:
    """Create a copy_result dict for verify_bronze_load testing."""
    return {
        **fetch_result,
        "copy_into_status": "success",
        "statements_executed": 2,
    }


@pytest.mark.parametrize(
    "host_input",
    [
        "https://dbc-test.cloud.databricks.com",
        "https://dbc-test.cloud.databricks.com/",
        "dbc-test.cloud.databricks.com",
    ],
)
@responses.activate
def test_copy_into_bronze_uses_correct_host(host_input):
    """Test that copy_into_bronze passes the correct normalized host to execute_sql_batch."""
    dag = _load_ingest_world_bank_dag()
    copy_into_bronze_fn = dag.task_dict["copy_into_bronze"].python_callable

    fetch_result = _make_fetch_result()

    with patch("airflow.sdk.Variable.get") as mock_var_get:
        mock_var_get.return_value = {
            "host": host_input,
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }

        # Mock SQL file read
        sql_content = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (country_id STRING);
COPY INTO ${catalog}.${schema}.world_bank_indicators FROM '${raw_path}' FILEFORMAT = JSON FORMAT_OPTIONS ('multiLine' = 'false');
"""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=sql_content)):
            # Mock API responses - two statements
            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": "stmt_1", "status": {"state": "SUCCEEDED"}},
                status=200,
            )
            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": "stmt_2", "status": {"state": "SUCCEEDED"}},
                status=200,
            )

            responses.get(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_1",
                json={"status": {"state": "SUCCEEDED"}, "statement_id": "stmt_1"},
                status=200,
            )
            responses.get(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_2",
                json={"status": {"state": "SUCCEEDED"}, "statement_id": "stmt_2"},
                status=200,
            )

            result = copy_into_bronze_fn(fetch_result)

            # Assertions
            assert result["copy_into_status"] == "success"
            assert result["statements_executed"] == 2

            # Verify exactly 2 POST calls were made
            post_calls = [c for c in responses.calls if c.request.method == "POST"]
            assert len(post_calls) == 2, f"Expected 2 POST calls, got {len(post_calls)}"

            # Every POST URL must be the normalized base URL
            for call in post_calls:
                assert call.request.url == "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements", \
                    f"POST URL mismatch: {call.request.url}"

            # Second POST body should contain COPY INTO with the correct table and batch_id
            second_post_body = json.loads(post_calls[1].request.body)
            assert "COPY INTO dwh_dev.bronze.world_bank_indicators" in second_post_body["statement"], \
                f"Second statement should contain COPY INTO: {second_post_body['statement']}"
            assert "wb_test_123" in second_post_body["statement"], \
                f"Statement should contain batch_id: {second_post_body['statement']}"


@responses.activate
def test_verify_bronze_load_parses_string_values():
    """Test that verify_bronze_load correctly parses string values from Databricks JSON_ARRAY."""
    dag = _load_ingest_world_bank_dag()
    verify_bronze_load_fn = dag.task_dict["verify_bronze_load"].python_callable

    fetch_result = _make_fetch_result()
    copy_result = _make_copy_result(fetch_result)

    with patch("airflow.sdk.Variable.get") as mock_var_get:
        mock_var_get.return_value = {
            "host": "https://dbc-test.cloud.databricks.com/",
            "token": "dapi_test_token",
            "warehouse_id": "warehouse_123",
        }

        # Mock verification query response with string values (Databricks JSON_ARRAY format)
        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
            json={
                "status": {"state": "SUCCEEDED"},
                "statement_id": "stmt_verify",
                "result": {
                    "data_array": [["500", "1", "2014", "2024", "489"]]
                },
            },
        )

        result = verify_bronze_load_fn(copy_result)

        # Verify the parsed verification result (values should be ints, not strings)
        assert result["verification"] == {
            "row_count": 500,
            "min_year": 2014,
            "max_year": 2024,
            "non_null_values": 489,
            "status": "passed",
        }


@pytest.fixture(autouse=True)
def reset_responses():
    """Reset responses between tests."""
    responses.reset()
    yield
    responses.reset()