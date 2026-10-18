-- =============================================================================
-- DataMind: reproducible Snowflake setup (PS1)
-- =============================================================================
-- Creates everything the DataMind backend needs, with least privilege:
--   * an X-Small warehouse that suspends itself after 60 s idle
--   * database DATAMIND, schema PUBLIC, and the synthetic SALES sample table
--   * a read-only role DATAMIND_READONLY (USAGE + SELECT only)
--   * a service user DATAMIND_SVC that authenticates with a key pair
--
-- HOW TO RUN: open a Snowsight worksheet and run the sections in order.
-- Sections 1-4 need an administrator role (ACCOUNTADMIN, or SYSADMIN for
-- objects plus SECURITYADMIN/USERADMIN for roles and users). The application
-- itself never runs this file and never uses these roles.
--
-- SAFETY
--   * No account identifiers, passwords or keys are stored here. Section 5 uses
--     a placeholder that you replace with your PUBLIC key only.
--   * Never paste a PRIVATE key into Snowflake, this file, or chat.
--   * Every statement is idempotent (IF NOT EXISTS / guarded INSERT), so the
--     script can be re-run without duplicating rows.
--   * Only USAGE and SELECT are granted to the app role. No OWNERSHIP, no
--     write privileges, no ACCOUNTADMIN for the app.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Warehouse with cost controls            (admin: SYSADMIN or ACCOUNTADMIN)
-- -----------------------------------------------------------------------------
USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS DATAMIND_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60            -- seconds idle before suspending (stops credit use)
  AUTO_RESUME = TRUE           -- wakes automatically on the next query
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'DataMind read-only query warehouse';


-- -----------------------------------------------------------------------------
-- 2. Database, schema and synthetic sample data   (admin: SYSADMIN)
-- -----------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS DATAMIND;
CREATE SCHEMA IF NOT EXISTS DATAMIND.PUBLIC;

-- Same 6 synthetic rows as backend/app/database.py (written by the DataMind team;
-- no real or third-party data). Electronics revenue 166000, Furniture 36000.
CREATE TABLE IF NOT EXISTS DATAMIND.PUBLIC.SALES (
  ORDER_ID   INTEGER PRIMARY KEY,
  PRODUCT    VARCHAR NOT NULL,
  CATEGORY   VARCHAR NOT NULL,
  QUANTITY   INTEGER NOT NULL,
  UNIT_PRICE DOUBLE  NOT NULL,
  YEAR       INTEGER NOT NULL
);

-- MERGE inserts only the rows that are missing, so re-running never duplicates.
MERGE INTO DATAMIND.PUBLIC.SALES t
USING (
  SELECT * FROM VALUES
    (1, 'Laptop',     'Electronics', 2, 50000.0, 2024),
    (2, 'Smartphone', 'Electronics', 3, 20000.0, 2025),
    (3, 'Headphones', 'Electronics', 4,  1500.0, 2025),
    (4, 'Desk',       'Furniture',   2, 12000.0, 2024),
    (5, 'Chair',      'Furniture',   4,  2500.0, 2025),
    (6, 'Lamp',       'Furniture',   2,  1000.0, 2024)
    AS s (ORDER_ID, PRODUCT, CATEGORY, QUANTITY, UNIT_PRICE, YEAR)
) s
ON t.ORDER_ID = s.ORDER_ID
WHEN NOT MATCHED THEN INSERT (ORDER_ID, PRODUCT, CATEGORY, QUANTITY, UNIT_PRICE, YEAR)
  VALUES (s.ORDER_ID, s.PRODUCT, s.CATEGORY, s.QUANTITY, s.UNIT_PRICE, s.YEAR);


-- -----------------------------------------------------------------------------
-- 3. Read-only application role             (admin: SECURITYADMIN or USERADMIN)
-- -----------------------------------------------------------------------------
USE ROLE SECURITYADMIN;

CREATE ROLE IF NOT EXISTS DATAMIND_READONLY
  COMMENT = 'DataMind app: read-only access to DATAMIND.PUBLIC';

-- Exactly the privileges the app needs: nothing that can write or change objects.
GRANT USAGE  ON WAREHOUSE DATAMIND_WH                      TO ROLE DATAMIND_READONLY;
GRANT USAGE  ON DATABASE  DATAMIND                         TO ROLE DATAMIND_READONLY;
GRANT USAGE  ON SCHEMA    DATAMIND.PUBLIC                  TO ROLE DATAMIND_READONLY;
GRANT SELECT ON ALL TABLES    IN SCHEMA DATAMIND.PUBLIC    TO ROLE DATAMIND_READONLY;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND.PUBLIC    TO ROLE DATAMIND_READONLY;


