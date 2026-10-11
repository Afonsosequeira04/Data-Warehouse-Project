from __future__ import annotations

import json
from datetime import datetime, timedelta

from airflow.sdk import DAG, task, Variable
from airflow.configuration import conf
from airflow.providers.amazon.aws.hooks.s3 import S3Hook


with DAG(
    dag_id="hello_world",
    description="Simple DAG to verify MWAA setup, Secrets Manager backend, and DAG bucket access",
    schedule="@once",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["test", "mwaa-validation"],
) as dag:

    @task
    def read_variable_and_write_s3() -> dict:
        """Read the world-bank variable from Secrets Manager backend and write test JSON to DAG bucket."""
        # This proves the Secrets Manager backend works (variable name: cloud-data-platform/world-bank)
        # Task MUST fail if the variable is missing - no default_var allowed.
        world_bank_config = Variable.get("world-bank", deserialize_json=True)

        # Verify the expected key exists (World Bank API base_url)
        if not isinstance(world_bank_config, dict) or "base_url" not in world_bank_config:
            raise ValueError(
                f"world-bank secret must be a JSON object with 'base_url' key, got: {world_bank_config}"
            )

        # Get the DAG bucket name from Airflow configuration (set via Terraform-managed MWAA config)
        dag_bucket = conf.get("mwaa", "dag_bucket", fallback=None)
        if not dag_bucket:
            raise ValueError(
                "DAG bucket name not found. Ensure MWAA airflow_configuration_options.mwaa.dag_bucket is set."
            )

        # Write a small test JSON under test/hello_world/ (never the raw bucket)
        test_key = f"test/hello_world/run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        test_data = {
            "dag_id": "hello_world",
            "execution_date": datetime.utcnow().isoformat(),
            "world_bank_variable_found": True,
            "world_bank_keys": list(world_bank_config.keys()),
            "dag_bucket_used": dag_bucket,
            "status": "success",
        }

        s3_hook = S3Hook(aws_conn_id="aws_default")
        s3_hook.load_string(
            string_data=json.dumps(test_data, indent=2),
            key=test_key,
            bucket_name=dag_bucket,
            replace=True,
        )

        return {
            "bucket": dag_bucket,
            "key": test_key,
            "world_bank_variable_found": True,
            "world_bank_keys": list(world_bank_config.keys()),
        }

    read_variable_and_write_s3()