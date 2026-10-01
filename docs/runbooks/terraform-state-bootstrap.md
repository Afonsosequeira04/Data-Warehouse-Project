# Manual Terraform Bootstrap and Deployment Runbook

This document describes the manual steps required to bootstrap the Terraform state bucket and deploy the persistent foundation stacks.

## Prerequisites

- AWS CLI configured with the `dwh` profile
- AWS account with permissions to create S3 buckets, IAM roles, Secrets Manager secrets, and Budgets
- Databricks workspace (Free Edition) in us-east-2 with Unity Catalog enabled
- Databricks personal access token
- Choose a globally unique `name_suffix` (e.g., `abc123` or your account ID)
- Budget notification email address

## 1. Choose a Unique Suffix

All S3 bucket names must be globally unique. Choose a suffix and use it consistently:

```bash
export NAME_SUFFIX="your-unique-suffix"  # e.g., abc123, or your AWS account ID
```

This suffix will be appended to:
- `dwh-raw-data-${NAME_SUFFIX}`
- `dwh-mwaa-dags-${NAME_SUFFIX}`
- `dwh-terraform-state-${NAME_SUFFIX}`
- `cloud-data-platform-uc-managed-${NAME_SUFFIX}`
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

## 3. Create Local terraform.tfvars Files (gitignored)

Create `infra/terraform/aws/persistent/terraform.tfvars` and `infra/terraform/databricks/terraform.tfvars` to avoid repeating `-var` flags. Both files are gitignored.

```bash
# AWS Persistent Stack tfvars
cat > infra/terraform/aws/persistent/terraform.tfvars <<EOF
name_suffix              = "${NAME_SUFFIX}"
budget_name              = "cloud-data-platform-budget"
budget_notification_email = "your-email@example.com"
EOF

# Databricks Stack tfvars (fill in after AWS stack outputs)
cat > infra/terraform/databricks/terraform.tfvars <<EOF
name_suffix                    = "${NAME_SUFFIX}"
raw_bucket_arn                 = ""  # Fill after AWS apply
dag_bucket_arn                 = ""  # Fill after AWS apply
raw_bucket_name                = ""  # Fill after AWS apply
dag_bucket_name                = ""  # Fill after AWS apply
uc_managed_bucket_arn          = ""  # Fill after AWS apply
uc_managed_bucket_name         = ""  # Fill after AWS apply
sql_warehouse_id               = ""  # Existing SQL Warehouse ID
storage_credential_external_id = "0000"  # Fake for first apply; replace with real value for second apply
uc_principal_pipeline          = "account users"
uc_principal_bi                = "account users"
uc_principal_developer         = "account users"
EOF

# Verify they are ignored
git check-ignore infra/terraform/aws/persistent/terraform.tfvars
git check-ignore infra/terraform/databricks/terraform.tfvars
```

## 4. Set Databricks Credentials via Environment Variables

The Databricks provider reads credentials from `DATABRICKS_HOST` and `DATABRICKS_TOKEN` environment variables (or `TF_VAR_databricks_host` / `TF_VAR_databricks_token`).

```bash
export DATABRICKS_HOST="https://<workspace-url>.databricks.com"
export DATABRICKS_TOKEN="<personal-access-token>"
export AWS_PROFILE="dwh"
export AWS_REGION="us-east-2"
```

## 5. Deploy AWS Persistent Stack (Single Apply)

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

# Plan and apply (uses terraform.tfvars)
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

Capture outputs:
- `raw_bucket_arn`, `dag_bucket_arn`, `uc_managed_bucket_arn`
- `raw_bucket_name`, `dag_bucket_name`, `uc_managed_bucket_name`
- `mwaa_execution_role_arn`, secret ARNs, `aws_account_id`

Update `infra/terraform/databricks/terraform.tfvars` with the bucket ARNs and names from AWS stack outputs.

## 6. Deploy Databricks Stack (Two Apply Flow)

### First Apply (with fake external_id, skip_validation = true, targeted)

```bash
cd ../../databricks

# Initialize with backend config pointing to your state bucket
terraform init -backend-config="bucket=dwh-terraform-state-${NAME_SUFFIX}"

# Validate
terraform validate

# First apply: create storage credential with fake external_id and skip_validation = true
# Target only the storage credential to avoid validating external locations with fake ID
terraform plan -target=databricks_storage_credential.s3 -out=plan1.tfplan
terraform apply plan1.tfplan
```

This creates:
- IAM role with trust policy using fake external_id "0000"
- Storage credential with `skip_validation = true`

### Get the Real External ID

```bash
# After first apply, get the real external_id from the storage credential
# In Databricks UI: Catalog > External Data > Credentials > click the credential > copy "External ID"
# Or via Databricks API
# Note: The storage_credential_external_id output was removed as the attribute could not be verified in provider docs
```

### Second Apply (with real external_id, skip_validation = false, full stack)

```bash
# Edit infra/terraform/databricks/terraform.tfvars by hand and replace:
# storage_credential_external_id = "0000"
# with the real external ID from the Databricks UI (e.g., "d3b07384d113edec49eaa6238ad5ff00")

# Full plan and apply
terraform plan -out=plan2.tfplan
terraform apply plan2.tfplan
```

