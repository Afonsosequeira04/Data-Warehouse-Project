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

variable "raw_bucket_name" {
  description = "Name of the raw data S3 bucket"
  type        = string
}

variable "dag_bucket_name" {
  description = "Name of the MWAA DAG S3 bucket"
  type        = string
}

variable "databricks_storage_role_arn" {
  description = "ARN of the IAM role for Databricks storage credential"
  type        = string
}

variable "sql_warehouse_id" {
  description = "ID of the existing Databricks SQL Warehouse (Free Edition only allows one)"
  type        = string
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