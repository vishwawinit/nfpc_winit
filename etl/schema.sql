-- NFPC Reports - PostgreSQL Reporting Schema
-- Denormalized flat tables optimized for report queries

-- ============================================================
-- DIMENSION LOOKUP TABLES (small, full copy from MSSQL)
-- ============================================================

CREATE TABLE IF NOT EXISTS dim_sales_org (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    country_code VARCHAR(50),
    currency_code VARCHAR(50),
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_route (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    sales_org_code VARCHAR(50),
    route_type VARCHAR(100),
    area_code VARCHAR(50),
    sub_area_code VARCHAR(50),
    route_cat_code VARCHAR(50),
    salesman_code VARCHAR(50),
    wh_code VARCHAR(50),
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_user (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    sales_org_code VARCHAR(50),
    route_code VARCHAR(100),
    depot_code VARCHAR(50),
    reports_to VARCHAR(50),
    user_type VARCHAR(50),
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_customer (
    code VARCHAR(50),
    sales_org_code VARCHAR(50),
    name VARCHAR(200),
    channel_code VARCHAR(50),
    channel_name VARCHAR(200),
    sub_channel_code VARCHAR(50),
    sub_channel_name VARCHAR(200),
    customer_group VARCHAR(50),
    customer_type VARCHAR(50),
    payment_type VARCHAR(50),
    city_code VARCHAR(200),
    city_name VARCHAR(200),
    region_code VARCHAR(50),
    region_name VARCHAR(200),
    country_code VARCHAR(50),
    country_name VARCHAR(200),
    latitude FLOAT,
    longitude FLOAT,
    is_active BOOLEAN,
    PRIMARY KEY (code, sales_org_code)
);

CREATE TABLE IF NOT EXISTS dim_item (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    base_uom VARCHAR(50),
    brand_code VARCHAR(50),
    brand_name VARCHAR(200),
    sub_brand_code VARCHAR(50),
    sub_brand_name VARCHAR(200),
    category_code VARCHAR(50),
    category_name VARCHAR(200),
    sub_category_code VARCHAR(50),
    sub_category_name VARCHAR(200),
    pack_type_code VARCHAR(50),
    pack_type_name VARCHAR(200),
    segment_code VARCHAR(50),
    segment_name VARCHAR(200),
    liter FLOAT,
    liter_per_unit FLOAT,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_channel (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS dim_country (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS dim_region (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    country_code VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS dim_city (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    region_code VARCHAR(50)
);

-- ============================================================
-- FACT TABLES (Denormalized, flat)
-- ============================================================

-- CORE: One row per transaction line with ALL dimensions pre-joined
DROP TABLE IF EXISTS rpt_sales_detail;
CREATE TABLE rpt_sales_detail (
    trx_code VARCHAR(50),
    line_no INT,
    trx_date DATE,
    trip_date DATE,
    trx_type INT,
    payment_type INT,
    -- User
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    sales_org_code VARCHAR(50),
    sales_org_name VARCHAR(200),
    depot_code VARCHAR(50),
    -- Route
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    route_type VARCHAR(100),
    area_code VARCHAR(50),
    sub_area_code VARCHAR(50),
    -- Customer
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    channel_code VARCHAR(50),
    channel_name VARCHAR(200),
    sub_channel_code VARCHAR(50),
    sub_channel_name VARCHAR(200),
    customer_group VARCHAR(50),
    customer_type VARCHAR(50),
    -- Geography
    country_code VARCHAR(50),
    country_name VARCHAR(200),
    region_code VARCHAR(50),
    region_name VARCHAR(200),
    city_code VARCHAR(200),
    city_name VARCHAR(200),
    -- Item
    item_code VARCHAR(50),
    item_name VARCHAR(200),
    brand_code VARCHAR(50),
    brand_name VARCHAR(200),
    category_code VARCHAR(50),
    category_name VARCHAR(200),
    sub_brand_code VARCHAR(50),
    sub_brand_name VARCHAR(200),
    pack_type_code VARCHAR(50),
    pack_type_name VARCHAR(200),
    segment_code VARCHAR(50),
    segment_name VARCHAR(200),
    base_uom VARCHAR(50),
    -- Measures
    qty_cases FLOAT,
    qty_pieces FLOAT,
    qty_volume FLOAT,
    base_price FLOAT,
    net_amount FLOAT,
    discount_amount FLOAT,
    tax_amount FLOAT,
    gross_amount FLOAT,
    -- Invoice
    invoice_number VARCHAR(50),
    -- Timestamps
    created_on TIMESTAMP,
    PRIMARY KEY (trx_code, line_no)
);

-- CORE: Pre-aggregated daily sales from tblRouteSalesSummaryByItemCustomer
DROP TABLE IF EXISTS rpt_daily_sales_summary;
CREATE TABLE rpt_daily_sales_summary (
    id SERIAL PRIMARY KEY,
    date DATE,
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    sales_org_code VARCHAR(50),
    sales_org_name VARCHAR(200),
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    channel_code VARCHAR(50),
    channel_name VARCHAR(200),
    item_code VARCHAR(50),
    item_name VARCHAR(200),
    brand_code VARCHAR(50),
    brand_name VARCHAR(200),
    category_code VARCHAR(50),
    category_name VARCHAR(200),
    -- Measures
    total_qty FLOAT,
    total_sales FLOAT,
    total_gr_qty FLOAT,
    total_gr_sales FLOAT,
    total_damage_qty FLOAT,
    total_damage_sales FLOAT,
    total_expiry_qty FLOAT,
    total_expiry_sales FLOAT
);

-- Collections flat
DROP TABLE IF EXISTS rpt_collections;
CREATE TABLE rpt_collections (
    receipt_id BIGINT PRIMARY KEY,
    receipt_number VARCHAR(50),
    receipt_date DATE,
    trip_date DATE,
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    sales_org_code VARCHAR(50),
    sales_org_name VARCHAR(200),
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    amount FLOAT,
    settled_amount FLOAT,
    payment_type VARCHAR(20),
    payment_status INT,
    currency_code VARCHAR(50)
);

-- Customer visits flat
DROP TABLE IF EXISTS rpt_customer_visits;
CREATE TABLE rpt_customer_visits (
    visit_id VARCHAR(50) PRIMARY KEY,
    date DATE,
    trip_date DATE,
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    sales_org_code VARCHAR(50),
    sales_org_name VARCHAR(200),
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    channel_name VARCHAR(200),
    city_name VARCHAR(200),
    region_name VARCHAR(200),
    arrival_time TIMESTAMP,
    out_time TIMESTAMP,
    total_time_mins INT,
    is_productive BOOLEAN,
    is_planned BOOLEAN,
    latitude FLOAT,
    longitude FLOAT,
    journey_code VARCHAR(50)
);

-- Journey/attendance flat
DROP TABLE IF EXISTS rpt_journeys;
CREATE TABLE rpt_journeys (
    journey_id INT PRIMARY KEY,
    journey_code VARCHAR(50),
    date DATE,
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    sales_org_code VARCHAR(50),
    start_time VARCHAR(50),
    end_time VARCHAR(50),
    vehicle_code VARCHAR(50)
);

-- Coverage summary flat (already denormalized in source)
DROP TABLE IF EXISTS rpt_coverage_summary;
CREATE TABLE rpt_coverage_summary (
    id INT PRIMARY KEY,
    visit_date DATE,
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    sales_org_code VARCHAR(50),
    scheduled_calls INT,
    total_actual_calls INT,
    planned_calls INT,
    unplanned_calls INT,
    selling_calls INT,
    planned_selling_calls INT
);

-- Sales + Collection summary per route/day
DROP TABLE IF EXISTS rpt_route_sales_collection;
CREATE TABLE rpt_route_sales_collection (
    id INT PRIMARY KEY,
    date DATE,
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    sales_org_code VARCHAR(50),
    total_sales FLOAT,
    total_collection FLOAT,
    total_sales_with_tax FLOAT,
    total_wastage FLOAT,
    target_amount FLOAT
);

-- Targets flat
DROP TABLE IF EXISTS rpt_targets;
CREATE TABLE rpt_targets (
    target_id BIGINT PRIMARY KEY,
    time_frame VARCHAR(1),
    start_date DATE,
    end_date DATE,
    year INT,
    month INT,
    salesman_code VARCHAR(50),
    salesman_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    sales_org_code VARCHAR(50),
    item_key VARCHAR(50),
    item_name VARCHAR(200),
    customer_key VARCHAR(50),
    amount NUMERIC,
    quantity FLOAT,
    is_active BOOLEAN
);

-- Outstanding/Pending invoices flat
DROP TABLE IF EXISTS rpt_outstanding;
CREATE TABLE rpt_outstanding (
    id INT PRIMARY KEY,
    trx_code VARCHAR(50),
    org_code VARCHAR(50),
    sales_org_name VARCHAR(200),
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    channel_name VARCHAR(200),
    trx_date DATE,
    due_date DATE,
    original_amount NUMERIC,
    balance_amount NUMERIC,
    pending_amount NUMERIC,
    collected_amount NUMERIC,
    days_overdue INT,
    aging_bucket VARCHAR(20),
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    currency_code VARCHAR(50)
);

-- EOT flat
DROP TABLE IF EXISTS rpt_eot;
CREATE TABLE rpt_eot (
    eot_id INT PRIMARY KEY,
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    route_code VARCHAR(50),
    route_name VARCHAR(100),
    sales_org_code VARCHAR(50),
    eot_type VARCHAR(20),
    eot_time TIMESTAMP,
    trip_date DATE
);

-- Daily Journey Plan flat
DROP TABLE IF EXISTS rpt_journey_plan;
CREATE TABLE rpt_journey_plan (
    id BIGINT PRIMARY KEY,
    date DATE,
    user_code VARCHAR(50),
    user_name VARCHAR(200),
    customer_code VARCHAR(50),
    customer_name VARCHAR(200),
    route_code VARCHAR(50),
    sequence INT,
    visit_status INT,
    sales_org_code VARCHAR(50)
);

-- Holidays reference
DROP TABLE IF EXISTS rpt_holidays;
CREATE TABLE rpt_holidays (
    holiday_id INT PRIMARY KEY,
    holiday_date DATE,
    name VARCHAR(200),
    year INT,
    sales_org_code VARCHAR(50)
);

-- ============================================================
-- INDEXES
-- ============================================================

-- rpt_sales_detail
CREATE INDEX idx_sd_date_org ON rpt_sales_detail(trx_date, sales_org_code);
CREATE INDEX idx_sd_route_date ON rpt_sales_detail(route_code, trx_date);
CREATE INDEX idx_sd_user_date ON rpt_sales_detail(user_code, trx_date);
CREATE INDEX idx_sd_item_date ON rpt_sales_detail(item_code, trx_date);
CREATE INDEX idx_sd_customer_date ON rpt_sales_detail(customer_code, trx_date);
CREATE INDEX idx_sd_trxtype ON rpt_sales_detail(trx_type);
CREATE INDEX idx_sd_brand ON rpt_sales_detail(brand_code, trx_date);

-- rpt_daily_sales_summary
CREATE INDEX idx_dss_date ON rpt_daily_sales_summary(date);
CREATE INDEX idx_dss_date_org ON rpt_daily_sales_summary(date, sales_org_code);
CREATE INDEX idx_dss_route_date ON rpt_daily_sales_summary(route_code, date);
CREATE INDEX idx_dss_user_date ON rpt_daily_sales_summary(user_code, date);
CREATE INDEX idx_dss_customer ON rpt_daily_sales_summary(customer_code, date);
CREATE INDEX idx_dss_item ON rpt_daily_sales_summary(item_code, date);
CREATE INDEX idx_dss_brand ON rpt_daily_sales_summary(brand_code, date);

-- rpt_collections
CREATE INDEX idx_coll_date ON rpt_collections(receipt_date);
CREATE INDEX idx_coll_user ON rpt_collections(user_code, receipt_date);
CREATE INDEX idx_coll_route ON rpt_collections(route_code, receipt_date);
CREATE INDEX idx_coll_org ON rpt_collections(sales_org_code, receipt_date);

-- rpt_customer_visits
CREATE INDEX idx_cv_date ON rpt_customer_visits(date);
CREATE INDEX idx_cv_user_date ON rpt_customer_visits(user_code, date);
CREATE INDEX idx_cv_route_date ON rpt_customer_visits(route_code, date);
CREATE INDEX idx_cv_customer ON rpt_customer_visits(customer_code, date);

-- rpt_coverage_summary
CREATE INDEX idx_cs_date ON rpt_coverage_summary(visit_date);
CREATE INDEX idx_cs_route ON rpt_coverage_summary(route_code, visit_date);
CREATE INDEX idx_cs_user ON rpt_coverage_summary(user_code, visit_date);

-- rpt_journeys
CREATE INDEX idx_j_date ON rpt_journeys(date);
CREATE INDEX idx_j_user ON rpt_journeys(user_code, date);

-- rpt_outstanding
CREATE INDEX idx_out_customer ON rpt_outstanding(customer_code);
CREATE INDEX idx_out_aging ON rpt_outstanding(aging_bucket);
CREATE INDEX idx_out_org ON rpt_outstanding(org_code);
CREATE INDEX idx_out_user ON rpt_outstanding(user_code);

-- rpt_eot
CREATE INDEX idx_eot_date ON rpt_eot(trip_date);
CREATE INDEX idx_eot_user ON rpt_eot(user_code, trip_date);

-- rpt_journey_plan
CREATE INDEX idx_jp_date ON rpt_journey_plan(date);
CREATE INDEX idx_jp_user ON rpt_journey_plan(user_code, date);

-- rpt_route_sales_collection
CREATE INDEX idx_rsc_date ON rpt_route_sales_collection(date);
CREATE INDEX idx_rsc_route ON rpt_route_sales_collection(route_code, date);

-- rpt_targets
CREATE INDEX idx_tgt_salesman ON rpt_targets(salesman_code);
CREATE INDEX idx_tgt_route ON rpt_targets(route_code);
CREATE INDEX idx_tgt_dates ON rpt_targets(start_date, end_date);
