{{ config(materialized='table') }}

select
    cst_id,
    cst_key,
    cst_firstname,
    cst_lastname,
    cst_marital_status,
    cst_gndr,
    cst_create_date,
    'CRM' as dwh_source_system,
    now() as dwh_create_date,
    'cst_id is null' as rejection_reason
from {{ source('bronze', 'crm_cust_info') }}
where cst_id is null