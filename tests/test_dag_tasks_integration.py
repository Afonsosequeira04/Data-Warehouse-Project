"""Integration tests for actual DAG task functions with mocked HTTP."""

from __future__ import annotations

# S102: exec is intentional for loading DAG from file
# ruff: noqa: S102
from unittest.mock import patch

import pytest
import responses


def _load_dag():
    """Load the DAG and return the dag object."""
    namespace = {"__file__": "orchestration/dags/ingest_world_bank.py"}
    with open("orchestration/dags/ingest_world_bank.py") as f:
        code = compile(f.read(), "orchestration/dags/ingest_world_bank.py", "exec")
        exec(code, namespace)
    return namespace["dag"]


class TestActualDagTasks:
    """Tests that execute the actual DAG task functions with mocked dependencies."""

    @responses.activate
    def test_verify_bronze_load_actual_task(self):
        """Test the actual verify_bronze_load task function with mocked HTTP."""
        dag = _load_dag()
        verify_bronze_load_fn = dag.task_dict["verify_bronze_load"].python_callable

        copy_result = {
            "batch_id": "wb_test",
            "ingest_date": "2025-01-15",
            "raw_bucket": "test-bucket",
            "raw_path": "s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/",
            "catalog": "dwh_dev",
            "schema": "bronze",
            "total_pages_written": 1,
            "total_records": 50,
            "quarantined_pages": 0,
            "errors": [],
            "table_name": "dwh_dev.bronze.world_bank_indicators",
            "copy_into_status": "success",
            "statements_executed": 2,
        }

        with patch("airflow.sdk.Variable.get") as mock_var_get:
            mock_var_get.return_value = {
                "host": "dbc-test.cloud.databricks.com",
                "token": "dapi_test_token",
                "warehouse_id": "warehouse_123",
            }

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
                        "data_array": [
                            [50, 1, 2020, 2023, 45]
                        ]
                    },
                },
            )

            result = verify_bronze_load_fn(copy_result)

            assert result["verification"]["status"] == "passed"
            assert result["verification"]["row_count"] == 50
            assert result["verification"]["min_year"] == 2020
            assert result["verification"]["max_year"] == 2023
            assert result["verification"]["non_null_values"] == 45

    @responses.activate
    def test_verify_bronze_load_actual_task_zero_rows(self):
        """Test verify_bronze_load fails when zero rows (but batch_count=1)."""
        dag = _load_dag()
        verify_bronze_load_fn = dag.task_dict["verify_bronze_load"].python_callable

        copy_result = {
            "batch_id": "wb_test",
            "ingest_date": "2025-01-15",
            "raw_bucket": "test-bucket",
            "raw_path": "s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/",
            "catalog": "dwh_dev",
            "schema": "bronze",
            "total_pages_written": 1,
            "total_records": 50,
            "quarantined_pages": 0,
            "errors": [],
            "table_name": "dwh_dev.bronze.world_bank_indicators",
            "copy_into_status": "success",
            "statements_executed": 2,
        }

        with patch("airflow.sdk.Variable.get") as mock_var_get:
            mock_var_get.return_value = {
                "host": "dbc-test.cloud.databricks.com",
                "token": "dapi_test_token",
                "warehouse_id": "warehouse_123",
            }

            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
            )
            responses.get(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
                json={
                    "status": {"state": "SUCCEEDED"},
                    "statement_id": "stmt_verify",
                    "result": {"data_array": [[0, 1, None, None, 0]]},
                },
            )

            with pytest.raises(ValueError, match="No rows loaded into Bronze table"):
                verify_bronze_load_fn(copy_result)

    @responses.activate
    def test_verify_bronze_load_actual_task_multiple_batches(self):
        """Test verify_bronze_load fails when multiple batch_ids."""
        dag = _load_dag()
        verify_bronze_load_fn = dag.task_dict["verify_bronze_load"].python_callable

        copy_result = {
            "batch_id": "wb_test",
            "ingest_date": "2025-01-15",
            "raw_bucket": "test-bucket",
            "raw_path": "s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/",
            "catalog": "dwh_dev",
            "schema": "bronze",
            "total_pages_written": 1,
            "total_records": 50,
            "quarantined_pages": 0,
            "errors": [],
            "table_name": "dwh_dev.bronze.world_bank_indicators",
            "copy_into_status": "success",
            "statements_executed": 2,
        }

        with patch("airflow.sdk.Variable.get") as mock_var_get:
            mock_var_get.return_value = {
                "host": "dbc-test.cloud.databricks.com",
                "token": "dapi_test_token",
                "warehouse_id": "warehouse_123",
            }

            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": "stmt_verify", "status": {"state": "SUCCEEDED"}},
            )
            responses.get(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_verify",
                json={
                    "status": {"state": "SUCCEEDED"},
                    "statement_id": "stmt_verify",
                    "result": {"data_array": [[50, 2, 2020, 2023, 45]]},
                },
            )

            with pytest.raises(ValueError, match="Expected 1 distinct _batch_id, found 2"):
                verify_bronze_load_fn(copy_result)


@pytest.fixture(autouse=True)
def reset_responses():
    """Reset responses between tests."""
    responses.reset()
    yield
    responses.reset()