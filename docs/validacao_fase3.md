# Validação Fase 3 — Reconciliação dbt vs Legacy

Data/Hora: 2026-09-20 22:51:25

## Resumo Executivo
✅ **Validação passou completamente.** Todas as contagens batem e todos os diffs `EXCEPT` (nos dois sentidos) retornam 0 linhas. O dbt replica fielmente a lógica do legacy Silver/Gold.

---

## 1. Contagens (row counts)

| Camada | Tabela/View | dbt (staging/marts) | Legacy (silver/gold) | Status |
|--------|-------------|---------------------|----------------------|--------|
| Staging | stg_crm__cust_info | 18.484 | 18.484 | ✅ |
| Staging | stg_crm__prd_info | 397 | 397 | ✅ |
| Staging | stg_crm__sales_details | 60.398 | 60.398 | ✅ |
| Staging | stg_erp__cust_az12 | 18.484 | 18.484 | ✅ |
| Staging | stg_erp__loc_a101 | 18.484 | 18.484 | ✅ |
| Staging | stg_erp__px_cat | 37 | 37 | ✅ |
| Marts | dim_customers | 18.484 | 18.484 | ✅ |
| Marts | dim_products | 295 | 295 | ✅ |
| Marts | fct_sales | 60.398 | 60.398 | ✅ |

---

## 2. Diff `EXCEPT` (ignorando `dwh_create_date`)

### Staging vs Silver (12 verificações — 6 tabelas × 2 direções)
```
stg_crm__cust_info       vs silver.crm_cust_info       : 0
silver.crm_cust_info     vs stg_crm__cust_info         : 0
stg_crm__prd_info        vs silver.crm_prd_info        : 0
silver.crm_prd_info      vs stg_crm__prd_info          : 0
stg_crm__sales_details   vs silver.crm_sales_details   : 0
silver.crm_sales_details vs stg_crm__sales_details     : 0
stg_erp__cust_az12       vs silver.erp_cust_az12       : 0
silver.erp_cust_az12     vs stg_erp__cust_az12         : 0
stg_erp__loc_a101        vs silver.erp_loc_a101        : 0
silver.erp_loc_a101      vs stg_erp__loc_a101          : 0
stg_erp__px_cat          vs silver.erp_px_cat_g1v2     : 0
silver.erp_px_cat_g1v2   vs stg_erp__px_cat            : 0
```

### Marts vs Gold (6 verificações — 3 views × 2 direções)
```
dim_customers marts vs gold : 0
dim_customers gold vs marts : 0
dim_products marts vs gold  : 0
dim_products gold vs marts  : 0
fct_sales marts vs gold     : 0
fct_sales gold vs marts     : 0
```

---

## 3. Observações

- **`dwh_create_date`**: Ignorado nos diffs, pois é `now()` no dbt e `DEFAULT NOW()` no legacy — gera valores diferentes a cada execução, mas a coluna existe em ambos os lados com o mesmo propósito.
- **Chaves surrogate**: A ordenação `ROW_NUMBER() OVER (ORDER BY ...)` é idêntica no legacy e no dbt (`customer_key`, `product_key`, `sales_key`), garantindo que as mesmas linhas recebam as mesmas chaves.
- **Tipos de dados**: Todos os casts (INT→DATE, limpeza de strings, etc.) produziram resultados idênticos.

---

## 4. Conclusão
A migração para dbt está **validada**. Pode-se prosseguir para o PASSO 6 (fecho técnico: mover scripts legacy, `dbt docs generate`, atualizar README, prova final `make all-dbt` + `make all` + `make dbt-build`).