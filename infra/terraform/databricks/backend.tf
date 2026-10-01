terraform {
  backend "s3" {
    bucket       = "dwh-terraform-state-persistent"
    key          = "databricks/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
    encrypt      = true
  }
}