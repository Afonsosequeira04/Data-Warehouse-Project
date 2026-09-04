-- =============================================================
-- Create Database and Schemas: 'data_warehouse_project'
-- =============================================================
-- Script Purpose:
--     This script creates the 'data_warehouse_project' database.
--     If the database already exists, it is dropped and recreated.
--     Any other active connections to the database are terminated
--     first so the drop doesn't fail.
--     The script then sets up three schemas following the
--     medallion architecture: 'bronze', 'silver', and 'gold'.
--
-- WARNING:
--     Running this script will drop the entire 'data_warehouse_project'
--     database if it exists. All data in the database will be
--     permanently deleted. Proceed with caution and ensure you have
--     proper backups before running this script.
-- =============================================================

-- Terminate any other active connections to the database, if it exists
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'data_warehouse_project' AND pid <> pg_backend_pid();

-- Drop and recreate the database
DROP DATABASE IF EXISTS data_warehouse_project;
CREATE DATABASE data_warehouse_project;

-- Connect to the new database before creating schemas
\c data_warehouse_project

-- Create Schemas
CREATE SCHEMA bronze;
CREATE SCHEMA silver;
CREATE SCHEMA gold;
