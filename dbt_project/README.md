# dbt Project — Data Warehouse

Transformação da camada Silver (limpeza/normalização) e Gold (star schema) usando dbt-core + dbt-postgres.

## Estrutura
- `models/staging/` — modelos **table** (espelho da Silver legacy), 6 modelos
- `models/marts/` — modelos **view** (dimensões + fato), 3 modelos
- `models/staging/_sources.yml` — declaração das 6 tabelas Bronze
- `macros/generate_schema_name.sql` — macro para schemas `staging` / `marts` sem prefixo
- `profiles.yml` — lê credenciais via `env_var()` (POSTGRES_*)
- `requirements.txt` — versões fixas de dbt-core e dbt-postgres

## Comandos (do Makefile da raiz)
```bash
make dbt-setup    # cria .venv e instala requirements.txt
make dbt-build    # dbt build completo (staging + marts + testes)
make dbt-docs     # gera docs (owner serve com make dbt-docs)
make all-dbt      # pipeline completo: up -> init-db -> validate-headers -> load-bronze -> dbt-build
```

## Convenções
- Nomenclatura: `stg_<source>__<table>`, `dim_*`, `fct_*`
- Referências: `{{ source('bronze', 'table') }}` e `{{ ref('model') }}`
- Testes built-in apenas: `not_null`, `unique`, `relationships`, `accepted_values`