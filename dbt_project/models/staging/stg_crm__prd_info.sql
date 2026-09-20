{{ config(materialized='table') }}

select
    prd_id,
    replace(substring(prd_key from 1 for 5), '-', '_') as cat_id,
    substring(prd_key from 7) as prd_key,
    prd_nm,
    coalesce(prd_cost, 0) as prd_cost,
    case upper(trim(prd_line))
        when 'M' then 'Mountain'
        when 'R' then 'Road'
        when 'S' then 'Other Sales'
        when 'T' then 'Touring'
        else 'n/a'
    end as prd_line,
    prd_start_dt,
    (lead(prd_start_dt) over (partition by prd_key order by prd_start_dt) - 1)::date as prd_end_dt,
    'CRM' as dwh_source_system,
    now() as dwh_create_date
from {{ source('bronze', 'crm_prd_info') }}