-- -----------------------------------------------------------------------------
-- 4. Service user (key-pair only)            (admin: SECURITYADMIN or USERADMIN)
-- -----------------------------------------------------------------------------
-- TYPE = SERVICE users cannot log in with a password, which is what we want.
CREATE USER IF NOT EXISTS DATAMIND_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = DATAMIND_READONLY
  DEFAULT_WAREHOUSE = DATAMIND_WH
  DEFAULT_NAMESPACE = DATAMIND.PUBLIC
  COMMENT = 'DataMind backend service user';

GRANT ROLE DATAMIND_READONLY TO USER DATAMIND_SVC;


-- -----------------------------------------------------------------------------
-- 5. Register the PUBLIC key                 (admin: SECURITYADMIN or the user owner)
-- -----------------------------------------------------------------------------
-- Generate the key pair locally (the private key stays on your machine,
-- outside the repository):
--   .\.venv\Scripts\python.exe backend\scripts\generate_snowflake_keypair.py
-- The script prints a ready-to-run ALTER USER line containing only the PUBLIC
-- key as one base64 line (no BEGIN/END lines, no line breaks). Paste it in place
-- of the placeholder below, then uncomment and run it.
--
-- ALTER USER DATAMIND_SVC SET RSA_PUBLIC_KEY = '<PASTE_PUBLIC_KEY_BASE64_HERE>';
--
-- Verify: RSA_PUBLIC_KEY_FP must equal the SHA256 fingerprint of your key.
-- DESC USER DATAMIND_SVC;


-- -----------------------------------------------------------------------------
-- 6. Verification (run as the app role; read-only)
-- -----------------------------------------------------------------------------
USE ROLE DATAMIND_READONLY;
USE WAREHOUSE DATAMIND_WH;
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE();
SELECT CATEGORY, SUM(QUANTITY * UNIT_PRICE) AS REVENUE
FROM DATAMIND.PUBLIC.SALES GROUP BY CATEGORY ORDER BY CATEGORY;
-- Expected: Electronics 166000, Furniture 36000.

-- This MUST fail with an insufficient-privileges error (proves the role is read-only):
-- DELETE FROM DATAMIND.PUBLIC.SALES WHERE ORDER_ID = 1;


-- -----------------------------------------------------------------------------
-- 7. Cost control when you are done for the day
-- -----------------------------------------------------------------------------
-- ALTER WAREHOUSE DATAMIND_WH SUSPEND;
-- Optional hard cap (admin: ACCOUNTADMIN): a resource monitor that suspends the
-- warehouse when its credit quota is used up.
-- CREATE RESOURCE MONITOR IF NOT EXISTS DATAMIND_MONITOR WITH CREDIT_QUOTA = 10
--   TRIGGERS ON 90 PERCENT DO SUSPEND ON 100 PERCENT DO SUSPEND_IMMEDIATE;
-- ALTER WAREHOUSE DATAMIND_WH SET RESOURCE_MONITOR = DATAMIND_MONITOR;


-- -----------------------------------------------------------------------------
-- 8. OPTIONAL second dataset: Snowflake sample data (TPC-H)
-- -----------------------------------------------------------------------------
-- SNOWFLAKE_SAMPLE_DATA is a shared database. In the DataMind team account the
-- read-only role could already read SNOWFLAKE_SAMPLE_DATA.TPCH_SF1 (checked on
-- 2026-10-18 with SELECT COUNT(*) ... REGION), most likely through the PUBLIC
-- role, so NO extra grant was needed there. If your account cannot read it,
-- the narrowest change is the statement below. It requires explicit approval
-- by the account owner and is therefore commented out:
--
-- USE ROLE ACCOUNTADMIN;
-- GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE DATAMIND_READONLY;
--
-- To point DataMind at TPC-H, change configuration only (no code changes):
--   SNOWFLAKE_DATABASE=SNOWFLAKE_SAMPLE_DATA
--   SNOWFLAKE_SCHEMA=TPCH_SF1
-- TPC-H has no open licence: query it in your account; never copy it into the repo.