This updates:
- IAM role trust policy with the real external_id (via `databricks_aws_unity_catalog_assume_role_policy` data source)
- Storage credential with `skip_validation = false` (now validates the IAM role)
- External locations with `skip_validation = false` (now validate the credential)
- Catalog, schemas, grants

## 7. Post-Deploy Steps

### Set Secret Values in AWS Secrets Manager (when needed for later phases)

```bash
# FRED API key (for P3)
aws secretsmanager put-secret-value \
  --secret-id cloud-data-platform/fred \
  --secret-string '{"base_url":"https://api.stlouisfed.org/fred","api_key":"<YOUR_FRED_API_KEY>"}' \
  --profile dwh

# Fivetran RDS connection (for P8)
aws secretsmanager put-secret-value \
  --secret-id cloud-data-platform/fivetran-rds \
  --secret-string '{"host":"<RDS_ENDPOINT>","port":5432,"database":"macro_watchlist_db","username":"<USER>","password":"<PASSWORD>"}' \
  --profile dwh

# Databricks connection (for CI/CD)
aws secretsmanager put-secret-value \
  --secret-id cloud-data-platform/databricks \
  --secret-string '{"host":"<DATABRICKS_HOST>","token":"<DATABRICKS_TOKEN>"}' \
  --profile dwh
```

### Verify Deployment

#### Verify Raw External Location is Read-Only

```bash
# Check that raw external location has read_only = true
# This is enforced in the Databricks stack: databricks_external_location.raw has read_only = true
```

#### Verify Catalog Storage Root

The catalog `dwh_dev` uses a separate Unity Catalog managed external location (`s3://<uc-managed-bucket>`) for its storage root, NOT the raw data bucket. The raw external location is read-only for Databricks.

#### Smoke Test

```bash
# 1. Write a test file to S3 (under a test prefix, not raw)
aws s3 cp test.json "s3://${RAW_BUCKET}/test/verify.json" --profile dwh

# 2. Read via Databricks SQL Warehouse
# In Databricks SQL editor:
# SELECT * FROM read_files('s3://<raw-bucket>/test/verify.json', format => 'json');
```

## Notes

- **Budget**: The $10/month AWS Budget is imported. Notifications are defined in code (50%, 80%, 100% actual; 100% forecasted). After import, `terraform plan` will show no changes to notifications if they already match the existing budget.
- **Secrets**: Only secret containers are created by Terraform. Secret values must be set manually in AWS Secrets Manager after deployment (see step 7, needed for later phases).
- **SQL Warehouse**: Free Edition allows only one SQL Warehouse. The stack references the existing one via data source.
- **Metastore**: Free Edition has one metastore per account attached to the workspace. The stack creates the catalog without explicit `metastore_id` (workspace-level auth).
- **Grants**: Three principal variables for least privilege: `uc_principal_pipeline` (write), `uc_principal_bi` (read gold), `uc_principal_developer` (read all). Default to `account users`; restrict for production.
- **State Locking**: Uses native lockfile locking (`use_lockfile = true`) since DynamoDB is out of scope.
- **Two-Apply Flow**: Required to resolve the circular dependency between IAM role trust policy (needs storage credential's external_id) and storage credential (needs IAM role). First apply uses fake external_id with `skip_validation = true` targeted to storage credential; second apply uses real external_id with `skip_validation = false` for full stack.

## Grant Reference (for PR body)

All grants use principal variables. Verified against Unity Catalog docs where possible:

| Securable | Principal | Privileges | Verified in Docs |
|-----------|-----------|------------|------------------|
| External Location (raw) | pipeline, bi, developer | READ_FILES | Yes |
| External Location (dag) | pipeline | READ_FILES, WRITE_FILES | Yes |
| External Location (uc_managed) | pipeline | READ_FILES, WRITE_FILES, CREATE_EXTERNAL_TABLE | Yes |
| Catalog (dwh_dev) | pipeline, bi, developer | USE_CATALOG | Yes |
| Catalog (dwh_dev) | pipeline | CREATE_SCHEMA | Yes |
| Schema (dwh_dev.bronze) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT verified |
| Schema (dwh_dev.bronze) | bi, developer | USE_SCHEMA, SELECT | USE_SCHEMA, SELECT verified |
| Schema (dwh_dev.silver) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | Same as bronze |
| Schema (dwh_dev.silver) | bi, developer | USE_SCHEMA, SELECT | Same as bronze |
| Schema (dwh_dev.gold) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | Same as bronze |
| Schema (dwh_dev.gold) | bi, developer | USE_SCHEMA, SELECT | Same as bronze |
| Schema (dwh_dev.quarantine) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | Same as bronze |
| Schema (dwh_dev.quarantine) | bi, developer | USE_SCHEMA, SELECT | Same as bronze |
| Schema (dwh_dev.snapshots) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | Same as bronze |
| Schema (dwh_dev.snapshots) | bi, developer | USE_SCHEMA, SELECT | Same as bronze |
| Schema (dwh_dev.raw_fivetran) | pipeline | USE_SCHEMA, CREATE_TABLE, CREATE_EXTERNAL_TABLE, SELECT | Same as bronze |
| Schema (dwh_dev.raw_fivetran) | bi, developer | USE_SCHEMA, SELECT | Same as bronze |

**Removed**: Storage credential USAGE grant (not a valid privilege on storage credential). MODIFY privilege on schemas (not verified for schemas).