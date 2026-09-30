variable "databricks_host" {
  description = "Databricks workspace URL (e.g., https://dbc-xxxxxxxx.xxxx.databricks.com)"
  type        = string
}

variable "databricks_token" {
  description = "Databricks personal access token"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = "dwh"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "cloud-data-platform"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "name_suffix" {
  description = "Unique suffix for globally unique names (must match AWS persistent stack)"
  type        = string
}

variable "raw_bucket_arn" {
  description = "ARN of the raw data S3 bucket"
  type        = string
}

variable "dag_bucket_arn" {
  description = "ARN of the MWAA DAG S3 bucket"
  type        = string
}

variable "raw_bucket_name" {
  description = "Name of the raw data S3 bucket"
  type        = string
}

variable "dag_bucket_name" {
  description = "Name of the MWAA DAG S3 bucket"
  type        = string
}

variable "uc_managed_bucket_arn" {
  description = "ARN of the Unity Catalog managed storage S3 bucket"
  type        = string
}

variable "uc_managed_bucket_name" {
  description = "Name of the Unity Catalog managed storage S3 bucket"
  type        = string
}

variable "sql_warehouse_id" {
  description = "ID of the existing Databricks SQL Warehouse (Free Edition only allows one)"
  type        = string
}

variable "uc_principal_pipeline" {
  description = "Unity Catalog principal for pipeline identity (write access to bronze, silver, gold, quarantine, snapshots, raw_fivetran)"
  type        = string
  default     = "account users"
}

variable "uc_principal_bi" {
  description = "Unity Catalog principal for BI consumers (read access to gold)"
  type        = string
  default     = "account users"
}

variable "uc_principal_developer" {
  description = "Unity Catalog principal for developers (read access to all, write to none)"
  type        = string
  default     = "account users"
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default = {
    project     = "cloud-data-platform"
    stack       = "databricks"
    environment = "dev"
    managed_by  = "terraform"
  }
}