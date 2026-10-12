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
  description = "Unique suffix for globally unique resource names (e.g., random string or account ID)"
  type        = string
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state (without suffix)"
  type        = string
  default     = "dwh-terraform-state"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (2 AZs)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (1 AZ for NAT)"
  type        = list(string)
  default     = ["10.0.101.0/24"]
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]
}

variable "mwaa_environment_class" {
  description = "MWAA environment class (e.g., mw1.small)"
  type        = string
  default     = "mw1.small"
}

variable "mwaa_min_workers" {
  description = "Minimum number of MWAA workers"
  type        = number
  default     = 1
}

variable "mwaa_max_workers" {
  description = "Maximum number of MWAA workers"
  type        = number
  default     = 1
}

variable "airflow_version" {
  description = "Airflow version for MWAA"
  type        = string
  default     = "3.3.1"
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    project    = "cloud-data-platform"
    stack      = "ephemeral"
    phase      = "P2"
    managed_by = "terraform"
  }
}