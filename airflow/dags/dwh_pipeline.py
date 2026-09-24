"""
DWH Pipeline DAG.

Orchestrates the full data warehouse pipeline:
  extract_load_bronze -> dbt_run_staging -> dbt_test_staging -> dbt_run_marts -> dbt_test_marts -> notify_success

Key design notes:
- Staging models are TABLES (not views). Rebuilding them with `dbt run --select staging`
  drops and recreates the tables. Because marts models are VIEWS that depend on staging,
  this CASCADE-drops the marts views. They are recreated only when `dbt run --select marts`
  runs subsequently.
- If `dbt_test_staging` fails, the DAG stops. The marts layer remains unavailable
  until the next successful run. This is intentional quarantine at the orchestration level.
- dbt runs inside the Airflow container using the same dbt_project/requirements.txt
  as the host dev environment (mounted read-only). A writable volume is mounted at
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
    
    # Run DDL (scripts are mounted at /opt/airflow/scripts/bronze in Airflow container)
    cmd1 = [
        "psql", "-h", "postgres", "-U", pg_user, "-d", pg_db,
        "-f", "/opt/airflow/scripts/bronze/ddl_bronze.sql"
    ]
    result1 = subprocess.run(cmd1, env=env, capture_output=True, text=True)
    if result1.returncode != 0:
        raise RuntimeError(f"DDL failed: {result1.stderr}")
    
    # Run load
    cmd2 = [
        "psql", "-h", "postgres", "-U", pg_user, "-d", pg_db,
        "-v", "datasets_dir=/data/datasets", "-f", "/opt/airflow/scripts/bronze/load_bronze.sql"
    ]
    result2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
    if result2.returncode != 0:
        raise RuntimeError(f"Load failed: {result2.stderr}")
    
    print(result2.stdout)


from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

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
    description="Data Warehouse pipeline: Bronze -> Staging -> Marts",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["data-warehouse", "dbt", "bronze", "staging", "marts"],
) as dag:

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
    # Task 2: dbt run --select staging
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

    # ------------------------------------------------------------------
    # Task 3: dbt test --select staging
    # ------------------------------------------------------------------
    dbt_test_staging = BashOperator(
        task_id="dbt_test_staging",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt test --select staging --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    # ------------------------------------------------------------------
    # Task 4: dbt run --select marts
    # ------------------------------------------------------------------
    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=(
            "cd /opt/airflow/dbt_project && "
            "dbt run --select marts --profiles-dir ."
        ),
        retries=1,
        retry_delay=timedelta(minutes=5),
    )

    # ------------------------------------------------------------------
    # Task 5: dbt test --select marts
    # ------------------------------------------------------------------
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
    # Task 6: Notify success (only runs if all previous tasks succeeded)
    # ------------------------------------------------------------------
    notify_success = PythonOperator(
        task_id="notify_success",
        python_callable=on_success_callback,
        provide_context=True,
        trigger_rule="all_success",
    )

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------
    (
        extract_load_bronze
        >> dbt_run_staging
        >> dbt_test_staging
        >> dbt_run_marts
        >> dbt_test_marts
        >> notify_success
    )