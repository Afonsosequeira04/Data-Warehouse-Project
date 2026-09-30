# Manual Terraform Bootstrap and Deployment Runbook

This document describes the manual steps required to bootstrap the Terraform state bucket and deploy the persistent foundation stacks.

## Prerequisites

- AWS CLI configured with the `dwh` profile
- AWS account with permissions to create S3 buckets, IAM roles, Secrets Manager secrets, and Budgets
- Databricks workspace (Free Edition) in us-east-2 with Unity Catalog enabled
- Databricks personal access token
- Choose a globally unique `name_suffix` (e.g., `abc123` or your account ID)

## 1. Choose a Unique Suffix

All S3 bucket names must be globally unique. Choose a suffix and use it consistently:

```bash
export NAME_SUFFIX="your-unique-suffix"  # e.g., abc123, or your AWS account ID
```

This suffix will be appended to:
- `dwh-raw-data-${NAME_SUFFIX}`
- `dwh-mwaa-dags-${NAME_SUFFIX}`
- `dwh-terraform-state-${NAME_SUFFIX}`
- Databricks storage credential IAM role name

## 2. Bootstrap Terraform State Bucket

Create the S3 bucket for Terraform state storage before running `terraform init` on the persistent stack.

```bash
# 1. Create the S3 bucket
aws s3api create-bucket \
  --bucket "dwh-terraform-state-${NAME_SUFFIX}" \
  --region us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2 \
  --profile dwh

# 2. Enable versioning
aws s3api put-bucket-versioning \
  --bucket "dwh-terraform-state-${NAME_SUFFIX}" \
  --versioning-configuration Status=Enabled \
  --profile dwh

# 3. Enable server-side encryption (SSE-S3)
aws s3api put-bucket-encryption \
  --bucket "dwh-terraform-state-${NAME_SUFFIX}" \
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

# 4. Block public access
aws s3api put-public-access-block \
  --bucket "dwh-terraform-state-${NAME_SUFFIX}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --profile dwh

# 5. Verify the bucket configuration
aws s3api get-bucket-versioning --bucket "dwh-terraform-state-${NAME_SUFFIX}" --profile dwh
aws s3api get-bucket-encryption --bucket "dwh-terraform-state-${NAME_SUFFIX}" --profile dwh
aws s3api get-public-access-block --bucket "dwh-terraform-state-${NAME_SUFFIX}" --profile dwh
```

## 3. Set Environment Variables

```bash
export DATABRICKS_HOST="https://<workspace-url>.databricks.com"
export DATABRICKS_TOKEN="<personal-access-token>"
export AWS_PROFILE="dwh"
export AWS_REGION="us-east-2"
export NAME_SUFFIX="your-unique-suffix"
export BUDGET_NAME="your-existing-budget-name"  # Exact name of the existing AWS Budget
```

## 4. Deploy AWS Persistent Stack

```bash
cd infra/terraform/aws/persistent

# Initialize with backend config pointing to your state bucket
terraform init -backend-config="bucket=dwh-terraform-state-${NAME_SUFFIX}"

# Validate configuration
terraform validate

# Import existing AWS Budget (MUST run before plan/apply)
# Format: <account_id>:<budget_name>
# Get account ID: aws sts get-caller-identity --query Account --output text --profile dwh
terraform import aws_budgets_budget.main "$(aws sts get-caller-identity --query Account --output text --profile dwh):${BUDGET_NAME}"

# Plan and apply
terraform plan \
  -var="name_suffix=${NAME_SUFFIX}" \
  -var="budget_name=${BUDGET_NAME}"

terraform apply \
  -var="name_suffix=${NAME_SUFFIX}" \
  -var="budget_name=${BUDGET_NAME}"
```

Capture outputs (raw_bucket_arn, dag_bucket_arn, mwaa_execution_role_arn, secret ARNs, aws_account_id).

## 5. Deploy Databricks Stack

