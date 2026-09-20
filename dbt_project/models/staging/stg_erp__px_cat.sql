{{ config(materialized='table') }}

select
    id,
    cat,
    subcat,
    maintenance,
    'ERP' as dwh_source_system,
    now() as dwh_create_date
from {{ source('bronze', 'erp_px_cat_g1v2') }}