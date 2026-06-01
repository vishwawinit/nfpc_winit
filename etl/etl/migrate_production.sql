-- NFPC Reports — Production DB Migration
-- Run this on the PostgreSQL reporting DB BEFORE re-running the ETL.
-- All statements use IF NOT EXISTS / IF EXISTS so they are safe to re-run.

-- ============================================================
-- FIX 1: dim_route — add missing column
-- ============================================================
ALTER TABLE dim_route ADD COLUMN IF NOT EXISTS has_active_assignment BOOLEAN DEFAULT false;

-- ============================================================
-- FIX 2: dim_item — add missing columns
-- ============================================================
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS alt_name        VARCHAR(200);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS arabic_name     VARCHAR(200);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS sales_org_code  VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS agency_code     VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS agency_name     VARCHAR(200);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS pack_size_code  VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS flavor_code     VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS flavor_name     VARCHAR(200);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS item_type       VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS classification  VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS size            VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS order_category  VARCHAR(50);
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS case_conversion FLOAT;
ALTER TABLE dim_item ADD COLUMN IF NOT EXISTS pc_conversion   FLOAT;

-- ============================================================
-- FIX 3: rpt_sales_detail — add missing column
-- ============================================================
ALTER TABLE rpt_sales_detail ADD COLUMN IF NOT EXISTS trx_status INT;

-- ============================================================
-- FIX 4: rpt_eot — add missing columns (added later in extract.py)
-- ============================================================
ALTER TABLE rpt_eot ADD COLUMN IF NOT EXISTS route_start_datetime TIMESTAMP;
ALTER TABLE rpt_eot ADD COLUMN IF NOT EXISTS unload_datetime      TIMESTAMP;
ALTER TABLE rpt_eot ADD COLUMN IF NOT EXISTS eot_status           VARCHAR(50);

-- ============================================================
-- FIX 5: rpt_route_sales_by_item_customer — table was never in schema.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS rpt_route_sales_by_item_customer (
    id               SERIAL PRIMARY KEY,
    route_code       VARCHAR(50),
    user_code        VARCHAR(50),
    customer_code    VARCHAR(50),
    item_code        VARCHAR(50),
    date             DATE,
    total_qty        FLOAT,
    total_gr_qty     FLOAT,
    total_damage_qty FLOAT,
    total_expiry_qty FLOAT,
    total_sales      FLOAT,
    total_gr_sales   FLOAT,
    total_damage_sales  FLOAT,
    total_expiry_sales  FLOAT
);
CREATE INDEX IF NOT EXISTS idx_rsic_date       ON rpt_route_sales_by_item_customer(date);
CREATE INDEX IF NOT EXISTS idx_rsic_route_date ON rpt_route_sales_by_item_customer(route_code, date);
CREATE INDEX IF NOT EXISTS idx_rsic_user_date  ON rpt_route_sales_by_item_customer(user_code, date);
CREATE INDEX IF NOT EXISTS idx_rsic_item_date  ON rpt_route_sales_by_item_customer(item_code, date);

-- ============================================================
-- FIX 6: rpt_targets — recreate cleanly if missing
-- ============================================================
CREATE TABLE IF NOT EXISTS rpt_targets (
    target_id      BIGINT PRIMARY KEY,
    time_frame     VARCHAR(1),
    start_date     DATE,
    end_date       DATE,
    year           INT,
    month          INT,
    salesman_code  VARCHAR(50),
    salesman_name  VARCHAR(200),
    route_code     VARCHAR(50),
    route_name     VARCHAR(100),
    sales_org_code VARCHAR(50),
    item_key       VARCHAR(50),
    item_name      VARCHAR(200),
    customer_key   VARCHAR(50),
    amount         NUMERIC,
    quantity       FLOAT,
    is_active      BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_tgt_salesman ON rpt_targets(salesman_code);
CREATE INDEX IF NOT EXISTS idx_tgt_route    ON rpt_targets(route_code);
CREATE INDEX IF NOT EXISTS idx_tgt_dates    ON rpt_targets(start_date, end_date);
