# Evidências P2 - Ephemeral MWAA

## O que foi criado

### Stack AWS Efémera (MWAA)
- **VPC** dedicada (10.0.0.0/16) com 2 subnets privadas e 1 pública em 2 AZs (us-east-2a, us-east-2b).
- **NAT Gateway** + Elastic IP nas subnets públicas.
- **Internet Gateway** para tráfego de entrada/saída.
- **Security Group** do MWAA com regra de egress all e ingress self-referencing.
- **Ambiente MWAA** `cloud-data-platform-dev`:
  - Airflow 3.3.1, classe `mw1.small`, 1 worker min/max.
  - Execution role do stack persistente (`cloud-data-platform-mwaa-execution-dev`).
  - DAG bucket persistente (`dwh-mwaa-dags-9015f2`), requirements no bucket.
  - Logs CloudWatch para dag-processing, scheduler, task, webserver, worker (INFO).
  - Secrets backend: Secrets Manager (ARN prefixo `cloud-data-platform/`).
- **Role e política IAM** do MWAA já existiam no stack persistente (reutilizadas).

## Ciclo executado

### Terraform apply
- **Início**: 2026-10-12 02:16:20 UTC
- **Fim**: 2026-10-12 02:51:38 UTC
- **Duração**: 35m 18s (recurso mais lento: `aws_mwaa_environment.main` — Creation complete after 34m47s)
- **Recursos criados**: 17 (0 changed, 0 destroyed)

### DAG run (hello_world)
- **S3 object criado**: `s3://dwh-mwaa-dags-9015f2/test/hello_world/run_20261012T024433Z.json`
- **Conteúdo**: `{"dag_id":"hello_world","written_at":"2026-10-12T02:44:33.327199+00:00","world_bank_keys":["base_url","format"],"dag_bucket":"dwh-mwaa-dags-9015f2","status":"success"}`
- **Log CloudWatch (Task)**: `{"logger":"task.stdout","event":"Wrote s3://dwh-mwaa-dags-9015f2/test/hello_world/run_20261012T024433Z.json (world-bank keys: ['base_url', 'format'])","level":"info"}`
- **Tempo entre apply fim e DAG run**: ~52 minutos (o DAG roda em schedule @once, assim que o scheduler arranca)

### Terraform destroy
- **Início**: 2026-10-12 03:01:58 UTC
- **Fim**: 2026-10-12 03:28:57 UTC
- **Duração**: 26m 59s
- **Recursos destruídos**: 17

## Tempos medidos

| Etapa | Início (UTC) | Fim (UTC) | Duração |
|-------|--------------|-----------|---------|
| terraform apply | 02:16:20 | 02:51:38 | 35m 18s |
| DAG hello_world run | — | 02:44:33 | ~52m após apply fim |
| terraform destroy | 03:01:58 | 03:28:57 | 26m 59s |
| **Janela total faturada** | 02:16:20 | 03:28:57 | **1h 12m 37s** |

## Verificação pós-destroy

- `aws mwaa list-environments`: `{"Environments": []}` ✅
- `aws ec2 describe-nat-gateways`: `[ "deleted" ]` ✅
- `aws ec2 describe-vpcs` (tag stack=ephemeral): `[]` ✅
- `aws ec2 describe-addresses`: `[]` ✅
- `aws logs describe-log-groups` (prefixo airflow-cloud-data-platform-dev): 5 log groups permanecem (criados pelo MWAA, não pelo Terraform; não têm custo sem logs ativos).
- `terraform plan` no stack persistente: **No changes** (exceto parâmetro de email do budget — ver nota).

## Custo

**ESTIMATE (billed window x published rates; Cost Explorer lags ~24h)**
- Janela faturada: 1h 12m 37s = 1.21 horas
- MWAA `mw1.small`: $0.49/hora
- NAT Gateway: $0.045/hora
- Total estimado: 1.21 × ($0.49 + $0.045) = **$0.65 USD**

## Nota

O ciclo não precisou de configuração na console:
- DAGs e requirements vêm do bucket persistente (S3).
- Secrets backend e `mwaa.dag_bucket` vêm do Terraform.
- O valor do secret `world-bank` é um passo manual único que persiste entre rebuilds (o secret container existe no stack persistente; só o `put-secret-value` foi feito uma vez).
- Screenshots omitidas; podem ser acrescentadas no P11.