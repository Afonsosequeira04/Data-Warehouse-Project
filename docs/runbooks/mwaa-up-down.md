# MWAA Up/Down Runbook

This runbook documents the exact commands and procedures to create, validate, use, and destroy the ephemeral MWAA environment for the cloud-data-platform project.

## Prerequisites

- AWS CLI configured with the `dwh` profile (or appropriate credentials)
    - Terraform >= 1.10.0 installed
    - GitHub CLI (`gh`) optional, for PR creation
    - Python 3.12 with a virtual environment for local DAG validation
    - Secret `cloud-data-platform/world-bank` with value `{"base_url":"https://api.worldbank.org/v2"}` exists in Secrets Manager (one-time manual step)

## Directory Structure

```
infra/terraform/aws/
├── persistent/     # Persistent stack (S3, IAM, Secrets, Budget, Unity Catalog)
└── ephemeral/      # Ephemeral stack (VPC, NAT, MWAA, CloudWatch Logs)
```

## Persistent Stack (Must Exist First)

The persistent stack must be applied before the ephemeral stack. It provides:
- Raw data S3 bucket
- DAG/requirements S3 bucket
- MWAA execution role with permissions
- Secrets Manager entries (including `cloud-data-platform/world-bank`)
- AWS Budget
- Unity Catalog setup

```bash
export AWS_PROFILE=dwh
cd infra/terraform/aws/persistent
terraform init -backend-config="bucket=dwh-terraform-state-9015f2"
terraform plan -var="name_suffix=9015f2" -var="budget_notification_email=your-email@example.com"
# Review plan, then apply
terraform apply -var="name_suffix=9015f2" -var="budget_notification_email=your-email@example.com"
```

## Ephemeral Stack Operations

### 1. Pre-flight Validation (Run Before Every Create)

Validate DAGs parse correctly without MWAA:

```bash
# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install test dependencies
pip install -r tests/test-requirements.txt

# Run DAG import test
python -m pytest tests/test_dag_import.py -v

# Deactivate
deactivate
```

Validate Terraform configuration:

```bash
export AWS_PROFILE=dwh
cd infra/terraform/aws/ephemeral
terraform fmt -check
terraform init -backend-config="bucket=dwh-terraform-state-9015f2"
terraform validate
terraform plan -var="name_suffix=9015f2"
```

**Do not proceed if any validation fails.**

### 2. Upload DAGs and Requirements to DAG Bucket (BEFORE Creating MWAA)

The MWAA environment reads DAGs and `requirements.txt` from the persistent DAG bucket at startup.
Upload them before creating the environment:

```bash
# Sync DAGs and requirements to the DAG bucket
aws s3 sync orchestration/dags/ s3://dwh-mwaa-dags-9015f2/dags/ --profile dwh --exclude "__pycache__/*"
aws s3 cp orchestration/requirements.txt s3://dwh-mwaa-dags-9015f2/requirements.txt --profile dwh

# Verify upload
aws s3 ls s3://dwh-mwaa-dags-9015f2/dags/ --profile dwh
aws s3 ls s3://dwh-mwaa-dags-9015f2/requirements.txt --profile dwh
```

### 3. Create MWAA Environment (Apply Ephemeral Stack)

```bash
export AWS_PROFILE=dwh
cd infra/terraform/aws/ephemeral
terraform apply -var="name_suffix=9015f2"
```

**Expected duration:** 20-30 minutes (billed time starts immediately)
**Estimated cost:** ~$0.49/hour for mw1.small + ~$0.045/hour for NAT Gateway + CloudWatch Logs
**Total estimated hourly cost:** ~$0.55-0.60/hour

Wait for the apply to complete. Note the `mwaa_webserver_url` from the outputs.

### 4. Verify MWAA Environment

1. Open the MWAA webserver URL in a browser (IAM authentication required)
2. Log in with your AWS credentials (IAM user/role with MWAA access)
3. Verify the `hello_world` DAG appears in the DAG list
4. Verify the DAG shows no import errors

### 5. Run the hello_world DAG

1. In the Airflow UI, find the `hello_world` DAG
2. Click "Trigger DAG" (manual trigger, no schedule)
3. Wait for the run to complete (should take < 1 minute)
4. Verify the task `read_variable_and_write_s3` succeeds
5. Check the task logs to confirm:
   - The `world-bank` variable was read from Secrets Manager
   - A JSON file was written to `s3://dwh-mwaa-dags-9015f2/test/hello_world/`

### 6. Collect Evidence

Capture the following for the phase evidence (text only, no screenshots):

- [ ] CloudWatch Logs sample: filter `airflow-cloud-data-platform-dev-Task` for the run
- [ ] S3 object verification: `aws s3 ls s3://dwh-mwaa-dags-9015f2/test/hello_world/ --profile dwh`
- [ ] Terraform apply output (duration, resources created)
- [ ] MWAA environment creation time (from timestamps)

All evidence goes in the single file `docs/evidence/P2-evidence.md` (text only).

Record measured values:
- **Terraform apply duration:** 35 minutes
- **MWAA environment creation time (from timestamps):** 34m 47s
- **DAG run duration:** < 1 minute
- **Total window duration so far:** 72 minutes

### 7. Destroy MWAA Environment

