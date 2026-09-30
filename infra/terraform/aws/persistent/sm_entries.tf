resource "aws_secretsmanager_secret" "world_bank" {
  name        = "${var.project_name}/world-bank"
  description = "World Bank API configuration (no auth required, placeholder for future use)"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "world_bank" {
  secret_id = aws_secretsmanager_secret.world_bank.id
  secret_string = jsonencode({
    base_url = "https://api.worldbank.org/v2"
  })
}

resource "aws_secretsmanager_secret" "fred" {
  name        = "${var.project_name}/fred"
  description = "FRED API key and configuration"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "fred" {
  secret_id = aws_secretsmanager_secret.fred.id
  secret_string = jsonencode({
    base_url = "https://api.stlouisfed.org/fred"
    api_key  = "REPLACE_WITH_ACTUAL_KEY"
  })
}

resource "aws_secretsmanager_secret" "fivetran_rds" {
  name        = "${var.project_name}/fivetran-rds"
  description = "Fivetran RDS PostgreSQL connection details"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "fivetran_rds" {
  secret_id = aws_secretsmanager_secret.fivetran_rds.id
  secret_string = jsonencode({
    host     = "REPLACE_WITH_RDS_ENDPOINT"
    port     = 5432
    database = "macro_watchlist_db"
    username = "REPLACE_WITH_USERNAME"
    password = "REPLACE_WITH_PASSWORD"
  })
}

resource "aws_secretsmanager_secret" "databricks" {
  name        = "${var.project_name}/databricks"
  description = "Databricks workspace connection details"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "databricks" {
  secret_id = aws_secretsmanager_secret.databricks.id
  secret_string = jsonencode({
    host  = "REPLACE_WITH_DATABRICKS_HOST"
    token = "REPLACE_WITH_DATABRICKS_TOKEN"
  })
}