# Data Platform Cloud

Plataforma de dados ponta a ponta, 100% cloud, construída com **dados reais**: ingestão de APIs públicas e de uma fonte SaaS/DB, arquitetura medallion no Databricks, transformação com dbt, governance com Unity Catalog e infraestrutura como código.

> As fontes são reais; o pipeline que as ingere, transforma e governa também é real.

## Arquitetura

```
APIs públicas ──► Airflow (MWAA) ──► S3 Raw ──► Databricks Bronze ─┐
                                                                   ├─► dbt Silver ─► dbt Gold ─► AI/BI
SaaS / DB ──────► Fivetran ─────────────────► Databricks Raw ──────┘
                                                        │
                                                  Unity Catalog (governance, lineage)
```

Diagrama completo: [`docs/architecture.png`](docs/architecture.png) · Ficha técnica: [`docs/ficha_tecnica.md`](docs/ficha_tecnica.md)

## Stack

| Camada | Tecnologia |
|---|---|
| Cloud / Storage | AWS, S3 |
| Orquestração | Amazon MWAA (Apache Airflow) |
| Ingestão | Python (APIs), Fivetran (SaaS/DB) |
| Lakehouse | Databricks, Delta Lake |
| Governance | Unity Catalog |
| Transformação | dbt-core, dbt-databricks |
| BI | Databricks AI/BI |
| IaC | Terraform |
| CI/CD | GitHub Actions (OIDC) |
| Secrets | AWS Secrets Manager |

## Fontes de dados

| Fonte | Tipo | Caminho |
|---|---|---|
| `<API 1>` | API pública REST | Airflow → S3 → Bronze |
| `<API 2>` | API pública REST | Airflow → S3 → Bronze |
| `<SaaS/DB>` | Conector Fivetran | Fivetran → Databricks |

## Camadas de dados

- **Bronze:** dados próximos da origem, com metadata técnica (`_batch_id`, `_ingested_at`, `_source_file`, `_source_system`, `_batch_date`).
- **Silver:** tipos, deduplicação, normalização e regras de negócio (dbt staging).
- **Gold:** dimensões e factos analíticos (dbt marts).
- **Quarantine:** registos rejeitados pelas validações.

## Estrutura do repositório

```
├── ingestion/        # código de extração (APIs) e config Fivetran
├── orchestration/    # DAGs Airflow
├── dbt_project/      # models, snapshots, tests, macros
├── infra/terraform/  # AWS e Databricks
├── docs/             # ficha técnica e diagramas
├── tests/
└── .github/workflows/
```

## Como começar

**Pré-requisitos:** conta AWS, workspace Databricks (AWS), Terraform, Python 3.11+, dbt-core com dbt-databricks.

```bash
# 1. Infraestrutura
cd infra/terraform/aws && terraform init && terraform plan
cd ../databricks && terraform init && terraform plan

# 2. Dependências Python
pip install -r requirements.txt

# 3. dbt
cd dbt_project
dbt deps
dbt build
```

Credenciais e API keys ficam no AWS Secrets Manager; nunca no repositório.

## CI/CD

| Evento | Ações |
|---|---|
| Pull Request | testes, `dbt parse`, lint, gitleaks, `terraform plan` |
| Merge em `main` | `terraform apply`, deploy Databricks, `dbt build` |

## Roadmap

- [ ] S3, IAM e Unity Catalog (storage credential + external location)
- [ ] Ingestão API 1 → S3 → Bronze
- [ ] Modelos dbt (staging, marts, testes)
- [ ] MWAA e DAG `daily_pipeline`
- [ ] Ingestão API 2
- [ ] Fivetran (fonte SaaS/DB)
- [ ] Terraform completo e GitHub Actions
- [ ] Dashboards AI/BI (negócio e qualidade)

## Custos

O MWAA e o SQL Warehouse são os componentes mais caros. Há um AWS Budget configurado; desligar os recursos quando não estiverem em uso.

## Licença

MIT
