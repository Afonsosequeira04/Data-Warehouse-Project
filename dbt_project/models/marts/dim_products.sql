{{ config(materialized='view') }}

with crm as (
    select * from {{ ref('stg_crm__prd_info') }}
),
erp_cat as (
    select * from {{ ref('stg_erp__px_cat') }}
),
latest_products as (
    select
        c.prd_id,
        c.prd_key,
        c.cat_id,
        c.prd_nm,
        c.prd_cost,
        c.prd_line,
        c.prd_start_dt,
        c.prd_end_dt,
        p.cat,
        p.subcat,
        p.maintenance,
        row_number() over (partition by c.prd_key order by c.prd_start_dt desc) as rn
    from crm c
    left join erp_cat p on c.cat_id = p.id
)
select
    row_number() over (order by prd_id) as product_key,
    prd_key as product_key_business,
    prd_id as crm_product_id,
    cat_id as category_id,
    prd_nm as product_name,
    prd_cost as product_cost,
    prd_line as product_line,
    prd_start_dt as product_start_date,
    prd_end_dt as product_end_date,
    coalesce(cat, 'n/a') as category,
    coalesce(subcat, 'n/a') as subcategory,
    coalesce(maintenance, 'n/a') as maintenance_required
from latest_products
where rn = 1