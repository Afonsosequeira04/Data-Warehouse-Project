{{ config(materialized='view') }}

with crm as (
    select * from {{ ref('stg_crm__cust_info') }}
),
erp_cust as (
    select * from {{ ref('stg_erp__cust_az12') }}
),
erp_loc as (
    select * from {{ ref('stg_erp__loc_a101') }}
)
select
    row_number() over (order by coalesce(c.cst_id, 0)) as customer_key,
    coalesce(c.cst_key, e.cid) as customer_id,
    c.cst_id as crm_customer_id,
    e.cid as erp_customer_id,
    trim(coalesce(c.cst_firstname, '')) || ' ' || trim(coalesce(c.cst_lastname, '')) as customer_full_name,
    coalesce(c.cst_firstname, '') as customer_first_name,
    coalesce(c.cst_lastname, '') as customer_last_name,
    coalesce(c.cst_marital_status, 'n/a') as marital_status,
    coalesce(c.cst_gndr, e.gen, 'n/a') as gender,
    e.bdate as birth_date,
    l.cntry as country,
    c.cst_create_date as customer_create_date,
    c.dwh_source_system as crm_source_system,
    e.dwh_source_system as erp_source_system,
    c.dwh_create_date as dwh_create_date
from crm c
full outer join erp_cust e on c.cst_key = e.cid
left join erp_loc l on e.cid = l.cid