-- =============================================================
-- Procedure: silver.load_silver()
-- =============================================================
-- Purpose:
--     Reads from bronze.*, cleans/standardizes the data, and
--     loads it into silver.* using TRUNCATE + INSERT per table,
--     with per-table error handling so one failure doesn't stop
--     the rest of the batch.
--
-- Requires: ddl_silver.sql must already be run (creates the
--           silver schema and tables this procedure loads into).
--
-- Cleaning rules applied:
--     crm_cust_info      -> dedupe by cst_id (keep latest by
--                           cst_create_date), trim names,
--                           standardize marital status/gender
--     crm_prd_info       -> split prd_key into cat_id + prd_key,
--                           null cost -> 0, standardize prd_line,
--                           recompute prd_end_dt
--     crm_sales_details  -> int (YYYYMMDD) -> DATE with
--                           0/invalid -> NULL, recompute
--                           sls_sales/sls_price where missing,
--                           negative, or inconsistent with qty*price
--     erp_cust_az12      -> strip 'NAS' prefix from cid, null out
--                           future bdates, standardize gen
--     erp_loc_a101       -> strip dashes from cid, standardize
--                           country codes
--     erp_px_cat_g1v2    -> already clean, loaded as-is
--
-- Note: dwh_source_system and dwh_create_date are intentionally
--       left out of every INSERT column list below -- they're
--       populated by the column defaults defined in ddl_silver.sql.
-- =============================================================

CREATE OR REPLACE PROCEDURE silver.load_silver()
LANGUAGE plpgsql
AS $$
DECLARE
    batch_start_time TIMESTAMP;
    batch_end_time   TIMESTAMP;
    start_time       TIMESTAMP;
    end_time         TIMESTAMP;
