variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "AWS CLI profile to use for authentication"
  type        = string
  default     = "dwh"
}

variable "project_name" {
  description = "Project name used for naming and tagging resources"
  type        = string
  default     = "cloud-data-platform"
}

variable "environment" {
  description = "Environment name (dev, prod, etc.)"
  type        = string
  default     = "dev"
}

variable "name_suffix" {
  description = "Unique suffix for globally unique bucket names (e.g., random string or account ID)"
  type        = string
}

variable "raw_bucket_name" {
  description = "Name of the S3 bucket for immutable raw data"
  type        = string
  default     = "dwh-raw-data"
}

variable "dag_bucket_name" {
  description = "Name of the S3 bucket for MWAA DAGs and requirements"
  type        = string
  default     = "dwh-mwaa-dags"
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  type        = string
  default     = "dwh-terraform-state"
}

variable "budget_name" {
  description = "Name of the existing AWS Budget to import"
  type        = string
}

variable "budget_limit_amount" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 10
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    project     = "cloud-data-platform"
    stack       = "persistent"
    environment = "dev"
    managed_by  = "terraform"
  }
}