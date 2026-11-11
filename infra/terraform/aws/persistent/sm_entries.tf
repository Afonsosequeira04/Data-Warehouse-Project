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

resource "aws_secretsmanager_secret" "firms" {
  name        = "${var.project_name}/firms"
  description = "NASA FIRMS MAP key and configuration"
  tags        = var.tags
}