```bash
cd ../../databricks

# Initialize
terraform init

# Validate
terraform validate

# Plan and apply
# Use the bucket ARNs and names from AWS persistent stack outputs
terraform plan \
  -var="name_suffix=${NAME_SUFFIX}" \
  -var="raw_bucket_arn=<raw_bucket_arn_from_aws_stack>" \
  -var="dag_bucket_arn=<dag_bucket_arn_from_aws_stack>" \
  -var="raw_bucket_name=<raw_bucket_name_from_aws_stack>" \
  -var="dag_bucket_name=<dag_bucket_name_from_aws_stack>" \
  -var="sql_warehouse_id=<existing-sql-warehouse-id>"

terraform apply \
  -var="name_suffix=${NAME_SUFFIX}" \
  -var="raw_bucket_arn=<raw_bucket_arn_from_aws_stack>" \
  -var="dag_bucket_arn=<dag_bucket_arn_from_aws_stack>" \
  -var="raw_bucket_name=<raw_bucket_name_from_aws_stack>" \
  -var="dag_bucket_name=<dag_bucket_name_from_aws_stack>" \
  -var="sql_warehouse_id=<existing-sql-warehouse-id>"
```

Capture outputs (storage_credential_external_id, databricks_storage_role_arn, external location names, catalog/schemas).

## 6. Verify Deployment

### Circular Dependency Resolution (IAM Role Trust Policy)

The Databricks storage credential IAM role trust policy uses the `external_id` from the `databricks_storage_credential` resource. This creates a circular dependency that is resolved in Terraform by:

1. The IAM role is created in the **Databricks stack** (same stack as the storage credential)
2. The trust policy references `databricks_storage_credential.s3.external_id` directly
3. Terraform creates the storage credential first (which generates the external_id), then creates the IAM role with that external_id in the trust policy
4. The role is **self-assuming**: the trust policy allows the AWS account root to assume the role, conditioned on the external_id matching the storage credential's external_id

This means a single `terraform apply` on the Databricks stack works without manual intervention.

### Verify Raw External Location is Read-Only

```bash
# Check that raw external location has read_only = true
# This is enforced in the Databricks stack: databricks_external_location.raw has read_only = true
```

### Verify Catalog Storage Root

The catalog `dwh_dev` uses a separate Unity Catalog managed external location (`s3://<raw-bucket>/unity-catalog`) for its storage root, NOT the raw data prefix. The raw external location is read-only for Databricks.

### Smoke Test

```bash
# 1. Write a test file to S3 (under a test prefix, not raw)
aws s3 cp test.json "s3://${RAW_BUCKET}/test/verify.json" --profile dwh

# 2. Read via Databricks SQL Warehouse
# In Databricks SQL editor:
# SELECT * FROM read_files('s3://<raw-bucket>/test/verify.json', format => 'json');
```

## Notes

- **Budget**: The $10/month AWS Budget already exists and is imported. Notifications are managed manually in the AWS console.
- **Secrets**: Only secret containers are created by Terraform. Secret values must be set manually in AWS Secrets Manager after deployment.
- **SQL Warehouse**: Free Edition allows only one SQL Warehouse. The stack references the existing one via data source.
- **Metastore**: Free Edition has one metastore per account attached to the workspace. The stack uses the workspace-level metastore data source.
- **Grants**: All grants use the `uc_principal` variable (default: `account users`). Review and restrict to specific groups/principals for production.
- **State Locking**: Uses native lockfile locking (`use_lockfile = true`) since DynamoDB is out of scope.

## Grant Reference (for verification)

All grants use principal = `var.uc_principal` (default: `account users`). Verify each privilege against Databricks provider docs:

| Securable | Privileges | Notes |
|-----------|------------|-------|
| Storage Credential | USAGE | Required to use the credential |
| External Location (raw) | READ_FILES | Read-only access to raw data |
| External Location (dag) | READ_FILES, WRITE_FILES | Read/write for DAGs |
| External Location (uc_managed) | READ_FILES, WRITE_FILES, CREATE_EXTERNAL_TABLE | UC managed storage |
| Catalog (dwh_dev) | USE_CATALOG, CREATE_SCHEMA | Catalog access |
| Schema (bronze) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Bronze layer |
| Schema (silver) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Silver layer |
| Schema (gold) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Gold layer |
| Schema (quarantine) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Quarantine |
| Schema (snapshots) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Snapshots |
| Schema (raw_fivetran) | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE | Fivetran landing |

Privilege names verified against Databricks Terraform provider documentation for `databricks_grant` resource.