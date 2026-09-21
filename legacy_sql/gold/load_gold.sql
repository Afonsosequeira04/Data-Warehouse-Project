-- =============================================================
-- Gold Layer Load Script
-- =============================================================
-- Script Purpose:
--     Executes the Gold layer DDL. Because all Gold objects are
--     views (not tables), there is no physical data to load.
--     The views are defined in ddl_gold.sql and materialised
--     on query.
--
--     This script simply runs the DDL and then verifies
--     row counts so you have immediate feedback.
-- =============================================================

\echo 'Loading Gold layer...'

\i legacy_sql/gold/ddl_gold.sql

\echo ''
\echo 'Gold layer views created.'
\echo ''
\echo 'Row counts:'

SELECT 'gold.dim_customers' AS table_name, count(*) FROM gold.dim_customers
UNION ALL
SELECT 'gold.dim_products', count(*) FROM gold.dim_products
UNION ALL
SELECT 'gold.fact_sales', count(*) FROM gold.fact_sales;
