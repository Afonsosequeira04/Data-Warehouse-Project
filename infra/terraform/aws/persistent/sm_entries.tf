resource "aws_secretsmanager_secret" "world_bank" {
  name        = "${var.project_name}/world-bank"
  description = "World Bank API configuration (no auth required)"
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "fred" {
  name        = "${var.project_name}/fred"
  description = "FRED API key and configuration"
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "fivetran_rds" {
  name        = "${var.project_name}/fivetran-rds"
  description = "Fivetran RDS PostgreSQL connection details"
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "databricks" {
  name        = "${var.project_name}/databricks"
  description = "Databricks workspace connection details"
  tags        = var.tags
}