BEGIN
    batch_start_time := clock_timestamp();
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Loading Silver Layer';
    RAISE NOTICE '================================================';

    -- ------------------------------------------------------------------
    -- silver.crm_cust_info
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.crm_cust_info';
        TRUNCATE TABLE silver.crm_cust_info;

        RAISE NOTICE '>> Inserting Data Into: silver.crm_cust_info';
        INSERT INTO silver.crm_cust_info (
            cst_id, cst_key, cst_firstname, cst_lastname,
            cst_marital_status, cst_gndr, cst_create_date
        )
        SELECT
            cst_id,
            cst_key,
            TRIM(cst_firstname) AS cst_firstname,
            TRIM(cst_lastname)  AS cst_lastname,
            CASE UPPER(TRIM(cst_marital_status))
                WHEN 'S' THEN 'Single'
                WHEN 'M' THEN 'Married'
                ELSE 'n/a'
            END AS cst_marital_status,
            CASE UPPER(TRIM(cst_gndr))
                WHEN 'F' THEN 'Female'
                WHEN 'M' THEN 'Male'
                ELSE 'n/a'
            END AS cst_gndr,
            cst_create_date
        FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY cst_id ORDER BY cst_create_date DESC) AS flag_last
            FROM bronze.crm_cust_info
            WHERE cst_id IS NOT NULL
        ) t
        WHERE flag_last = 1;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.crm_cust_info: %', SQLERRM;
    END;

    -- ------------------------------------------------------------------
    -- silver.crm_prd_info
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.crm_prd_info';
        TRUNCATE TABLE silver.crm_prd_info;

        RAISE NOTICE '>> Inserting Data Into: silver.crm_prd_info';
        INSERT INTO silver.crm_prd_info (
            prd_id, cat_id, prd_key, prd_nm, prd_cost, prd_line, prd_start_dt, prd_end_dt
        )
        SELECT
            prd_id,
            REPLACE(SUBSTRING(prd_key FROM 1 FOR 5), '-', '_') AS cat_id,
            SUBSTRING(prd_key FROM 7)                          AS prd_key,
            prd_nm,
            COALESCE(prd_cost, 0) AS prd_cost,
            CASE UPPER(TRIM(prd_line))
                WHEN 'M' THEN 'Mountain'
                WHEN 'R' THEN 'Road'
                WHEN 'S' THEN 'Other Sales'
                WHEN 'T' THEN 'Touring'
                ELSE 'n/a'
            END AS prd_line,
            prd_start_dt,
            (LEAD(prd_start_dt) OVER (PARTITION BY prd_key ORDER BY prd_start_dt) - 1)::DATE AS prd_end_dt
        FROM bronze.crm_prd_info;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.crm_prd_info: %', SQLERRM;
    END;

    -- ------------------------------------------------------------------
    -- silver.crm_sales_details
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.crm_sales_details';
        TRUNCATE TABLE silver.crm_sales_details;

        RAISE NOTICE '>> Inserting Data Into: silver.crm_sales_details';
        INSERT INTO silver.crm_sales_details (
            sls_ord_num, sls_prd_key, sls_cust_id,
            sls_order_dt, sls_ship_dt, sls_due_dt,
            sls_sales, sls_quantity, sls_price
        )
        SELECT
            sls_ord_num,
            sls_prd_key,
            sls_cust_id,
            CASE WHEN sls_order_dt = 0 OR LENGTH(sls_order_dt::TEXT) != 8 THEN NULL
                 ELSE TO_DATE(sls_order_dt::TEXT, 'YYYYMMDD') END AS sls_order_dt,
            CASE WHEN sls_ship_dt = 0 OR LENGTH(sls_ship_dt::TEXT) != 8 THEN NULL
                 ELSE TO_DATE(sls_ship_dt::TEXT, 'YYYYMMDD') END AS sls_ship_dt,
            CASE WHEN sls_due_dt = 0 OR LENGTH(sls_due_dt::TEXT) != 8 THEN NULL
                 ELSE TO_DATE(sls_due_dt::TEXT, 'YYYYMMDD') END AS sls_due_dt,
            CASE WHEN sls_sales IS NULL OR sls_sales <= 0
                      OR sls_sales != sls_quantity * ABS(sls_price)
                 THEN sls_quantity * ABS(sls_price)
                 ELSE sls_sales END AS sls_sales,
            sls_quantity,
            CASE WHEN sls_price IS NULL OR sls_price <= 0
                 THEN sls_sales / NULLIF(sls_quantity, 0)
                 ELSE sls_price END AS sls_price
        FROM bronze.crm_sales_details;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.crm_sales_details: %', SQLERRM;
    END;

    -- ------------------------------------------------------------------
    -- silver.erp_cust_az12
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.erp_cust_az12';
        TRUNCATE TABLE silver.erp_cust_az12;

        RAISE NOTICE '>> Inserting Data Into: silver.erp_cust_az12';
        INSERT INTO silver.erp_cust_az12 (cid, bdate, gen)
        SELECT
            CASE WHEN cid LIKE 'NAS%' THEN SUBSTRING(cid FROM 4) ELSE cid END AS cid,
            CASE WHEN bdate > CURRENT_DATE THEN NULL ELSE bdate END AS bdate,
            CASE
                WHEN UPPER(TRIM(gen)) IN ('F', 'FEMALE') THEN 'Female'
                WHEN UPPER(TRIM(gen)) IN ('M', 'MALE')   THEN 'Male'
                ELSE 'n/a'
            END AS gen
        FROM bronze.erp_cust_az12;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.erp_cust_az12: %', SQLERRM;
    END;

    -- ------------------------------------------------------------------
    -- silver.erp_loc_a101
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.erp_loc_a101';
        TRUNCATE TABLE silver.erp_loc_a101;

        RAISE NOTICE '>> Inserting Data Into: silver.erp_loc_a101';
        INSERT INTO silver.erp_loc_a101 (cid, cntry)
        SELECT
            REPLACE(cid, '-', '') AS cid,
            CASE
                WHEN TRIM(cntry) = 'DE'          THEN 'Germany'
                WHEN TRIM(cntry) IN ('US', 'USA') THEN 'United States'
                WHEN TRIM(cntry) = '' OR cntry IS NULL THEN 'n/a'
                ELSE TRIM(cntry)
            END AS cntry
        FROM bronze.erp_loc_a101;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.erp_loc_a101: %', SQLERRM;
    END;

    -- ------------------------------------------------------------------
    -- silver.erp_px_cat_g1v2
    -- ------------------------------------------------------------------
    BEGIN
        start_time := clock_timestamp();
        RAISE NOTICE '>> Truncating Table: silver.erp_px_cat_g1v2';
        TRUNCATE TABLE silver.erp_px_cat_g1v2;

        RAISE NOTICE '>> Inserting Data Into: silver.erp_px_cat_g1v2';
        INSERT INTO silver.erp_px_cat_g1v2 (id, cat, subcat, maintenance)
        SELECT id, cat, subcat, maintenance
        FROM bronze.erp_px_cat_g1v2;

        end_time := clock_timestamp();
        RAISE NOTICE '>> Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (end_time - start_time))::NUMERIC, 2);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Error loading silver.erp_px_cat_g1v2: %', SQLERRM;
    END;

    batch_end_time := clock_timestamp();
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Silver Layer Load Complete';
    RAISE NOTICE '   Total Load Duration: % seconds', ROUND(EXTRACT(EPOCH FROM (batch_end_time - batch_start_time))::NUMERIC, 2);
    RAISE NOTICE '================================================';

EXCEPTION WHEN OTHERS THEN
    RAISE WARNING '================================================';
    RAISE WARNING 'ERROR OCCURRED DURING LOADING SILVER LAYER';
    RAISE WARNING 'Error Message: %', SQLERRM;
    RAISE WARNING '================================================';
END;
$$;

-- =============================================================
-- Run the load
-- =============================================================
CALL silver.load_silver();
