"""World Bank Indicators ingestion DAG.

Tasks:
1. fetch_and_validate: Fetch from World Bank API, validate, write raw NDJSON to S3
2. copy_into_bronze: Run COPY INTO via Databricks SQL Statement Execution API
3. verify_bronze_load: Verify row count and _batch_id in Bronze table
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.configuration import conf
from airflow.sdk import DAG, Variable, task

# Import shared Databricks SQL utilities
from ingestion.databricks_sql import (
    execute_sql_batch,
    normalize_host,
    render_sql_template,
    split_sql_statements,
)

logger = logging.getLogger(__name__)

# Default DAG parameters (can be overridden at runtime)
DEFAULT_CATALOG = "dwh_dev"
DEFAULT_SCHEMA = "bronze"
SOURCE_NAME = "world_bank_indicators"
RAW_PREFIX = "api/world_bank_indicators"
QUARANTINE_PREFIX = "quarantine/api/world_bank_indicators"
# SQL file lives in ingestion/sql/ which is synced to dags/ingestion/sql/
SQL_FILE_PATH = "ingestion/sql/bronze_world_bank_indicators.sql"


with DAG(
    dag_id="ingest_world_bank",
    description="Ingest World Bank Indicators -> S3 raw -> Bronze Delta table",
    schedule=None,  # Triggered manually or by daily_pipeline
    start_date=datetime(2025, 1, 1, tzinfo=UTC),
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=2),
    },
    params={
        "catalog": DEFAULT_CATALOG,
        "schema": DEFAULT_SCHEMA,
        "indicators": None,  # None = use defaults from client config
        "date_range": None,  # None = use defaults
        "backfill": False,
    },
    tags=["ingestion", "world_bank", "bronze"],
) as dag:

    @task
    def fetch_and_validate(**context) -> dict:
        """Fetch World Bank data, validate responses, write raw NDJSON to S3.

        Returns dict with batch metadata for downstream tasks.
        """
        from ingestion.api.s3_writer import (
            S3Writer,
            S3WriterConfig,
            generate_batch_id,
            get_ingest_date,
        )
        from ingestion.api.world_bank_client import (
            WorldBankAPIError,
            WorldBankClient,
            WorldBankConfig,
        )

        # Resolve parameters
        params = context.get("params", {})
        catalog = params.get("catalog", DEFAULT_CATALOG)
        schema = params.get("schema", DEFAULT_SCHEMA)

        # Get raw bucket from Airflow config (set via Terraform mwaa.raw_bucket)
        raw_bucket = conf.get("mwaa", "raw_bucket", fallback=None)
        if not raw_bucket:
            raise ValueError(
                "mwaa.raw_bucket not set in airflow_configuration_options. "
                "Add it in infra/terraform/aws/ephemeral/mwaa.tf"
            )

        # Generate batch identifiers
        batch_id = generate_batch_id()
        ingest_date = get_ingest_date()

        # Initialize clients
        config = WorldBankConfig()
        if params.get("indicators"):
            config = WorldBankConfig(indicators=tuple(params["indicators"]))
        if params.get("date_range"):
            config = WorldBankConfig(date_range=params["date_range"])

        s3_config = S3WriterConfig(
            raw_bucket=raw_bucket,
            raw_prefix=RAW_PREFIX,
            quarantine_prefix=QUARANTINE_PREFIX,
        )
        s3_writer = S3Writer(s3_config)
        client = WorldBankClient(config)

        # Track results
        total_pages_written = 0
        total_records = 0
        quarantined_pages = 0
        errors = []

        try:
            for indicator in config.indicators:
                logger.info(f"Processing indicator: {indicator}")

                for page, raw_data in client.fetch_raw_pages(indicator):
                    try:
                        # Validate by attempting to parse
                        parsed_count = 0
                        for item in raw_data:
                            obs = client._parse_observation(item, indicator)
                            if obs is not None:
                                parsed_count += 1

                        if parsed_count == 0 and raw_data:
                            # Data exists but nothing parsed - quarantine
                            s3_writer.write_quarantine(
                                ingest_date=ingest_date,
                                batch_id=batch_id,
                                indicator=indicator,
                                page=page,
                                error_type="parse_error",
                                error_message="All records in page failed to parse",
                                raw_data=raw_data,
                            )
                            quarantined_pages += 1
                            continue

                        # Write valid raw page to S3
                        result = s3_writer.write_raw_page(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            data=raw_data,
                            metadata={"parsed_count": parsed_count},
                        )
                        total_pages_written += 1
                        total_records += parsed_count
                        logger.info(f"Wrote raw page: {result.key} ({parsed_count} records)")

                    except WorldBankAPIError as e:
                        # API-level errors (invalid schema, error payload) - quarantine
                        s3_writer.write_quarantine(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            error_type="api_error",
                            error_message=str(e),
                            raw_data=raw_data if "raw_data" in locals() else None,
                        )
                        quarantined_pages += 1
                        errors.append(f"{indicator} page {page}: {e}")
                        logger.error(f"Quarantined {indicator} page {page}: {e}")

                    except Exception as e:
                        # Unexpected errors - quarantine and re-raise
                        s3_writer.write_quarantine(
                            ingest_date=ingest_date,
                            batch_id=batch_id,
                            indicator=indicator,
                            page=page,
                            error_type="unexpected_error",
                            error_message=str(e),
                            raw_data=raw_data if "raw_data" in locals() else None,
                        )
                        quarantined_pages += 1
                        raise

        finally:
            client.close()

        if total_pages_written == 0:
            raise ValueError("No raw pages were successfully written to S3")

        # Build raw path for COPY INTO
        raw_path = f"s3://{raw_bucket}/{RAW_PREFIX}/ingest_date={ingest_date}/{batch_id}/"

        result = {
            "batch_id": batch_id,
            "ingest_date": ingest_date,
            "raw_bucket": raw_bucket,
            "raw_path": raw_path,
            "catalog": catalog,
            "schema": schema,
            "total_pages_written": total_pages_written,
            "total_records": total_records,
            "quarantined_pages": quarantined_pages,
            "errors": errors,
            "table_name": f"{catalog}.{schema}.{SOURCE_NAME}",
        }

        logger.info(f"Fetch complete: {json.dumps(result, indent=2)}")
        return result

    @task
    def copy_into_bronze(fetch_result: dict) -> dict:
        """Run COPY INTO via Databricks SQL Statement Execution API to load Bronze table."""
        # Get Databricks connection from secret
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        if not isinstance(databricks_secret, dict):
            raise TypeError("databricks secret must be a JSON object")

        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        if not all([host, token, warehouse_id]):
            raise ValueError("databricks secret must contain host, token, and warehouse_id")

        # Read SQL template (ingestion/sql/ is synced to dags/ingestion/sql/)
        sql_path = Path(__file__).parent / SQL_FILE_PATH
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL file not found: {sql_path}")

        with open(sql_path) as f:
            sql_template = f.read()

        # Render SQL with batch parameters using shared utility
        sql = render_sql_template(
            sql_template=sql_template,
            catalog=fetch_result["catalog"],
            schema=fetch_result["schema"],
            raw_path=fetch_result["raw_path"],
            batch_id=fetch_result["batch_id"],
            batch_date=fetch_result["ingest_date"],
        )

        # Split into individual statements (CREATE TABLE, then COPY INTO)
        statements = split_sql_statements(sql)

        logger.info(f"Executing {len(statements)} statements for batch {fetch_result['batch_id']}")

        # Execute each statement via Databricks Statement Execution API
        results = execute_sql_batch(
            host=normalize_host(fetch_result.get("databricks_host", "")) or normalize_host(host),
            token=token,
            warehouse_id=warehouse_id,
            statements=statements,
            wait_timeout="50s",
        )

        for i, result in enumerate(results, 1):
            logger.info(f"Statement {i} completed: {result.get('statement_id')}")

        logger.info("All statements completed successfully")

        return {
            **fetch_result,
            "copy_into_status": "success",
            "statements_executed": len(statements),
        }

    @task
    def verify_bronze_load(copy_result: dict) -> dict:
        """Verify Bronze table load: row count and _batch_id match."""
        databricks_secret = Variable.get("databricks", deserialize_json=True)
        if not isinstance(databricks_secret, dict):
            raise TypeError("databricks secret must be a JSON object")

        host = databricks_secret.get("host")
        token = databricks_secret.get("token")
        warehouse_id = databricks_secret.get("warehouse_id")

        if not all([host, token, warehouse_id]):
            raise ValueError("databricks secret must contain host, token, and warehouse_id")

        table_name = copy_result["table_name"]
        batch_id = copy_result["batch_id"]
        expected_records = copy_result["total_records"]

        # Verification query
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

        logger.info(f"Verifying Bronze load for batch {batch_id}")

        # Use INLINE disposition for small verification results
        from ingestion.databricks_sql import (
            execute_statement,
            normalize_host,
            parse_verification_row,
        )

        result = execute_statement(
            host=normalize_host(host),
            token=token,
            warehouse_id=warehouse_id,
            statement=verify_sql,
            wait_timeout="50s",
            disposition="INLINE",
            format="JSON_ARRAY",
        )

        # Parse result from result.data_array
        rows = result.get("result", {}).get("data_array", [])
        if not rows:
            raise RuntimeError("Verification query returned no rows")

        row = rows[0]

        # Databricks JSON_ARRAY returns all values as strings - cast to int
        actual_count, batch_count, min_year, max_year, non_null_values = parse_verification_row(row)

        # Validate
        if batch_count != 1:
            raise ValueError(f"Expected 1 distinct _batch_id, found {batch_count}")

        if actual_count == 0:
            raise ValueError("No rows loaded into Bronze table")

        # Allow some tolerance for null values being filtered
        if actual_count < expected_records * 0.5:
            raise ValueError(
                f"Row count mismatch: expected ~{expected_records}, got {actual_count}"
            )

        logger.info(
            f"Verification passed: {actual_count} rows, batch_id={batch_id}, "
            f"year range={min_year}-{max_year}, non-null values={non_null_values}"
        )

        return {
            **copy_result,
            "verification": {
                "row_count": actual_count,
                "min_year": min_year,
                "max_year": max_year,
                "non_null_values": non_null_values,
                "status": "passed",
            },
        }

    # Task dependencies
    fetch_result = fetch_and_validate()
    copy_result = copy_into_bronze(fetch_result)
    verify_bronze_load(copy_result)