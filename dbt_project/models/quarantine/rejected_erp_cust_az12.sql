{{ config(materialized='table') }}

select
    cid,
    bdate,
    gen,
    'ERP' as dwh_source_system,
    now() as dwh_create_date,
    'bdate > current_date (future birthdate)' as rejection_reason
from {{ source('bronze', 'erp_cust_az12') }}
where bdate > current_date