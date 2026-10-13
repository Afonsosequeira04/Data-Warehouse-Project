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

resource "aws_secretsmanager_secret" "macro_watchlist_db" {
  name        = "${var.project_name}/macro-watchlist-db"
  description = "Supabase PostgreSQL (macro_watchlist) connection details for Fivetran"
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "databricks" {
  name        = "${var.project_name}/databricks"
  description = "Databricks workspace connection details"
  tags        = var.tags
}