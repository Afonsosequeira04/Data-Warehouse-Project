# ADR-004: MWAA Ephemeral Operating Model

## Status

Proposed

## Context

Per D-005 and D-006, MWAA is used directly (no local Airflow) as an ephemeral environment: created for a work window with Terraform and destroyed afterwards. The persistent stack (S3, IAM, Secrets, Budget, Unity Catalog) survives destroys; the ephemeral stack (VPC, NAT, MWAA, MWAA logs) does not.

Key questions to resolve:
1. **Creation/destruction workflow**: How are apply/destroy triggered? Manual? GitHub Actions? CLI?
2. **State that must survive destroy**: DAGs, requirements.txt, connections, variables, secrets references
3. **Networking cost options**: NAT Gateway (expensive, always on) vs. alternatives (public MWAA, VPC endpoints, no NAT)
4. **DAG validation before spend**: How to verify DAGs parse/import correctly before creating MWAA environment

Constraints:
- MWAA cannot be paused; only destruction stops billing (~$0.49/hour for small env + NAT + logs)
- Creation takes ~20-30 min; destruction takes ~15-20 min (also billed)
- DAGs and `requirements.txt` live in persistent S3 (managed by persistent stack)
- Connections/variables must come from AWS Secrets Manager (Airflow secrets backend) or Terraform
- Airflow metadata DB (run history, UI variables) is ephemeral and lost on destroy
- Persistent facts (batch IDs, ingestion status) live in S3/Databricks, not Airflow DB

## Decision Being Considered

What is the MWAA operating model: creation/destruction workflow, persistent state strategy, networking approach, and pre-flight validation?

## Options

### Option 1: Manual Terraform CLI (Current Baseline)

- `terraform apply -target=aws_ephemeral` to create
- `terraform destroy -target=aws_ephemeral` to destroy
- Run from local machine or CI with OIDC credentials
- DAG validation: separate `terraform plan` + local `airflow dags test` or `python -m py_compile` on DAG files

**Trade-offs:**
- Pros:
  - Simple, explicit, full control
  - No additional automation infrastructure
  - Clear audit trail in terminal output
- Cons:
  - Human error risk (forget destroy, wrong target)
  - Requires local Terraform + AWS creds
  - No standardized pre-flight checks
  - Hard to enforce "validate before spend"

### Option 2: GitHub Actions Workflows (Create / Destroy)

Two manual-dispatch workflows:
- `mwaa-create.yml`: `terraform init/plan/apply` on ephemeral stack
- `mwaa-destroy.yml`: `terraform destroy` on ephemeral stack
- Both require manual approval in Actions UI
- Pre-flight: separate `mwaa-validate.yml` runs DAG import test on PR and before create

**Trade-offs:**
- Pros:
  - Auditable, repeatable, no local setup needed
  - OIDC authentication built in
  - Can enforce pre-flight validation gate
  - Team can trigger without local Terraform
- Cons:
  - Workflow runtime adds to GH Actions minutes (minor)
  - Must manage Terraform state locking (S3 native lockfile)
  - Destroy workflow must be run explicitly (no auto-cleanup)

### Option 3: GitHub Actions with TTL / Scheduled Destroy

Same as Option 2, but `mwaa-create` workflow optionally accepts a `ttl_hours` input. A scheduled workflow or the create workflow itself schedules a destroy after TTL (via EventBridge + Lambda or a second workflow dispatch).

**Trade-offs:**
- Pros:
  - Prevents "forgot to destroy" cost overruns
  - Self-service with guardrails
- Cons:
  - More complex (EventBridge, Lambda, or workflow chaining)
  - TTL may cut off a running DAG
  - Additional AWS resources (Lambda, EventBridge) - though minor

### Option 4: Wrapper Script / Makefile

A `scripts/mwaa-up.sh` and `scripts/mwaa-down.sh` that:
- Run pre-flight checks (DAG parse test, terraform fmt/validate)
- Execute terraform apply/destroy with correct targets
- Output cost estimate and duration
- Verify post-destroy cleanup

**Trade-offs:**
- Pros:
  - Encapsulates best practices
  - Can include cost estimation
  - Shareable across team
- Cons:
  - Still requires local execution environment
  - Script maintenance burden

## Networking Options (Sub-decision)

### Networking Option A: Private MWAA + NAT Gateway (Default)

MWAA in private subnets, NAT Gateway for outbound (PyPI, Databricks, AWS APIs).
- Cost: ~$45/month for NAT Gateway (per AZ) + data processing
- Reliable, standard pattern

### Networking Option B: Public MWAA (No NAT)

MWAA in public subnets with public IPs, no NAT.
- Cost: $0 NAT
- Security: MWAA web server exposed (but auth protected); workers need outbound internet
- Risk: Non-standard, may not support all MWAA features

### Networking Option C: VPC Endpoints (PrivateLink)

MWAA in private subnets, VPC endpoints for S3, Secrets Manager, Databricks, CloudWatch.
- Cost: ~$7-10/month per endpoint (cheaper than NAT for high traffic)
- Complexity: More Terraform, must ensure all required services have endpoints

### Networking Option D: Hybrid (Public MWAA Web, Private Workers + NAT)

Web server public, workers private with NAT.
- Cost: Reduced NAT usage
- Complexity: Higher

## Consequences

| Aspect | Manual CLI | GH Actions Create/Destroy | GH Actions + TTL | Wrapper Script |
|--------|------------|---------------------------|------------------|----------------|
| Accessibility | Local only | Any team member | Any team member | Local only |
| Audit trail | Terminal | GH Actions logs | GH Actions logs | Terminal |
| Pre-flight enforcement | Manual | Workflow gate | Workflow gate | Script-enforced |
| Forget-destroy protection | None | Manual discipline | Auto (TTL) | Manual discipline |
| Setup required | Terraform, AWS CLI | GH OIDC, repo secrets | GH OIDC + EventBridge | Script + local env |

| Networking | Cost | Security | Complexity | Reliability |
|------------|------|----------|------------|-------------|
| Private + NAT | High | High | Low | High |
| Public | None | Medium | Low | Medium |
| VPC Endpoints | Medium | High | Medium | High |
| Hybrid | Medium | High | High | High |

## Decision

*To be filled when Accepted: which operating model and networking option were chosen and why.*

## Related

- D-005: MWAA is ephemeral
- D-006: Persistent vs ephemeral stack split
- P2 tasks in NOTION_PROJECT_PLAN.md
- Runbook: `docs/runbooks/mwaa-up-down.md` (to be created in P2)