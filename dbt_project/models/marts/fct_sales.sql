{{ config(materialized='view') }}

with sales as (
    select * from {{ ref('stg_crm__sales_details') }}
),
customers as (
    select customer_key, crm_customer_id from {{ ref('dim_customers') }}
),
products as (
    select product_key, product_key_business from {{ ref('dim_products') }}
)
select
    row_number() over (order by s.sls_ord_num) as sales_key,
    s.sls_ord_num as sales_order_number,
    dc.customer_key as customer_key,
    dp.product_key as product_key,
    s.sls_cust_id as erp_customer_ref,
    s.sls_prd_key as product_business_key,
    s.sls_order_dt as order_date,
    s.sls_ship_dt as ship_date,
    s.sls_due_dt as due_date,
    s.sls_sales as sales_amount,
    s.sls_quantity as sales_quantity,
    s.sls_price as unit_price,
    s.dwh_create_date as dwh_create_date
from sales s
left join customers dc on s.sls_cust_id = dc.crm_customer_id
left join products dp on s.sls_prd_key = dp.product_key_business