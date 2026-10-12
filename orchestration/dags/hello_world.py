from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from airflow.configuration import conf
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import DAG, Variable, task

with DAG(
    dag_id="hello_world",
    description="Verify MWAA setup, Secrets Manager backend and DAG bucket access",
    schedule="@once",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
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
        """Read the world-bank variable via the Secrets Manager backend and
        write a small JSON under test/hello_world/ in the DAG bucket."""
        # Resolved as secret "cloud-data-platform/world-bank". No default:
        # the task must fail if the secret is missing or has no value.
        world_bank_config = Variable.get("world-bank", deserialize_json=True)

        # Never put the secret content in an error message (it ends up in logs).
        if not isinstance(world_bank_config, dict) or "base_url" not in world_bank_config:
            raise ValueError("world-bank secret must be a JSON object with a 'base_url' key")

        dag_bucket = conf.get("mwaa", "dag_bucket", fallback=None)
        if not dag_bucket:
            raise ValueError(
                "mwaa.dag_bucket is not set; check airflow_configuration_options in "
                "infra/terraform/aws/ephemeral/mwaa.tf"
            )

        now = datetime.now(timezone.utc)
        key = f"test/hello_world/run_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        key_names = sorted(world_bank_config.keys())  # key names only, never values
        payload = {
            "dag_id": "hello_world",
            "written_at": now.isoformat(),
            "world_bank_keys": key_names,
            "dag_bucket": dag_bucket,
            "status": "success",
        }

        S3Hook(aws_conn_id="aws_default").load_string(
            string_data=json.dumps(payload, indent=2),
            key=key,
            bucket_name=dag_bucket,
            replace=True,
        )

        print(f"Wrote s3://{dag_bucket}/{key} (world-bank keys: {key_names})")
        return {"bucket": dag_bucket, "key": key, "world_bank_keys": key_names}

    read_variable_and_write_s3()
