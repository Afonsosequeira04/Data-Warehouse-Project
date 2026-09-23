{{ config(materialized='table') }}

with source as (
    select
        sls_ord_num,
        sls_prd_key,
        sls_cust_id,
        sls_order_dt,
        sls_ship_dt,
        sls_due_dt,
        sls_sales,
        sls_quantity,
        sls_price,
        'CRM' as dwh_source_system,
        now() as dwh_create_date
    from {{ source('bronze', 'crm_sales_details') }}
),
flagged as (
    select
        *,
        case
            when sls_sales is null or sls_sales <= 0
                 or sls_sales != sls_quantity * abs(sls_price)
            then 'sls_sales invalid (null, <=0, or != quantity * abs(price))'
            when sls_price is null or sls_price <= 0
            then 'sls_price invalid (null or <=0)'
        end as rejection_reason
    from source
    where sls_sales is null
       or sls_sales <= 0
       or sls_sales != sls_quantity * abs(sls_price)
       or sls_price is null
       or sls_price <= 0
)
select
    sls_ord_num,
    sls_prd_key,
    sls_cust_id,
    sls_order_dt,
    sls_ship_dt,
    sls_due_dt,
    sls_sales,
    sls_quantity,
    sls_price,
    dwh_source_system,
    dwh_create_date,
    rejection_reason
from flagged