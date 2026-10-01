# Evidências P1 - Persistent Foundation

## O que foi criado

### Stack AWS Persistente
- **3 buckets S3**: bucket de dados raw, bucket de DAGs do MWAA, bucket gerenciado do Unity Catalog. Todos com versioning, SSE-S3, public access blocked e `prevent_destroy`.
- **Role IAM do MWAA**: execution role com acesso aos buckets S3, Secrets Manager (World Bank, FRED, Fivetran RDS, Databricks) e CloudWatch Logs.
- **Secrets Manager**: 4 secrets criados (containers apenas, sem valores): world-bank, fred, fivetran-rds, databricks.
- **AWS Budget**: orçamento de $10/mês importado, com notificações em 50%, 80%, 100% actual e 100% forecasted.

### Stack Databricks
- **Storage credential**: credencial baseada em IAM role para acesso S3 via Unity Catalog.
- **3 external locations**: raw (read-only), dags (read/write), uc-managed (read/write).
- **Catálogo `dwh_dev`**: com storage root no bucket gerenciado.
- **6 schemas**: bronze, silver, gold, quarantine, snapshots, raw_fivetran.
- **Grants**: um `databricks_grants` por objeto (catálogo, schemas, external locations), com papéis mapeados via variáveis `uc_principal_*`. BI só tem acesso ao gold. `CREATE_EXTERNAL_TABLE` apenas nas external locations.

## Smoke test
Um CSV de 2 linhas num prefixo `smoke-test/` do bucket das DAGs foi lido no SQL Editor com `read_files(..., format => 'csv', header => true)`, via external location do Unity Catalog, sem credenciais no código. Resultado: 2 linhas (id 1 e 2, value "ok"). O ficheiro foi apagado depois.

## Terraform plan
`terraform plan` dá "No changes" nos dois stacks (AWS persistente e Databricks).

## Nota
Os screenshots previstos no plano foram omitidos; podem ser acrescentados no P11.