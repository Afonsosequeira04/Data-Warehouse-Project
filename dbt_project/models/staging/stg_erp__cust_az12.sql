{{ config(materialized='table') }}

select
    case when cid like 'NAS%' then substring(cid from 4) else cid end as cid,
    case when bdate > current_date then null else bdate end as bdate,
    case
        when upper(trim(gen)) in ('F', 'FEMALE') then 'Female'
        when upper(trim(gen)) in ('M', 'MALE') then 'Male'
        else 'n/a'
    end as gen,
    'ERP' as dwh_source_system,
    now() as dwh_create_date
from {{ source('bronze', 'erp_cust_az12') }}