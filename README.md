# Cloud Data Platform

End-to-end, 100% cloud data platform built on **real data**: ingestion from public APIs (World Bank, FRED) and an operational database (Amazon RDS PostgreSQL via Fivetran), a medallion architecture on Databricks, dbt transformations, Unity Catalog governance and infrastructure as code.

> The sources are real; the pipeline that ingests, transforms and governs them is real too.

## Architecture

![Architecture](docs/architecture1.png)

Full details: [Technical Datasheet (PDF)](docs/technical_datasheet.pdf)

Notion Plan - https://app.notion.com/p/NOTION_PROJECT_PLAN-a0545b08c0b682c9adac81d55a468fd1?source=copy_link

## Stack

| Layer | Technology |
|---|---|
| Cloud / Storage | AWS, S3 |
| Orchestration | Amazon MWAA (Apache Airflow) |
| Ingestion | Python (APIs), Fivetran (RDS PostgreSQL) |
| Lakehouse | Databricks, Delta Lake |
| Governance | Unity Catalog |
| Transformation | dbt-core, dbt-databricks |
| BI | Databricks AI/BI |
| IaC | Terraform |
| CI/CD | GitHub Actions (OIDC) |
| Secrets | AWS Secrets Manager |

## Data Sources

| Source | Type | Path |
|---|---|---|
| **World Bank Indicators** | Public REST API | Airflow → S3 → Bronze |
| **FRED Economic Series** | Public REST API (API key) | Airflow → S3 → Bronze |
| **Amazon RDS PostgreSQL** | Fivetran connector (PostgreSQL) | Fivetran → Databricks (schema: raw_fivetran) |

## Data Layers

- **S3 Raw/Landing:** immutable source payloads, partitioned by ingestion date
- **Bronze:** data close to the source, with technical metadata (`_batch_id`, `_ingested_at`, `_source_file`, `_source_system`, `_batch_date`)
- **raw_fivetran:** Fivetran-managed landing area for the operational database (schema name confirmed in P8)
- **Silver:** types, deduplication, normalization and business rules (dbt staging)
- **Gold:** analytical dimensions and facts (dbt marts)
- **Quarantine:** records rejected by validations (structural → S3, semantic → Databricks)
- **Snapshots:** dbt snapshot history using SCD2 where historical tracking is required

## Repository Structure

```
├── ingestion/        # extraction code (APIs) and Fivetran config
├── orchestration/    # Airflow DAGs
├── dbt_project/      # models, snapshots, tests, macros
├── infra/terraform/  # AWS and Databricks
├── docs/             # datasheet and diagrams
├── tests/
└── .github/workflows/
```

## Getting Started

**Prerequisites:** AWS account, Databricks workspace (AWS), Terraform, Python 3.11+, dbt-core with dbt-databricks.

```bash
# 1. Infrastructure
cd infra/terraform/aws && terraform init && terraform plan
cd ../databricks && terraform init && terraform plan

# 2. Python dependencies
pip install -r requirements.txt

# 3. dbt
cd dbt_project
dbt deps
dbt build
```

Credentials and API keys live in AWS Secrets Manager, never in the repository.

## CI/CD

| Event | Actions |
|---|---|
| Pull Request | tests, `dbt parse`, lint, gitleaks, `terraform plan` |
| Merge to `main` | `terraform apply`, Databricks deployment, `dbt build` |

## Roadmap

- [ ] S3, IAM and Unity Catalog (storage credential + external location)
- [ ] World Bank ingestion → S3 → Bronze
- [ ] FRED ingestion → S3 → Bronze
- [ ] dbt models (staging, marts, tests)
- [ ] MWAA and the `daily_pipeline` DAG
- [ ] Fivetran (RDS PostgreSQL source)
- [ ] Full Terraform and GitHub Actions
- [ ] AI/BI dashboards (business and data quality)

## Costs

MWAA and the SQL Warehouse are the most expensive components. An AWS Budget is configured ($10/month guardrail with alerts at 50%, 80%, 100% actual and 100% forecasted); shut resources down when not in use.

## License

MIT