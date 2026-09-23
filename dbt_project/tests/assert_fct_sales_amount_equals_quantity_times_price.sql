-- assert_fct_sales_amount_equals_quantity_times_price.sql
-- Business rule: sales_amount should equal sales_quantity * unit_price (within rounding tolerance)
-- Excludes rows where sales_quantity or unit_price is null
-- Returns 0 rows if the assertion passes

select
    sales_key,
    sales_order_number,
    sales_amount,
    sales_quantity,
    unit_price,
    (sales_quantity * unit_price) as calculated_amount,
    abs(sales_amount - (sales_quantity * unit_price)) as diff
from {{ ref('fct_sales') }}
where sales_quantity is not null
  and unit_price is not null
  and abs(sales_amount - (sales_quantity * unit_price)) > 0.01