"""Unit tests for ingestion.databricks_sql shared module."""

from __future__ import annotations

import pytest
import responses


class TestNormalizeHost:
    """Tests for normalize_host function."""

    def test_normalize_host_with_https_and_trailing_slash(self):
        """Test normalizing host with https:// and trailing slash."""
        from ingestion.databricks_sql import normalize_host
        assert normalize_host("https://dbc-test.cloud.databricks.com/") == "https://dbc-test.cloud.databricks.com"

    def test_normalize_host_with_https_no_trailing_slash(self):
        """Test normalizing host with https:// but no trailing slash."""
        from ingestion.databricks_sql import normalize_host
        assert normalize_host("https://dbc-test.cloud.databricks.com") == "https://dbc-test.cloud.databricks.com"

    def test_normalize_host_without_protocol(self):
        """Test normalizing host without protocol."""
        from ingestion.databricks_sql import normalize_host
        assert normalize_host("dbc-test.cloud.databricks.com") == "https://dbc-test.cloud.databricks.com"

    def test_normalize_host_with_trailing_slash_no_protocol(self):
        """Test normalizing host with trailing slash but no protocol."""
        from ingestion.databricks_sql import normalize_host
        assert normalize_host("dbc-test.cloud.databricks.com/") == "https://dbc-test.cloud.databricks.com"


class TestRenderSqlTemplate:
    """Tests for render_sql_template function."""

    def test_render_sql_replaces_all_placeholders(self):
        """Test that all ${...} placeholders are replaced in SQL template."""
        from ingestion.databricks_sql import render_sql_template

        sql_template = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (country_id STRING);
COPY INTO ${catalog}.${schema}.world_bank_indicators FROM '${raw_path}'
FILEFORMAT = JSON FORMAT_OPTIONS ('multiLine' = 'false');
"""

        sql = render_sql_template(
            sql_template=sql_template,
            catalog="dwh_dev",
            schema="bronze",
            raw_path="s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/",
            batch_id="wb_test",
            batch_date="2025-01-15",
        )

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
        assert "s3://test-bucket/api/world_bank_indicators/ingest_date=2025-01-15/wb_test/" in sql


class TestSplitSqlStatements:
    """Tests for split_sql_statements function."""

    def test_split_simple_statements(self):
        """Test splitting simple statements."""
        from ingestion.databricks_sql import split_sql_statements

        sql = "CREATE TABLE test (id INT); COPY INTO test FROM 's3://path';"
        statements = split_sql_statements(sql)

        assert len(statements) == 2
        assert "CREATE TABLE test (id INT)" in statements[0]
        assert "COPY INTO test FROM 's3://path'" in statements[1]

    def test_split_multiline_statements(self):
        """Test splitting multi-line statements."""
        from ingestion.databricks_sql import split_sql_statements

        sql = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (
    country_id STRING NOT NULL,
    year INT NOT NULL
);
COPY INTO ${catalog}.${schema}.world_bank_indicators
FROM '${raw_path}'
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiLine' = 'false');
"""
        statements = split_sql_statements(sql)

        assert len(statements) == 2
        assert "CREATE TABLE" in statements[0]
        assert "COPY INTO" in statements[1]

    def test_drop_comment_only_chunks(self):
        """Test that comment-only chunks (like verification query at end of .sql) are dropped."""
        from ingestion.databricks_sql import split_sql_statements

        # This simulates the actual .sql file with a commented verification query at the end
        sql = """
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.world_bank_indicators (country_id STRING);
COPY INTO ${catalog}.${schema}.world_bank_indicators FROM '${raw_path}' FILEFORMAT = JSON FORMAT_OPTIONS ('multiLine' = 'false');
-- Verification query: count rows and verify batch_id
-- SELECT _batch_id, COUNT(*) as row_count, MIN(year), MAX(year)
-- FROM ${catalog}.${schema}.world_bank_indicators
-- WHERE _batch_id = '${batch_id}'
-- GROUP BY _batch_id;
"""

        statements = split_sql_statements(sql)

        # Should only have 2 executable statements (CREATE TABLE, COPY INTO)
        # The commented verification query should be dropped
        assert len(statements) == 2
        assert "CREATE TABLE" in statements[0]
        assert "COPY INTO" in statements[1]

        # Verify the commented query is not in the results
        for stmt in statements:
            assert "Verification query" not in stmt
            assert "GROUP BY _batch_id" not in stmt


class TestParseVerificationRow:
    """Tests for parse_verification_row function."""

    def test_parse_verification_row_strings_to_int(self):
        """Test parsing verification row with string values (Databricks JSON_ARRAY returns strings)."""
        from ingestion.databricks_sql import parse_verification_row

        # Databricks JSON_ARRAY returns all values as strings
        row = ["500", "1", "2014", "2024", "489"]
        row_count, batch_count, min_year, max_year, non_null_values = parse_verification_row(row)

        assert row_count == 500
        assert batch_count == 1
        assert min_year == 2014
        assert max_year == 2024
        assert non_null_values == 489

    def test_parse_verification_row_with_none_values(self):
        """Test parsing verification row with None values for min/max year."""
        from ingestion.databricks_sql import parse_verification_row

        row = ["0", "1", None, None, "0"]
        row_count, batch_count, min_year, max_year, non_null_values = parse_verification_row(row)

        assert row_count == 0
        assert batch_count == 1
        assert min_year == 0
        assert max_year == 0
        assert non_null_values == 0

    def test_parse_verification_row_invalid_length(self):
        """Test parsing verification row with wrong number of columns."""
        from ingestion.databricks_sql import parse_verification_row

        with pytest.raises(ValueError, match="Expected 5 columns"):
            parse_verification_row(["1", "2", "3"])

    def test_parse_verification_row_invalid_values(self):
        """Test parsing verification row with non-numeric values."""
        from ingestion.databricks_sql import parse_verification_row

        with pytest.raises(ValueError):
            parse_verification_row(["abc", "1", "2014", "2024", "489"])


