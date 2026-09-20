{{ config(materialized='table') }}

select
    replace(cid, '-', '') as cid,
    case
        when trim(cntry) = 'DE' then 'Germany'
        when trim(cntry) in ('US', 'USA') then 'United States'
        when trim(cntry) = '' or cntry is null then 'n/a'
        else trim(cntry)
    end as cntry,
    'ERP' as dwh_source_system,
    now() as dwh_create_date
from {{ source('bronze', 'erp_loc_a101') }}