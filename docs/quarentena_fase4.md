# Quarentena — Fase 4 (Qualidade de dados avançada)

Registado em 2026-09-24 após `make dbt-build` na branch `fase-4-qualidade-dados-avancada`.

## Resumo de contagens

| Tabela de quarentena                        | Linhas |
|--------------------------------------------|--------|
| `quarantine.rejected_crm_cust_info`        | 4      |
| `quarantine.rejected_crm_sales_details`    | 35     |
| `quarantine.rejected_erp_cust_az12`        | 16     |

---

## Amostras (2-3 linhas por tabela)

### `rejected_crm_cust_info` — 4 linhas (cst_id IS NULL)

| cst_id | cst_key | cst_firstname | cst_lastname | cst_marital_status | cst_gndr | cst_create_date | dwh_source_system | dwh_create_date | rejection_reason |
|--------|---------|---------------|--------------|--------------------|----------|-----------------|-------------------|-----------------|------------------|
| (null) | SF566   | (null)        | (null)       | (null)             | (null)   | (null)          | CRM               | 2026-09-23 23:30:53 | cst_id is null |
| (null) | PO25    | (null)        | (null)       | (null)             | (null)   | (null)          | CRM               | 2026-09-23 23:30:53 | cst_id is null |
| (null) | 13451235| (null)        | (null)       | (null)             | (null)   | (null)          | CRM               | 2026-09-23 23:30:53 | cst_id is null |

> Estas 4 linhas desapareciam silenciosamente no staging (filtro `where cst_id is not null`). Agora ficam visíveis para auditoria.

---

### `rejected_crm_sales_details` — 35 linhas (sls_sales ou sls_price inválidos)

| sls_ord_num | sls_prd_key | sls_cust_id | sls_order_dt | sls_ship_dt | sls_due_dt | sls_sales | sls_quantity | sls_price | rejection_reason |
|-------------|-------------|-------------|--------------|-------------|------------|-----------|--------------|-----------|------------------|
| SO51259     | WB-H098     | 11433       | 20130101     | 20130108    | 20130113   | 10        | 2            | (null)    | sls_price invalid (null or <=0) |
| SO57804     | BK-M38S-40  | 16470       | 20130511     | 20130518    | 20130523   | 769       | 1            | -769      | sls_price invalid (null or <=0) |
| SO58335     | TI-M823     | 13326       | 20130520     | 20130527    | 20130601   | 35        | 2            | 35        | sls_sales invalid (null, <=0, or != quantity * abs(price)) |
| SO61548     | CA-1098     | 12386       | 20130705     | 20130712    | 20130717   | (null)    | 1            | 9         | sls_sales invalid (null, <=0, or != quantity * abs(price)) |
| SO61570     | CA-1098     | 17809       | 20130705     | 20130712    | 20130717   | -18       | 1            | 9         | sls_sales invalid (null, <=0, or != quantity * abs(price)) |
| SO69066     | SJ-0194-L   | 17923       | 20131024     | 20131031    | 20131105   | -54       | 1            | 54        | sls_sales invalid (null, <=0, or != quantity * abs(price)) |

> **Padrões observados:**
> - **Preço nulo** (7 linhas): o staging recalcula `sls_sales = quantity * abs(price)`, mas o preço original era NULL.
> - **Preço negativo** (8 linhas): ex. `-769`, `-30`, `-22` — o staging usa `abs(sls_price)`.
> - **Sales nulo** (8 linhas): sales ausente, preço presente — staging recalcula.
> - **Sales <= 0** (5 linhas): ex. `0`, `-18`, `-54` — staging recalcula.
> - **Sales inconsistente** (7 linhas): sales ≠ quantity × abs(price) — staging recalcula.

> Antes da quarentena, estas linhas eram "corrigidas" silenciosamente no staging. Agora o valor original fica preservado para investigação.

---

### `rejected_erp_cust_az12` — 16 linhas (bdate > CURRENT_DATE)

| cid          | bdate      | gen    | dwh_source_system | dwh_create_date | rejection_reason |
|--------------|------------|--------|-------------------|-----------------|------------------|
| NASAW00011257| 2050-07-06 | Female | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |
| NASAW00011410| 2042-02-22 | Male   | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |
| NASAW00011551| 2050-05-21 | Male   | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |
| NASAW00011562| 2038-10-17 | Male   | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |
| NASAW00011915| 9999-09-13 | Male   | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |
| AW00028543   | 2980-03-09 | Male   | ERP               | 2026-09-23 23:30:53 | bdate > current_date (future birthdate) |

> Estas 16 linhas têm datas de nascimento no futuro (algumas em 9999, outras em 2038–2080). No staging, `bdate` vira `NULL` silenciosamente (`case when bdate > current_date then null else bdate end`). A quarentena preserva a data original para que se possa decidir se é erro de digitação, placeholder, ou dado real.

---

## Testes de negócio (singular tests)

| Teste | Resultado | Detalhes |
|-------|-----------|----------|
| `assert_fct_sales_amount_equals_quantity_times_price` | **PASS** | 0 linhas violam `sales_amount = sales_quantity * unit_price` (tolerância 0.01), excluindo nulos. A recalc no staging garante consistência. |
| `assert_sales_dates_are_chronological` | **PASS** | 0 linhas com `order_date > ship_date` ou `order_date > due_date` quando as três datas existem. Dados legacy são cronologicamente consistentes. |

---

## Testes dbt totais (Fase 3 + Fase 4)

- Testes Fase 3 (built-in): 28
- `dbt_utils.unique_combination_of_columns` em `stg_crm__sales_details (sls_ord_num, sls_prd_key)`: 1
- Testes singulares Fase 4: 2
- Testes `not_null` nas tabelas de quarentena: 6 (1 WARN esperado em `rejected_crm_cust_info.cst_id`)
- **Total executado: 37 data tests** (48 PASS, 1 WARN, 0 ERROR no `dbt build`)

---

## Comandos para reproduzir

```bash
# Na branch fase-4-qualidade-dados-avancada
make up
make init-db
make validate-headers
make load-bronze
make dbt-build
```

---

## Conclusão

✅ **Definition of Done cumprida:**
- `make dbt-build` passa sem ERROR
- Linhas com `cst_id` nulo, `sls_sales` inconsistente, ou `bdate` futura aparecem nas tabelas de quarentena (antes desapareciam ou eram corrigidas silenciosamente)
- Testes de negócio existem e correm: amount=qty×price, datas cronológicas, grain da encomenda (unique_combination_of_columns)
- Sintaxe de testes migrada para `arguments:` — zero avisos de deprecation
- dbt-utils 1.4.1 instalado e usado