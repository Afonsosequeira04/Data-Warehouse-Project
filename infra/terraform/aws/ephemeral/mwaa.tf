resource "aws_mwaa_environment" "main" {
  name                  = "${var.project_name}-${var.environment}"
  airflow_version       = var.airflow_version
  environment_class     = var.mwaa_environment_class
  execution_role_arn    = local.mwaa_execution_role_arn
  source_bucket_arn     = local.dag_bucket_arn
  dag_s3_path           = "dags/"
  requirements_s3_path  = "requirements.txt"
  webserver_access_mode = "PUBLIC_ONLY"
  min_workers           = var.mwaa_min_workers
  max_workers           = var.mwaa_max_workers
  network_configuration {
    security_group_ids = [aws_security_group.mwaa.id]
    subnet_ids         = aws_subnet.private[*].id
  }

  logging_configuration {
    dag_processing_logs {
      enabled   = true
      log_level = "INFO"
    }
    task_logs {
      enabled   = true
      log_level = "INFO"
    }
    worker_logs {
      enabled   = true
      log_level = "INFO"
    }
    scheduler_logs {
      enabled   = true
      log_level = "INFO"
    }
    webserver_logs {
      enabled   = true
      log_level = "INFO"
    }
  }

  # Configure Airflow to use AWS Secrets Manager as the secrets backend
  # and expose the DAG bucket name and raw bucket name to DAGs via custom config options.
  # Custom options in airflow_configuration_options are accepted by MWAA
  # (see AWS MWAA docs: "Custom options" under "Using Apache Airflow configuration options")
  airflow_configuration_options = {
    "secrets.backend" = "airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend"
    "secrets.backend_kwargs" = jsonencode({
      "connections_prefix" = var.project_name
      "variables_prefix"   = var.project_name
    })
    # Custom config for DAG bucket name (read by hello_world DAG via conf.get)
    "mwaa.dag_bucket" = local.dag_bucket_name
    # Custom config for raw bucket name (read by ingestion DAGs via conf.get)
    "mwaa.raw_bucket" = local.raw_bucket_name
  }

  tags = var.tags
}