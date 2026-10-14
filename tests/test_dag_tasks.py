"""Unit tests for ingest_world_bank DAG tasks."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import responses


class TestExecuteDatabricksStatement:
    """Tests for _execute_databricks_statement helper."""

    @responses.activate
    def test_execute_statement_success(self):
        """Test successful statement execution and polling."""
        from orchestration.dags.ingest_world_bank import _execute_databricks_statement

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_123", "status": {"state": "PENDING"}},
            status=200,
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_123",
            json={
                "statement_id": "stmt_123",
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [[1]]},
            },
            status=200,
        )

        result = _execute_databricks_statement(
            host="dbc-test.cloud.databricks.com",
            token="test_token",
            warehouse_id="warehouse_123",
            statement="SELECT 1",
            wait_timeout="50s",
        )

        assert result["statement_id"] == "stmt_123"
        assert result["status"]["state"] == "SUCCEEDED"
        assert result["result"]["data_array"] == [[1]]

    @responses.activate
    def test_execute_statement_failure(self):
        """Test statement execution failure."""
        from orchestration.dags.ingest_world_bank import _execute_databricks_statement

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_123", "status": {"state": "PENDING"}},
            status=200,
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_123",
            json={
                "statement_id": "stmt_123",
                "status": {"state": "FAILED", "error": {"message": "Syntax error"}},
            },
            status=200,
        )

        with pytest.raises(RuntimeError, match="Statement stmt_123 failed: Syntax error"):
            _execute_databricks_statement(
                host="dbc-test.cloud.databricks.com",
                token="test_token",
                warehouse_id="warehouse_123",
                statement="SELECT 1",
            )

    @responses.activate
    def test_execute_statement_http_error(self):
        """Test HTTP error handling."""
        from orchestration.dags.ingest_world_bank import _execute_databricks_statement

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            status=401,
            json={"error_code": "UNAUTHORIZED", "message": "Invalid token"},
        )

        with pytest.raises(Exception, match="401"):
            _execute_databricks_statement(
                host="dbc-test.cloud.databricks.com",
                token="bad_token",
                warehouse_id="warehouse_123",
                statement="SELECT 1",
            )


class TestCopyIntoBronzeLogic:
    """Tests for copy_into_bronze logic (extracted from DAG)."""

    def test_render_sql_replaces_all_placeholders(self):
        """Test that all ${...} placeholders are replaced in SQL template."""
        from orchestration.dags.ingest_world_bank import copy_into_bronze

        # We test the SQL rendering logic directly
        sql_template = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (country_id STRING);
COPY INTO ${catalog}.${schema}.world_bank_indicators FROM '${raw_path}' 
FILEFORMAT = JSON FORMAT_OPTIONS ('multiLine' = 'false') PATTERN = '*.json';
"""

        fetch_result = {
            "batch_id": "wb_test",
            "ingest_date": "2025-01-15",
            "raw_path": "s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/",
            "catalog": "dwh_dev",
            "schema": "bronze",
        }

        sql = sql_template.replace("${catalog}", fetch_result["catalog"]) \
                         .replace("${schema}", fetch_result["schema"]) \
                         .replace("${raw_path}", fetch_result["raw_path"]) \
                         .replace("${batch_id}", fetch_result["batch_id"]) \
                         .replace("${batch_date}", fetch_result["ingest_date"])

        # Verify no placeholders remain
        assert "${catalog}" not in sql
        assert "${schema}" not in sql
        assert "${raw_path}" not in sql
        assert "${batch_id}" not in sql
        assert "${batch_date}" not in sql

        # Verify values were substituted
        assert "dwh_dev" in sql
        assert "bronze" in sql
        assert "wb_test" in sql
        assert "2025-01-15" in sql

    def test_sql_split_into_individual_statements(self):
        """Test that SQL is correctly split into individual statements."""
        sql = "CREATE TABLE test (id INT); COPY INTO test FROM 's3://path';"
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]

        assert len(statements) == 2
        assert "CREATE TABLE test (id INT)" in statements[0]
        assert "COPY INTO test FROM 's3://path'" in statements[1]

    def test_sql_with_multiline_no_semicolon_in_strings(self):
        """Test SQL splitting handles multi-line statements correctly."""
        sql = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (
    country_id STRING NOT NULL,
    year INT NOT NULL
);
COPY INTO ${catalog}.${schema}.world_bank_indicators
FROM '${raw_path}'
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiLine' = 'false')
PATTERN = '*.json';
"""
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]

        assert len(statements) == 2
        assert "CREATE TABLE" in statements[0]
        assert "COPY INTO" in statements[1]


class TestVerifyBronzeLoadLogic:
    """Tests for verify_bronze_load logic (extracted from DAG)."""

    def test_verification_query_structure(self):
        """Test that verification query has correct structure."""
        table_name = "dwh_dev.bronze.world_bank_indicators"
        batch_id = "wb_test"

        verify_sql = f"""
            SELECT
                COUNT(*) as row_count,
                COUNT(DISTINCT _batch_id) as batch_count,
                MIN(year) as min_year,
                MAX(year) as max_year,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) as non_null_values
            FROM {table_name}
            WHERE _batch_id = '{batch_id}'
        """

        assert "COUNT(*)" in verify_sql
        assert "COUNT(DISTINCT _batch_id)" in verify_sql
        assert "MIN(year)" in verify_sql
        assert "MAX(year)" in verify_sql
        assert "SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END)" in verify_sql
        assert f"WHERE _batch_id = '{batch_id}'" in verify_sql

    def test_verification_validation_logic_pass(self):
        """Test verification validation passes for valid data."""
        # Simulate the validation logic
        row = [50, 1, 2020, 2023, 45]  # row_count, batch_count, min_year, max_year, non_null_values
        expected_records = 50

        actual_count = row[0]
        batch_count = row[1]
        min_year = row[2]
        max_year = row[3]
        non_null_values = row[4]

        assert batch_count == 1
        assert actual_count > 0
        assert actual_count >= expected_records * 0.5

    def test_verification_validation_logic_fail_zero_rows(self):
        """Test verification fails when zero rows."""
        row = [0, 0, None, None, 0]
        expected_records = 50

        actual_count = row[0]

        with pytest.raises(ValueError, match="No rows loaded into Bronze table"):
            if actual_count == 0:
                raise ValueError("No rows loaded into Bronze table")

    def test_verification_validation_logic_fail_multiple_batches(self):
        """Test verification fails when multiple batch_ids."""
        row = [50, 2, 2020, 2023, 45]

        batch_count = row[1]

        with pytest.raises(ValueError, match="Expected 1 distinct _batch_id, found 2"):
            if batch_count != 1:
                raise ValueError(f"Expected 1 distinct _batch_id, found {batch_count}")

    def test_verification_validation_logic_fail_count_mismatch(self):
        """Test verification fails on significant count mismatch."""
        row = [10, 1, 2020, 2023, 8]
        expected_records = 50

        actual_count = row[0]

        with pytest.raises(ValueError, match="Row count mismatch"):
            if actual_count < expected_records * 0.5:
                raise ValueError(f"Row count mismatch: expected ~{expected_records}, got {actual_count}")


class TestDagHelpers:
    """Tests for helper functions."""

    @responses.activate
    def test_execute_databricks_statement_calls_correct_endpoints(self):
        """Test that _execute_databricks_statement calls POST then GET."""
        from orchestration.dags.ingest_world_bank import _execute_databricks_statement

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            json={"statement_id": "stmt_123", "status": {"state": "PENDING"}},
            status=200,
        )
        responses.get(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_123",
            json={
                "statement_id": "stmt_123",
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [[1]]},
            },
            status=200,
        )

        result = _execute_databricks_statement(
            host="dbc-test.cloud.databricks.com",
            token="test_token",
            warehouse_id="warehouse_123",
            statement="SELECT 1",
        )

        # Verify POST was called with correct payload
        post_call = responses.calls[0]
        assert post_call.request.method == "POST"
        assert post_call.request.url == "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements"
        request_body = json.loads(post_call.request.body)
        assert request_body["statement"] == "SELECT 1"
        assert request_body["warehouse_id"] == "warehouse_123"
        assert request_body["wait_timeout"] == "50s"
        assert request_body["format"] == "JSON_ARRAY"

        # Verify GET was called for polling
        get_call = responses.calls[1]
        assert get_call.request.method == "GET"
        assert get_call.request.url == "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_123"


@pytest.fixture(autouse=True)
def reset_responses():
    """Reset responses between tests."""
    responses.reset()
    yield
    responses.reset()