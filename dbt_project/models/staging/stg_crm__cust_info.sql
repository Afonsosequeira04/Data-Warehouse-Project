{{ config(materialized='table') }}

with ranked as (
    select
        cst_id,
        cst_key,
        trim(cst_firstname) as cst_firstname,
        trim(cst_lastname) as cst_lastname,
        case upper(trim(cst_marital_status))
            when 'S' then 'Single'
            when 'M' then 'Married'
            else 'n/a'
        end as cst_marital_status,
        case upper(trim(cst_gndr))
            when 'F' then 'Female'
            when 'M' then 'Male'
            else 'n/a'
        end as cst_gndr,
        cst_create_date,
        row_number() over (partition by cst_id order by cst_create_date desc) as flag_last,
        'CRM' as dwh_source_system,
        now() as dwh_create_date
    from {{ source('bronze', 'crm_cust_info') }}
    where cst_id is not null
)
select
    cst_id,
    cst_key,
    cst_firstname,
    cst_lastname,
    cst_marital_status,
    cst_gndr,
    cst_create_date,
    dwh_source_system,
    dwh_create_date
from ranked
where flag_last = 1