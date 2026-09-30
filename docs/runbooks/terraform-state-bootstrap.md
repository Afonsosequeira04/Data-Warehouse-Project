# Manual Terraform State Bucket Bootstrap

This document describes the manual steps required to create the S3 bucket for Terraform state storage before running `terraform init` on the persistent stack.

## Prerequisites

- AWS CLI configured with the `dwh` profile
- AWS account with permissions to create S3 buckets and configure bucket policies

## Commands

Run the following commands in order:

### 1. Create the S3 bucket

```bash
aws s3api create-bucket \
  --bucket dwh-terraform-state-persistent \
  --region us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2 \
  --profile dwh
```

### 2. Enable versioning

```bash
aws s3api put-bucket-versioning \
  --bucket dwh-terraform-state-persistent \
  --versioning-configuration Status=Enabled \
  --profile dwh
```

### 3. Enable server-side encryption (SSE-S3)

```bash
aws s3api put-bucket-encryption \
  --bucket dwh-terraform-state-persistent \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }
    ]
  }' \
  --profile dwh
```

### 4. Block public access

```bash
aws s3api put-public-access-block \
  --bucket dwh-terraform-state-persistent \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --profile dwh
```

### 5. Verify the bucket configuration

```bash
aws s3api get-bucket-versioning --bucket dwh-terraform-state-persistent --profile dwh
aws s3api get-bucket-encryption --bucket dwh-terraform-state-persistent --profile dwh
aws s3api get-public-access-block --bucket dwh-terraform-state-persistent --profile dwh
```

## Notes

- The bucket name `dwh-terraform-state-persistent` must be globally unique. If it's taken, choose a different name and update `backend.tf` accordingly.
- This bucket is created manually because Terraform cannot manage its own state bucket (chicken-and-egg problem).
- The bucket uses SSE-S3 encryption (AES256) as per the project's decision to not require KMS at startup (D-003).
- The bucket has versioning enabled to allow state recovery.
- Public access is blocked to prevent accidental exposure.
- Terraform uses native lockfile locking (`use_lockfile = true`) since DynamoDB is out of scope (D-006 consequence).

## After Bootstrap

Once the bucket is created, run:

```bash
cd infra/terraform/aws/persistent
terraform init
terraform validate
terraform plan
```

And similarly for the Databricks stack:

```bash
cd infra/terraform/databricks
terraform init
terraform validate
terraform plan
```