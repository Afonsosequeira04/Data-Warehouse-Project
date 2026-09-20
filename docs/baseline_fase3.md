# Baseline Fase 3 — Contagens antes da migração dbt

Data/Hora: 2026-09-20 22:34:32

## Bronze (raw)
| Tabela | Contagem |
|--------|---------|
| crm_cust_info | 18494 |
| crm_prd_info | 397 |
| crm_sales_details | 60398 |
| erp_cust_az12 | 18484 |
| erp_loc_a101 | 18484 |
| erp_px_cat_g1v2 | 37 |

## Silver (cleaned)
| Tabela | Contagem |
|--------|---------|
| crm_cust_info | 18484 |
| crm_prd_info | 397 |
| crm_sales_details | 60398 |
| erp_cust_az12 | 18484 |
| erp_loc_a101 | 18484 |
| erp_px_cat_g1v2 | 37 |

## Gold (views)
| View | Contagem |
|------|---------|
| dim_customers | 18484 |
| dim_products | 295 |
| fact_sales | 60398 |

**Status:** Todos os valores batem com os esperados no PLANO_MODERNIZACAO.md.