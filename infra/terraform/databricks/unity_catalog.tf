resource "databricks_storage_credential" "s3" {
  name            = "${var.project_name}-${var.environment}-storage-credential"
  read_only       = false
  skip_validation = false

  aws_iam_role {
    role_arn = var.databricks_storage_role_arn
  }
}

resource "databricks_external_location" "raw" {
  name            = "${var.project_name}-${var.environment}-raw-location"
  credential_name = databricks_storage_credential.s3.name
  url             = "s3://${var.raw_bucket_name}"
  read_only       = false
  skip_validation = false
}

resource "databricks_external_location" "dag" {
  name            = "${var.project_name}-${var.environment}-dag-location"
  credential_name = databricks_storage_credential.s3.name
  url             = "s3://${var.dag_bucket_name}"
  read_only       = false
  skip_validation = false
}

resource "databricks_catalog" "dwh_dev" {
  name         = "dwh_dev"
  comment      = "Data warehouse catalog for development environment"
  storage_root = "s3://${var.raw_bucket_name}/unity-catalog"
  metastore_id = data.databricks_metastore.workspace.metastore_id
}

data "databricks_metastore" "workspace" {}

resource "databricks_schema" "bronze" {
  name         = "bronze"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Bronze layer - raw data with technical metadata"
}

resource "databricks_schema" "silver" {
  name         = "silver"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Silver layer - cleaned and normalized data"
}

resource "databricks_schema" "gold" {
  name         = "gold"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Gold layer - analytical dimensions and facts"
}

resource "databricks_schema" "quarantine" {
  name         = "quarantine"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Quarantine layer - rejected records with diagnostic metadata"
}

resource "databricks_schema" "snapshots" {
  name         = "snapshots"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Snapshots layer - dbt SCD2 historical tracking"
}

resource "databricks_schema" "raw_fivetran" {
  name         = "raw_fivetran"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Fivetran managed landing area for operational database"
}

resource "databricks_grant" "storage_credential_usage" {
  principal          = "account users"
  privileges         = ["USAGE"]
  storage_credential = databricks_storage_credential.s3.name
}

resource "databricks_grant" "external_location_usage_raw" {
  principal         = "account users"
  privileges        = ["USAGE"]
  external_location = databricks_external_location.raw.name
}

resource "databricks_grant" "external_location_usage_dag" {
  principal         = "account users"
  privileges        = ["USAGE"]
  external_location = databricks_external_location.dag.name
}

resource "databricks_grant" "catalog_usage" {
  principal  = "account users"
  privileges = ["USE_CATALOG"]
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "catalog_create_schema" {
  principal  = "account users"
  privileges = ["CREATE_SCHEMA"]
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_bronze" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.bronze.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_bronze" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.bronze.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_silver" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.silver.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_silver" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.silver.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_gold" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.gold.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_gold" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.gold.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_quarantine" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.quarantine.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_quarantine" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.quarantine.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_snapshots" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.snapshots.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_snapshots" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.snapshots.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_usage_raw_fivetran" {
  principal  = "account users"
  privileges = ["USE_SCHEMA"]
  schema     = databricks_schema.raw_fivetran.name
  catalog    = databricks_catalog.dwh_dev.name
}

resource "databricks_grant" "schema_create_raw_fivetran" {
  principal  = "account users"
  privileges = ["CREATE_TABLE"]
  schema     = databricks_schema.raw_fivetran.name
  catalog    = databricks_catalog.dwh_dev.name
}

data "databricks_sql_warehouse" "existing" {
  id = var.sql_warehouse_id
}