**IMPORTANT:** Destroy the ephemeral stack when done to stop billing. MWAA cannot be paused.

```bash
export AWS_PROFILE=dwh
cd infra/terraform/aws/ephemeral
terraform destroy -var="name_suffix=9015f2"
```

**Expected duration:** 15-20 minutes (also billed)
**DO NOT use `-auto-approve`** — confirm manually.

### 8. Post-Destroy Verification

After destroy completes, verify nothing billable remains:

```bash
# Verify MWAA environment is gone
aws mwaa list-environments --profile dwh --region us-east-2
# Should not show cloud-data-platform-dev

# Verify NAT Gateway is deleted
aws ec2 describe-nat-gateways --filter "Name=tag:project,Values=cloud-data-platform" --profile dwh --region us-east-2
# Should show no NAT gateways or only "deleted" state

# Verify VPC is deleted
aws ec2 describe-vpcs --filters "Name=tag:project,Values=cloud-data-platform" "Name=tag:stack,Values=ephemeral" --profile dwh --region us-east-2
# Should show no VPCs

# Verify CloudWatch Log Groups (created by MWAA, not Terraform; they persist but have no cost without logs)
# Log groups: airflow-cloud-data-platform-dev-{DAGProcessing,Scheduler,Task,WebServer,Worker}
# If cleanup needed (rare), delete manually:
# aws logs delete-log-group --log-group-name airflow-cloud-data-platform-dev-Task --profile dwh --region us-east-2

# Verify persistent stack is UNTOUCHED
aws s3 ls s3://dwh-raw-data-9015f2/ --profile dwh          # Raw bucket exists
aws s3 ls s3://dwh-mwaa-dags-9015f2/ --profile dwh        # DAG bucket exists
aws secretsmanager list-secrets --profile dwh --region us-east-2 | grep cloud-data-platform  # Secrets exist
aws budgets describe-budgets --profile dwh --region us-east-2  # Budget exists
```

Check AWS Cost Explorer or Billing console to confirm no unexpected charges.

Record measured values:
- **Terraform destroy duration:** 27 minutes
- **Total billable window (create + run + destroy):** 73 minutes
- **Estimated total cost:** $0.65

## Assumptions Documented from ADR-004

1. **Web server access: PUBLIC_ONLY** — The MWAA web server is accessible over the public internet with IAM authentication. This is configured via `webserver_access_mode = "PUBLIC_ONLY"` in the MWAA environment. Workers are in private subnets and route outbound via the NAT Gateway.

2. **Single NAT Gateway** — One NAT Gateway in a single public subnet (us-east-2a) is used for cost optimization. This is not highly available but acceptable for an ephemeral portfolio environment.

3. **Secrets Manager Backend** — Connections and variables use the prefix `cloud-data-platform` configured via `airflow_configuration_options` in Terraform. Secret names in AWS Secrets Manager are `cloud-data-platform/<name>` (e.g., `cloud-data-platform/world-bank`).

4. **DAG Bucket** — The persistent DAG bucket (`dwh-mwaa-dags-<suffix>`) stores DAGs and `requirements.txt`. A rebuilt MWAA environment picks them up automatically with no manual steps.

5. **No Airflow Metadata DB Persistence** — Run history, UI variables, and connections created in the UI are lost on destroy. Only Terraform-managed configuration and Secrets Manager entries persist.

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| DAG import errors in Airflow UI | Run pre-flight validation locally first (`pytest tests/test_dag_import.py`) |
| MWAA create fails with IAM error | Verify persistent stack execution role has CloudWatch Logs permission for pattern `airflow-cloud-data-platform-dev-*` |
| DAG can't read variable | Verify secret `cloud-data-platform/world-bank` exists in Secrets Manager |
| DAG can't write to S3 | Verify execution role has `S3DagBucketAccess` policy for the DAG bucket |
| Destroy hangs on NAT Gateway | Wait longer; NAT Gateway deletion can take 10+ minutes |
| Log group not deleted | Delete manually via `aws logs delete-log-group` |

## Cost Estimation (us-east-2, approximate)

| Resource | Hourly Cost | Notes |
|----------|-------------|-------|
| MWAA mw1.small | ~$0.49 | Billed while environment exists |
| NAT Gateway (1 AZ) | ~$0.045 | Billed while NAT exists |
| NAT Data Processing | ~$0.045/GB | Minimal for DAG runs |
| CloudWatch Logs | ~$0.50/GB ingested | Depends on log volume |
| **Total/hour (estimate)** | **~$0.55-0.60** | |

**Example 1-hour window:** ~$0.60
**Example 2-hour window (create + run + destroy):** ~$1.20 + creation/destruction time
**Measured P2 window (73 min):** ~$0.65

Always check current AWS pricing before running.

## Evidence Checklist for P2

All evidence goes in the single file `docs/evidence/P2-evidence.md` (text only, no screenshots):

- [ ] Terraform apply output (duration, resources created)
- [ ] S3 object verification (`aws s3 ls` and `aws s3 cp` output)
- [ ] CloudWatch Logs sample (filtered for "Wrote s3://")
- [ ] Terraform destroy output (duration, resources destroyed)
- [ ] Post-destroy verification commands output
- [ ] Measured times and estimated cost (filled in above)