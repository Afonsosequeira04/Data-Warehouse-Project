terraform {
  backend "s3" {
    # Bucket name must match the state_bucket_name variable with name_suffix.
    # Set via -backend-config="bucket=dwh-terraform-state-<suffix>" or edit this file.
    bucket       = "dwh-terraform-state-persistent"
    key          = "aws/persistent/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
    encrypt      = true
  }
}