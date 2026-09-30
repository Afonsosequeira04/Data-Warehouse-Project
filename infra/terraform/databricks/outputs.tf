output "storage_credential_name" {
  description = "Name of the Databricks storage credential"
  value       = databricks_storage_credential.s3.name
}

output "external_location_raw_name" {
  description = "Name of the raw data external location"
  value       = databricks_external_location.raw.name
}

output "external_location_dag_name" {
  description = "Name of the DAG bucket external location"
  value       = databricks_external_location.dag.name
}

output "catalog_name" {
  description = "Name of the Unity Catalog catalog"
  value       = databricks_catalog.dwh_dev.name
}

output "schema_bronze_name" {
  description = "Name of the bronze schema"
  value       = databricks_schema.bronze.name
}

output "schema_silver_name" {
  description = "Name of the silver schema"
  value       = databricks_schema.silver.name
}

output "schema_gold_name" {
  description = "Name of the gold schema"
  value       = databricks_schema.gold.name
}

output "schema_quarantine_name" {
  description = "Name of the quarantine schema"
  value       = databricks_schema.quarantine.name
}

output "schema_snapshots_name" {
  description = "Name of the snapshots schema"
  value       = databricks_schema.snapshots.name
}

output "schema_raw_fivetran_name" {
  description = "Name of the raw_fivetran schema"
  value       = databricks_schema.raw_fivetran.name
}

output "sql_warehouse_id" {
  description = "ID of the existing SQL Warehouse"
  value       = data.databricks_sql_warehouse.existing.id
}

output "sql_warehouse_name" {
  description = "Name of the existing SQL Warehouse"
  value       = data.databricks_sql_warehouse.existing.name
}