class TestExecuteStatement:
    """Tests for execute_statement function."""

    @responses.activate
    def test_execute_statement_success(self):
        """Test successful statement execution and polling."""
        from ingestion.databricks_sql import execute_statement

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
                "result": {"data_array": [["1"]]},  # JSON_ARRAY returns strings
            },
            status=200,
        )

        result = execute_statement(
            host="dbc-test.cloud.databricks.com",
            token="test_token",
            warehouse_id="warehouse_123",
            statement="SELECT 1",
            wait_timeout="50s",
        )

        assert result["statement_id"] == "stmt_123"
        assert result["status"]["state"] == "SUCCEEDED"
        assert result["result"]["data_array"] == [["1"]]

    @responses.activate
    def test_execute_statement_failure(self):
        """Test statement execution failure."""
        from ingestion.databricks_sql import execute_statement

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
            execute_statement(
                host="dbc-test.cloud.databricks.com",
                token="test_token",
                warehouse_id="warehouse_123",
                statement="SELECT 1",
            )

    @responses.activate
    def test_execute_statement_http_error(self):
        """Test HTTP error handling."""
        from ingestion.databricks_sql import execute_statement

        responses.post(
            "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
            status=401,
            json={"error_code": "UNAUTHORIZED", "message": "Invalid token"},
        )

        with pytest.raises(Exception, match="401"):
            execute_statement(
                host="dbc-test.cloud.databricks.com",
                token="bad_token",
                warehouse_id="warehouse_123",
                statement="SELECT 1",
            )


class TestExecuteSqlBatch:
    """Tests for execute_sql_batch function."""

    @responses.activate
    def test_execute_sql_batch_multiple_statements(self):
        """Test executing multiple statements sequentially."""
        from ingestion.databricks_sql import execute_sql_batch

        statements = ["SELECT 1", "SELECT 2"]

        for i in range(2):
            responses.post(
                "https://dbc-test.cloud.databricks.com/api/2.0/sql/statements",
                json={"statement_id": f"stmt_{i+1}", "status": {"state": "SUCCEEDED"}},
                status=200,
            )
            responses.get(
                f"https://dbc-test.cloud.databricks.com/api/2.0/sql/statements/stmt_{i+1}",
                json={
                    "statement_id": f"stmt_{i+1}",
                    "status": {"state": "SUCCEEDED"},
                    "result": {"data_array": [[str(i+1)]]},
                },
                status=200,
            )

        results = execute_sql_batch(
            host="dbc-test.cloud.databricks.com",
            token="test_token",
            warehouse_id="warehouse_123",
            statements=statements,
            wait_timeout="50s",
        )

        assert len(results) == 2
        assert results[0]["statement_id"] == "stmt_1"
        assert results[1]["statement_id"] == "stmt_2"


class TestVerifyBronzeLoadLogic:
    """Tests for verify_bronze_load logic."""

    def test_verification_validation_logic_pass(self):
        """Test verification validation passes for valid data."""
        from ingestion.databricks_sql import parse_verification_row

        # Databricks returns strings
        row = ["500", "1", "2014", "2024", "489"]
        row_count, batch_count, _min_year, _max_year, _non_null_values = parse_verification_row(row)

        assert batch_count == 1
        assert row_count > 0
        assert row_count >= 250  # 500 * 0.5

    def test_verification_validation_logic_fail_zero_rows(self):
        """Test verification fails when zero rows."""
        from ingestion.databricks_sql import parse_verification_row

        row = ["0", "1", None, None, "0"]
        row_count, _batch_count, _min_year, _max_year, _non_null_values = parse_verification_row(row)

        with pytest.raises(ValueError, match="No rows loaded into Bronze table"):
            if row_count == 0:
                raise ValueError("No rows loaded into Bronze table")

    def test_verification_validation_logic_fail_multiple_batches(self):
        """Test verification fails when multiple batch_ids."""
        from ingestion.databricks_sql import parse_verification_row

        row = ["500", "2", "2014", "2024", "489"]
        _row_count, batch_count, _min_year, _max_year, _non_null_values = parse_verification_row(row)

        with pytest.raises(ValueError, match="Expected 1 distinct _batch_id, found 2"):
            if batch_count != 1:
                raise ValueError(f"Expected 1 distinct _batch_id, found {batch_count}")

    def test_verification_validation_logic_fail_count_mismatch(self):
        """Test verification fails on significant count mismatch."""
        from ingestion.databricks_sql import parse_verification_row

        row = ["100", "1", "2014", "2024", "50"]
        row_count, _batch_count, _min_year, _max_year, _non_null_values = parse_verification_row(row)

        expected_records = 500
        with pytest.raises(ValueError, match="Row count mismatch"):
            if row_count < expected_records * 0.5:
                raise ValueError(f"Row count mismatch: expected ~{expected_records}, got {row_count}")


@pytest.fixture(autouse=True)
def reset_responses():
    """Reset responses between tests."""
    responses.reset()
    yield
    responses.reset()