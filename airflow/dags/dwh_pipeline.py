"""
DWH Pipeline DAG.

Orchestrates the full data warehouse pipeline:
  validate_headers -> extract_load_bronze
                      -> dbt_run_staging -> dbt_test_staging
                      -> dbt_run_quarantine -> dbt_test_quarantine
    Both branches converge on notify_success.

Key design notes:
- Staging models are TABLES (not views). Rebuilding them with `dbt run --select staging`
  drops and recreates the tables. Because marts models are VIEWS that depend on staging,
  this CASCADE-drops the marts views. They are recreated only when `dbt run --select marts`
  runs subsequently. If `dbt_test_staging` fails, the DAG stops and marts views
  remain dropped until the next successful run.
- Quarantine models are TABLES. They run in a separate branch and their failures
  do not affect the staging/marts chain. Quarantine failures are logged but do
  not drop the marts views.
- dbt runs inside the Airflow container using the same dbt_project/requirements.txt
  as the host dev environment. The dbt project is baked into the Airflow image
  with `dbt deps` pre-installed. A writable volume is mounted at
  /opt/airflow/dbt_project/target for dbt artifacts.
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from notifications import on_failure_callback, on_success_callback


def extract_load_bronze_callable():
    """Extract and load bronze layer using psql."""
    import subprocess
    
    pg_user = os.environ.get("POSTGRES_USER", "data_warehouse")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "data_warehouse")
    pg_db = os.environ.get("POSTGRES_DB", "data_warehouse_project")
    
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password
    
    # Helper to run psql commands against the warehouse
    def psql_cmd(sql, *, capture=True):
        cmd = ["psql", "-h", "postgres", "-U", pg_user, "-d", pg_db, "-At", "-c", sql]
        return subprocess.run(cmd, env=env, capture_output=capture, text=True)
    
    # 1) Take a watermark from the DATABASE clock (not Airflow clock)
    # bronze.load_errors.occurred_at defaults to now() = clock_timestamp()
    # It is timestamp without time zone (see table schema).
    # Use -At (aligned, tuples only) and cast to timestamp to get just the value.
    watermark = psql_cmd("SELECT clock_timestamp()::timestamp", capture=True)
    if watermark.returncode != 0:
        raise RuntimeError(f"Failed to get DB clock: {watermark.stderr}")
    watermark_ts = watermark.stdout.strip()
    
    # 2) Run DDL with ON_ERROR_STOP=1 (scripts mounted at /opt/airflow/scripts/bronze)
    cmd1 = [
        "psql", "-h", "postgres", "-U", pg_user, "-d", pg_db,
        "-v", "ON_ERROR_STOP=1",
        "-f", "/opt/airflow/scripts/bronze/ddl_bronze.sql"
    ]
    result1 = subprocess.run(cmd1, env=env, capture_output=True, text=True)
    if result1.returncode != 0:
        raise RuntimeError(f"DDL failed: {result1.stderr}")
    
    # 3) Run load with ON_ERROR_STOP=1
    cmd2 = [
        "psql", "-h", "postgres", "-U", pg_user, "-d", pg_db,
        "-v", "ON_ERROR_STOP=1",
        "-v", "datasets_dir=/data/datasets",
        "-f", "/opt/airflow/scripts/bronze/load_bronze.sql"
    ]
    result2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
    if result2.returncode != 0:
        raise RuntimeError(f"Load failed: {result2.stderr}")
    
    print(result2.stdout)
    
    # 4) After load, check bronze.load_errors for errors with occurred_at >= watermark
    # occurred_at is timestamp without time zone (no TZ), watermark from clock_timestamp() is also without TZ
    # Use -At (aligned, tuples only) to get clean count
    check_sql = (
        "SELECT count(*) FROM bronze.load_errors "
        f"WHERE occurred_at >= '{watermark_ts}'"
    )
    check = psql_cmd(check_sql)
    if check.returncode != 0:
        raise RuntimeError(f"Failed to query load_errors: {check.stderr}")
    
    count_str = check.stdout.strip()
    try:
        error_count = int(count_str)
    except ValueError:
        raise RuntimeError(f"Failed to parse error count: {check.stdout}")
    
    if error_count > 0:
        # List the actual error rows for this run
        detail_sql = (
            "SELECT table_name, error_type, error_message, attempt_number, occurred_at "
            "FROM bronze.load_errors "
            f"WHERE occurred_at >= '{watermark_ts}'"
        )
        detail = psql_cmd(detail_sql)
        if detail.returncode != 0:
            raise RuntimeError(f"Failed to query error details: {detail.stderr}")
        raise RuntimeError(f"Bronze load produced {error_count} error(s) in this run:\n{detail.stdout}")
    
    # Note: proper run_id column is planned for Fase 6 to replace watermark approach


from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from notifications import on_failure_callback, on_success_callback


# ----------------------------------------------------------------------
# Default arguments
# ----------------------------------------------------------------------
default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure_callback,
}

# ----------------------------------------------------------------------
# DAG definition
# ----------------------------------------------------------------------
with DAG(
    dag_id="dwh_pipeline",
    description="Data Warehouse pipeline: Bronze -> Staging -> Marts (+ Quarantine)",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["data-warehouse", "dbt", "bronze", "staging", "marts", "quarantine"],
) as dag:

    # ------------------------------------------------------------------
    # Task 0: Validate CSV headers (runs before bronze load)
    # ------------------------------------------------------------------
    validate_headers = BashOperator(
        task_id="validate_headers",
        bash_command=(
            "bash /opt/airflow/scripts/bronze/validate_headers.sh /data/datasets"
        ),
        retries=1,
        retry_delay=timedelta(minutes=2),
    )

    # ------------------------------------------------------------------
    # Task 1: Extract & Load Bronze (psql COPY from CSV)
    # ------------------------------------------------------------------
    extract_load_bronze = PythonOperator(
        task_id="extract_load_bronze",
        python_callable=extract_load_bronze_callable,
        retries=1,
        retry_delay=timedelta(minutes=2),
    )

    # ------------------------------------------------------------------
    # Branch A: Staging -> Marts (main chain)
    # ------------------------------------------------------------------
    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt run --select staging --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    dbt_test_staging = BashOperator(
        task_id="dbt_test_staging",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt test --select staging --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt run --select marts --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    dbt_test_marts = BashOperator(
        task_id="dbt_test_marts",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt test --select marts --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    # ------------------------------------------------------------------
    # Branch B: Quarantine (runs in parallel, failures don't drop marts)
    # ------------------------------------------------------------------
    dbt_run_quarantine = BashOperator(
        task_id="dbt_run_quarantine",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt run --select quarantine --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    dbt_test_quarantine = BashOperator(
        task_id="dbt_test_quarantine",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt test --select quarantine --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    # ------------------------------------------------------------------
    # Task Final: Notify success (runs only if both branches succeed)
    # ------------------------------------------------------------------
    notify_success = PythonOperator(
        task_id="notify_success",
        python_callable=on_success_callback,
        trigger_rule="all_success",
    )

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------
    (
        validate_headers
        >> extract_load_bronze
        >> [dbt_run_staging, dbt_run_quarantine]
    )
    (
        dbt_run_staging
        >> dbt_test_staging
        >> dbt_run_marts
        >> dbt_test_marts
    )
    (
        dbt_run_quarantine
        >> dbt_test_quarantine
    )
    # notify_success depends on both branches
    (
        dbt_test_marts
        >> notify_success
    )
    (
        dbt_test_quarantine
        >> notify_success
    )