-- =============================================================
-- DDL Script: Create Gold Layer (Views)
-- =============================================================
-- Script Purpose:
--     Creates the business-ready 'gold' schema objects: star
--     schema dimension views and a fact view.
--
--     All objects are VIEWS (no partitioned tables in this phase).
--     The partitioning strategy is documented but not implemented
--     until the Gold layer is materialized (Fase 3+).
--
-- Partitioning decision (documented, not yet implemented):
--     gold.fact_sales will be RANGE partitioned by sls_order_dt
--     (monthly) when it becomes a physical table. See the comment
--     block above the view definition for details.
-- =============================================================


-- ---------------------------------------------------------
-- gold.dim_customers
-- ---------------------------------------------------------
-- Merge of CRM + ERP customer data.
-- Surrogate key: customer_key (auto-incrementing integer)
--    Join crm_cust_info.cst_id with erp_cust_az12.cid + erp_loc_a101.cid
--    (Silver-level cleaning normalizes cid values, e.g. strips
--     'NAS' prefix and dashes, and standardizes country names,
--     so the keys align 1:1 between CRM and ERP).
-- Conflict resolution for gender: CRM takes priority, ERP gen
--    fills in where CRM is null.
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW gold.dim_customers AS
SELECT
    ROW_NUMBER() OVER (ORDER BY COALESCE(c.cst_id, 0)) AS customer_key,
    COALESCE(c.cst_key, e.cid)                         AS customer_id,
    c.cst_id                                           AS crm_customer_id,
    e.cid                                              AS erp_customer_id,
    TRIM(COALESCE(c.cst_firstname, '')) || ' ' ||
    TRIM(COALESCE(c.cst_lastname, ''))                 AS customer_full_name,
    COALESCE(c.cst_firstname, '')                      AS customer_first_name,
    COALESCE(c.cst_lastname, '')                       AS customer_last_name,
    COALESCE(c.cst_marital_status, 'n/a')              AS marital_status,
    COALESCE(c.cst_gndr, e.gen, 'n/a')                 AS gender,
    e.bdate                                            AS birth_date,
    l.cntry                                            AS country,
    c.cst_create_date                                  AS customer_create_date,
    c.dwh_source_system                                AS crm_source_system,
    e.dwh_source_system                                AS erp_source_system,
    c.dwh_create_date                                  AS dwh_create_date
FROM silver.crm_cust_info c
FULL OUTER JOIN silver.erp_cust_az12 e ON c.cst_key = e.cid
LEFT JOIN silver.erp_loc_a101 l ON e.cid = l.cid;


-- ---------------------------------------------------------
-- gold.dim_products
-- ---------------------------------------------------------
-- Merge of CRM + ERP product/category data.
-- Surrogate key: product_key (auto-incrementing integer)
--    crm_prd_info provides the product identity (prd_id, prd_key)
--    erp_px_cat_g1v2 provides the category/subcategory
--    (cat_id in CRM = id in ERP, already cleaned by Silver).
--
--    prd_key is NOT unique in crm_prd_info (same product appears
--    multiple times with different start/end dates as pricing changes
--    over time). To produce one row per product, we keep only the
--    latest version (by prd_start_dt DESC) per prd_key.
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW gold.dim_products AS
SELECT
    ROW_NUMBER() OVER (ORDER BY prd_id) AS product_key,
    prd_key                             AS product_key_business,
    prd_id                              AS crm_product_id,
    cat_id                              AS category_id,
    prd_nm                              AS product_name,
    prd_cost                            AS product_cost,
    prd_line                            AS product_line,
    prd_start_dt                        AS product_start_date,
    prd_end_dt                          AS product_end_date,
    COALESCE(cat, 'n/a')                AS category,
    COALESCE(subcat, 'n/a')             AS subcategory,
    COALESCE(maintenance, 'n/a')        AS maintenance_required
FROM (
    SELECT
        c.prd_id, c.prd_key, c.cat_id, c.prd_nm, c.prd_cost,
        c.prd_line, c.prd_start_dt, c.prd_end_dt,
        p.cat, p.subcat, p.maintenance,
        ROW_NUMBER() OVER (
            PARTITION BY c.prd_key ORDER BY c.prd_start_dt DESC
        ) AS rn
    FROM silver.crm_prd_info c
    LEFT JOIN silver.erp_px_cat_g1v2 p ON c.cat_id = p.id
) latest_products
WHERE rn = 1;


-- ---------------------------------------------------------
-- gold.fact_sales
-- ---------------------------------------------------------
-- Sales fact table joining crm_sales_details to the two
-- dimensions above via surrogate keys.
--
-- PARTITIONING STRATEGY (documented, not yet implemented):
--     When fact_sales is materialized as a physical table,
--     it will be RANGE partitioned by sls_order_dt (month/year).
--     Example:
--         CREATE TABLE gold.fact_sales ( ... ) PARTITION BY RANGE (sls_order_dt);
--         CREATE TABLE gold.fact_sales_y2010m12 PARTITION OF gold.fact_sales
--             FOR VALUES FROM ('2010-12-01') TO ('2011-01-01');
--
--     This key is chosen because:
--       - Date-based partitioning is natural for time-series query loads
--       - sls_order_dt is already cleaned to DATE in Silver
--     - Most analytical queries filter or aggregate by date
--     Index the surrogate FK columns (customer_key, product_key)
--       locally within each partition for join performance.
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW gold.fact_sales AS
SELECT
    ROW_NUMBER() OVER (ORDER BY s.sls_ord_num)        AS sales_key,
    s.sls_ord_num                                     AS sales_order_number,
    dc.customer_key                                   AS customer_key,
    dp.product_key                                    AS product_key,
    s.sls_cust_id                                     AS erp_customer_ref,
    s.sls_prd_key                                     AS product_business_key,
    s.sls_order_dt                                    AS order_date,
    s.sls_ship_dt                                     AS ship_date,
    s.sls_due_dt                                      AS due_date,
    s.sls_sales                                       AS sales_amount,
    s.sls_quantity                                    AS sales_quantity,
    s.sls_price                                       AS unit_price,
    s.dwh_create_date                                 AS dwh_create_date
FROM silver.crm_sales_details s
LEFT JOIN gold.dim_customers dc ON s.sls_cust_id = dc.crm_customer_id
LEFT JOIN gold.dim_products dp   ON s.sls_prd_key = dp.product_key_business;
