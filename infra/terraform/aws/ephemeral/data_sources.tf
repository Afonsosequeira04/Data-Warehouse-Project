data "terraform_remote_state" "persistent" {
  backend = "s3"
  config = {
    bucket  = "${var.state_bucket_name}-${var.name_suffix}"
    key     = "aws/persistent/terraform.tfstate"
    region  = var.aws_region
    profile = var.aws_profile
  }
}

# Persistent stack outputs
locals {
  raw_bucket_name         = data.terraform_remote_state.persistent.outputs.raw_bucket_name
  raw_bucket_arn          = data.terraform_remote_state.persistent.outputs.raw_bucket_arn
  dag_bucket_name         = data.terraform_remote_state.persistent.outputs.dag_bucket_name
  dag_bucket_arn          = data.terraform_remote_state.persistent.outputs.dag_bucket_arn
  mwaa_execution_role_arn = data.terraform_remote_state.persistent.outputs.mwaa_execution_role_arn
  aws_account_id          = data.terraform_remote_state.persistent.outputs.aws_account_id
}