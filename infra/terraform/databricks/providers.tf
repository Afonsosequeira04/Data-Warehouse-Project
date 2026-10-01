provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}