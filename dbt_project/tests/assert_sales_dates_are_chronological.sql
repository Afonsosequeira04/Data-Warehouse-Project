-- assert_sales_dates_are_chronological.sql
-- Business rule: order_date <= ship_date AND order_date <= due_date when all three dates exist
-- Returns 0 rows if the assertion passes

select
    sales_key,
    sales_order_number,
    order_date,
    ship_date,
    due_date
from {{ ref('fct_sales') }}
where order_date is not null
  and ship_date is not null
  and due_date is not null
  and (order_date > ship_date or order_date > due_date)