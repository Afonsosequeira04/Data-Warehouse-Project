output "raw_bucket_name" {
  description = "Name of the raw data S3 bucket"
  value       = aws_s3_bucket.raw.id
}

output "raw_bucket_arn" {
  description = "ARN of the raw data S3 bucket"
  value       = aws_s3_bucket.raw.arn
}

output "dag_bucket_name" {
  description = "Name of the MWAA DAG S3 bucket"
  value       = aws_s3_bucket.dag.id
}

output "dag_bucket_arn" {
  description = "ARN of the MWAA DAG S3 bucket"
  value       = aws_s3_bucket.dag.arn
}

output "uc_managed_bucket_name" {
  description = "Name of the Unity Catalog managed storage S3 bucket"
  value       = aws_s3_bucket.uc_managed.id
}

output "uc_managed_bucket_arn" {
  description = "ARN of the Unity Catalog managed storage S3 bucket"
  value       = aws_s3_bucket.uc_managed.arn
}

output "mwaa_execution_role_arn" {
  description = "ARN of the MWAA execution role"
  value       = aws_iam_role.mwaa_execution.arn
}

output "world_bank_secret_arn" {
  description = "ARN of the World Bank secret"
  value       = aws_secretsmanager_secret.world_bank.arn
}

output "fred_secret_arn" {
  description = "ARN of the FRED secret"
  value       = aws_secretsmanager_secret.fred.arn
}

output "fivetran_rds_secret_arn" {
  description = "ARN of the Fivetran RDS secret"
  value       = aws_secretsmanager_secret.fivetran_rds.arn
}

output "databricks_secret_arn" {
  description = "ARN of the Databricks secret"
  value       = aws_secretsmanager_secret.databricks.arn
}

output "budget_name" {
  description = "Name of the AWS Budget"
  value       = aws_budgets_budget.main.name
}

output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region"
  value       = var.aws_region
}