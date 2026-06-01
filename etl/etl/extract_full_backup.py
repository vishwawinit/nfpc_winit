#!/usr/bin/env python3
"""
NFPC Reports ETL - Extract from MSSQL, denormalize, load into PostgreSQL.
READ-ONLY on MSSQL source. All writes go to local PostgreSQL only.

Usage:
    python etl/extract.py              # Full ETL
    python etl/extract.py --table X    # Single table only
    python etl/extract.py --dry-run    # Show plan without executing

Logs to: etl/logs/etl_YYYYMMDD_HHMMSS.log
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pymssql
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Date range: Jan 01 to today
from datetime import date as _date
DATE_FROM = '2026-01-01'
DATE_TO = _date.today().strftime('%Y-%m-%d')
UPSERT_MODE = False

# ============================================================
# LOGGING SETUP
# ============================================================

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"etl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure root logger to write to both console and file
logger = logging.getLogger('etl')
logger.setLevel(logging.DEBUG)

# Console handler - INFO level, concise format
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter(
    '\033[90m%(asctime)s\033[0m %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(console)

# File handler - DEBUG level, full detail
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(file_handler)

log = logger.info
log_debug = logger.debug
log_warn = logger.warning
log_error = logger.error

# ============================================================
# PROGRESS TRACKER
# ============================================================

class ProgressTracker:
    """Tracks ETL progress across all steps."""

    def __init__(self):
        self.steps = []
        self.current_step = None
        self.etl_start = None
        self.completed = 0
        self.total_steps = 0
        self.total_rows = 0
        self.status_file = LOG_DIR / 'etl_status.json'

    def start_etl(self, total_steps):
        self.etl_start = time.time()
        self.total_steps = total_steps
        self._write_status()

    def start_step(self, name, expected_rows=None):
        self.current_step = {
            'name': name,
            'start': time.time(),
            'expected_rows': expected_rows,
            'rows_loaded': 0,
            'status': 'running',
        }
        bar = self._progress_bar()
        log(f"\n{'─' * 50}")
        log(f"  [{self.completed + 1}/{self.total_steps}] {name} {bar}")
        if expected_rows:
            log(f"       Expected: ~{expected_rows:,} rows")
        self._write_status()

    def update_rows(self, rows_so_far):
        """Called during batch loading to report progress."""
        if self.current_step:
            self.current_step['rows_loaded'] = rows_so_far
            elapsed = time.time() - self.current_step['start']
            rate = rows_so_far / elapsed if elapsed > 0 else 0
            expected = self.current_step.get('expected_rows')

            parts = [f"       {rows_so_far:>12,} rows"]
            parts.append(f" | {rate:,.0f} rows/sec")
            parts.append(f" | {elapsed:.0f}s elapsed")

            if expected and rate > 0:
                remaining_rows = expected - rows_so_far
                eta_secs = remaining_rows / rate if remaining_rows > 0 else 0
                parts.append(f" | ETA {eta_secs:.0f}s")

            log(''.join(parts))
            self._write_status()

    def finish_step(self, rows_loaded, error=None):
        elapsed = time.time() - self.current_step['start']
        rate = rows_loaded / elapsed if elapsed > 0 else 0

        self.current_step['rows_loaded'] = rows_loaded
        self.current_step['elapsed'] = elapsed
        self.current_step['rate'] = rate

        if error:
            self.current_step['status'] = 'FAILED'
            log_error(f"  FAILED: {error}")
        else:
            self.current_step['status'] = 'done'
            emoji = 'OK' if rows_loaded > 0 else 'EMPTY'
            log(f"  [{emoji}] {rows_loaded:,} rows in {elapsed:.1f}s ({rate:,.0f} rows/sec)")

        self.steps.append(self.current_step)
        self.completed += 1
        self.total_rows += rows_loaded

        # Estimate remaining time
        if self.completed < self.total_steps:
            avg_time = (time.time() - self.etl_start) / self.completed
            remaining = avg_time * (self.total_steps - self.completed)
            log(f"       Progress: {self.completed}/{self.total_steps} steps"
                f" | Est. remaining: {remaining / 60:.1f} min")

        self.current_step = None
        self._write_status()

    def finish_etl(self):
        total_elapsed = time.time() - self.etl_start
        log(f"\n{'═' * 60}")
        log(f"  ETL COMPLETE")
        log(f"  Total time:  {total_elapsed / 60:.1f} minutes")
        log(f"  Total rows:  {self.total_rows:,}")
        log(f"  Steps:       {self.completed}/{self.total_steps}")
        log(f"  Log file:    {log_file}")
        log(f"{'═' * 60}")

        # Summary table
        log(f"\n  {'Step':<35} {'Rows':>12} {'Time':>8} {'Rate':>12} {'Status'}")
        log(f"  {'─' * 35} {'─' * 12} {'─' * 8} {'─' * 12} {'─' * 8}")
        for s in self.steps:
            log(f"  {s['name']:<35} {s['rows_loaded']:>12,} {s['elapsed']:>7.1f}s {s.get('rate', 0):>10,.0f}/s  {s['status']}")

        self._write_status()

    def _progress_bar(self):
        pct = (self.completed / self.total_steps * 100) if self.total_steps else 0
        filled = int(pct / 5)
        return f"[{'█' * filled}{'░' * (20 - filled)}] {pct:.0f}%"

    def _write_status(self):
        """Write current status to JSON file for external monitoring."""
        status = {
            'started_at': datetime.fromtimestamp(self.etl_start).isoformat() if self.etl_start else None,
            'completed_steps': self.completed,
            'total_steps': self.total_steps,
            'total_rows': self.total_rows,
            'current_step': self.current_step['name'] if self.current_step else None,
            'current_step_rows': self.current_step['rows_loaded'] if self.current_step else 0,
            'elapsed_seconds': time.time() - self.etl_start if self.etl_start else 0,
            'log_file': str(log_file),
            'steps': [
                {'name': s['name'], 'rows': s['rows_loaded'], 'elapsed': s['elapsed'],
                 'status': s['status']}
                for s in self.steps
            ],
        }
        try:
            self.status_file.write_text(json.dumps(status, indent=2, default=str))
        except Exception:
            pass

progress = ProgressTracker()

# ============================================================
# DB CONNECTIONS
# ============================================================

def get_mssql_conn():
    log("Connecting to MSSQL...")
    conn = pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        login_timeout=15,
        timeout=1800,  # 30 min - large queries on outstanding/sales_detail need time
    )
    log("  MSSQL connected")
    return conn

def get_pg_conn():
    log("Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=os.environ.get('PG_PORT', '5432'),
        dbname=os.environ['PG_DATABASE'],
        user=os.environ.get('PG_USER', 'fci'),
        password=os.environ.get('PG_PASSWORD', ''),
    )
    log("  PostgreSQL connected")
    return conn

# ============================================================
# SCHEMA BOOTSTRAP
# ============================================================

def ensure_schema(pg_conn):
    """Create all ETL-managed tables and patch missing columns. Safe to run on existing DB."""
    cur = pg_conn.cursor()
    log("  Verifying schema...")

    tables = [
        # ── Dimensions ──────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS dim_sales_org (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200),
            country_code VARCHAR(50), currency_code VARCHAR(50), is_active BOOLEAN
        )""",
        """CREATE TABLE IF NOT EXISTS dim_route (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(100),
            sales_org_code VARCHAR(50), route_type VARCHAR(100),
            area_code VARCHAR(50), sub_area_code VARCHAR(50),
            route_cat_code VARCHAR(50), salesman_code VARCHAR(50),
            wh_code VARCHAR(50), is_active BOOLEAN,
            has_active_assignment BOOLEAN DEFAULT false
        )""",
        """CREATE TABLE IF NOT EXISTS dim_channel (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200)
        )""",
        """CREATE TABLE IF NOT EXISTS dim_country (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200)
        )""",
        """CREATE TABLE IF NOT EXISTS dim_region (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200), country_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS dim_city (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200), region_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS dim_user (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200), email VARCHAR(150),
            username VARCHAR(100), mobile_no VARCHAR(50), sales_org_code VARCHAR(50),
            route_code VARCHAR(100), depot_code VARCHAR(50), depot_name VARCHAR(255),
            reports_to VARCHAR(50), reports_to_name VARCHAR(200),
            user_type VARCHAR(50), user_sub_type VARCHAR(50), department VARCHAR(50),
            sales_group VARCHAR(50), emp_code VARCHAR(50), emp_file_no VARCHAR(100),
            role_code VARCHAR(50), role_name VARCHAR(200), location_code VARCHAR(50),
            van_code VARCHAR(100), country_code VARCHAR(50), region_code VARCHAR(50),
            ud_sales_org_code VARCHAR(50), ud_reports_to VARCHAR(50), is_active BOOLEAN
        )""",
        """CREATE TABLE IF NOT EXISTS dim_item (
            code VARCHAR(50) PRIMARY KEY, name VARCHAR(200),
            alt_name VARCHAR(200), arabic_name VARCHAR(200),
            sales_org_code VARCHAR(50), base_uom VARCHAR(50), is_active BOOLEAN,
            agency_code VARCHAR(50), agency_name VARCHAR(200),
            brand_code VARCHAR(50), brand_name VARCHAR(200),
            sub_brand_code VARCHAR(50), sub_brand_name VARCHAR(200),
            category_code VARCHAR(50), category_name VARCHAR(200),
            pack_type_code VARCHAR(50), pack_type_name VARCHAR(200),
            pack_size_code VARCHAR(50),
            flavor_code VARCHAR(50), flavor_name VARCHAR(200),
            segment_code VARCHAR(50), segment_name VARCHAR(200),
            item_type VARCHAR(50), classification VARCHAR(50), size VARCHAR(50),
            liter FLOAT, liter_per_unit FLOAT, order_category VARCHAR(50),
            case_conversion FLOAT, pc_conversion FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS dim_customer (
            code VARCHAR(50), sales_org_code VARCHAR(50), name VARCHAR(200),
            channel_code VARCHAR(50), channel_name VARCHAR(200),
            sub_channel_code VARCHAR(50), sub_channel_name VARCHAR(200),
            customer_group VARCHAR(50), customer_type VARCHAR(50), payment_type VARCHAR(50),
            city_code VARCHAR(200), city_name VARCHAR(200),
            region_code VARCHAR(50), region_name VARCHAR(200),
            country_code VARCHAR(50), country_name VARCHAR(200),
            latitude FLOAT, longitude FLOAT, is_active BOOLEAN,
            PRIMARY KEY (code, sales_org_code)
        )""",
        # ── Fact / Report tables ────────────────────────────────
        """CREATE TABLE IF NOT EXISTS rpt_sales_detail (
            trx_code VARCHAR(50), line_no INT, trx_date DATE, trip_date DATE,
            trx_type INT, payment_type INT, trx_status INT,
            user_code VARCHAR(50), user_name VARCHAR(200),
            sales_org_code VARCHAR(50), sales_org_name VARCHAR(200), depot_code VARCHAR(50),
            route_code VARCHAR(50), route_name VARCHAR(100), route_type VARCHAR(100),
            area_code VARCHAR(50), sub_area_code VARCHAR(50),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            channel_code VARCHAR(50), channel_name VARCHAR(200),
            sub_channel_code VARCHAR(50), sub_channel_name VARCHAR(200),
            customer_group VARCHAR(50), customer_type VARCHAR(50),
            country_code VARCHAR(50), country_name VARCHAR(200),
            region_code VARCHAR(50), region_name VARCHAR(200),
            city_code VARCHAR(200), city_name VARCHAR(200),
            item_code VARCHAR(50), item_name VARCHAR(200),
            brand_code VARCHAR(50), brand_name VARCHAR(200),
            category_code VARCHAR(50), category_name VARCHAR(200),
            sub_brand_code VARCHAR(50), sub_brand_name VARCHAR(200),
            pack_type_code VARCHAR(50), pack_type_name VARCHAR(200),
            segment_code VARCHAR(50), segment_name VARCHAR(200), base_uom VARCHAR(50),
            qty_cases FLOAT, qty_pieces FLOAT, qty_volume FLOAT,
            base_price FLOAT, net_amount FLOAT, discount_amount FLOAT,
            tax_amount FLOAT, gross_amount FLOAT,
            invoice_number VARCHAR(50), visit_code VARCHAR(50), created_on TIMESTAMP,
            PRIMARY KEY (trx_code, line_no)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_daily_sales_summary (
            id SERIAL PRIMARY KEY, date DATE,
            route_code VARCHAR(50), route_name VARCHAR(100),
            user_code VARCHAR(50), user_name VARCHAR(200),
            sales_org_code VARCHAR(50), sales_org_name VARCHAR(200),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            channel_code VARCHAR(50), channel_name VARCHAR(200),
            item_code VARCHAR(50), item_name VARCHAR(200),
            brand_code VARCHAR(50), brand_name VARCHAR(200),
            category_code VARCHAR(50), category_name VARCHAR(200),
            total_qty FLOAT, total_sales FLOAT,
            total_gr_qty FLOAT, total_gr_sales FLOAT,
            total_damage_qty FLOAT, total_damage_sales FLOAT,
            total_expiry_qty FLOAT, total_expiry_sales FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_collections (
            receipt_id BIGINT PRIMARY KEY, receipt_number VARCHAR(50),
            receipt_date DATE, trip_date DATE,
            user_code VARCHAR(50), user_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100),
            sales_org_code VARCHAR(50), sales_org_name VARCHAR(200),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            amount FLOAT, settled_amount FLOAT,
            payment_type VARCHAR(20), payment_status INT, currency_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_customer_visits (
            visit_id VARCHAR(50) PRIMARY KEY, date DATE, trip_date DATE,
            user_code VARCHAR(50), user_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100),
            sales_org_code VARCHAR(50), sales_org_name VARCHAR(200),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            channel_name VARCHAR(200), city_name VARCHAR(200), region_name VARCHAR(200),
            arrival_time TIMESTAMP, out_time TIMESTAMP, total_time_mins INT,
            is_productive BOOLEAN, is_planned BOOLEAN,
            latitude FLOAT, longitude FLOAT,
            journey_code VARCHAR(50), visit_code VARCHAR(100)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_journeys (
            journey_id INT PRIMARY KEY, journey_code VARCHAR(50), date DATE,
            user_code VARCHAR(50), user_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100),
            sales_org_code VARCHAR(50), start_time VARCHAR(50),
            end_time VARCHAR(50), vehicle_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_coverage_summary (
            id INT PRIMARY KEY, visit_date DATE,
            route_code VARCHAR(50), route_name VARCHAR(100),
            user_code VARCHAR(50), user_name VARCHAR(200), sales_org_code VARCHAR(50),
            scheduled_calls INT, total_actual_calls INT,
            planned_calls INT, unplanned_calls INT,
            selling_calls INT, planned_selling_calls INT
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_route_sales_collection (
            id INT PRIMARY KEY, date DATE,
            route_code VARCHAR(50), route_name VARCHAR(100),
            user_code VARCHAR(50), user_name VARCHAR(200), sales_org_code VARCHAR(50),
            total_sales FLOAT, total_collection FLOAT,
            total_sales_with_tax FLOAT, total_wastage FLOAT, target_amount FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_route_sales_summary_by_item (
            id SERIAL PRIMARY KEY, date DATE,
            route_code VARCHAR(50), route_name VARCHAR(100),
            user_code VARCHAR(50), user_name VARCHAR(200), sales_org_code VARCHAR(50),
            item_code VARCHAR(50), item_name VARCHAR(200),
            category_code VARCHAR(50), brand_code VARCHAR(50),
            total_sales FLOAT, total_collection FLOAT,
            total_sales_with_tax FLOAT, total_wastage FLOAT, target_amount FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_route_sales_by_item_customer (
            id SERIAL PRIMARY KEY,
            route_code VARCHAR(50), user_code VARCHAR(50),
            customer_code VARCHAR(50), item_code VARCHAR(50), date DATE,
            total_qty FLOAT, total_gr_qty FLOAT,
            total_damage_qty FLOAT, total_expiry_qty FLOAT,
            total_sales FLOAT, total_gr_sales FLOAT,
            total_damage_sales FLOAT, total_expiry_sales FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_targets (
            target_id BIGINT PRIMARY KEY, time_frame VARCHAR(1),
            start_date DATE, end_date DATE, year INT, month INT,
            salesman_code VARCHAR(50), salesman_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100), sales_org_code VARCHAR(50),
            item_key VARCHAR(50), item_name VARCHAR(200), customer_key VARCHAR(50),
            amount NUMERIC, quantity FLOAT, is_active BOOLEAN
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_outstanding (
            id INT PRIMARY KEY, trx_code VARCHAR(50),
            org_code VARCHAR(50), sales_org_name VARCHAR(200),
            customer_code VARCHAR(50), customer_name VARCHAR(200), channel_name VARCHAR(200),
            trx_date DATE, due_date DATE,
            original_amount NUMERIC, balance_amount NUMERIC,
            pending_amount NUMERIC, collected_amount NUMERIC,
            days_overdue INT, aging_bucket VARCHAR(20),
            user_code VARCHAR(50), user_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100), currency_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_eot (
            eot_id INT PRIMARY KEY,
            user_code VARCHAR(50), user_name VARCHAR(200),
            route_code VARCHAR(50), route_name VARCHAR(100), sales_org_code VARCHAR(50),
            eot_type VARCHAR(20), eot_time TIMESTAMP, trip_date DATE,
            route_start_datetime TIMESTAMP, unload_datetime TIMESTAMP,
            eot_status VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_journey_plan (
            id BIGINT PRIMARY KEY, date DATE,
            user_code VARCHAR(50), user_name VARCHAR(200),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            route_code VARCHAR(50), sequence INT, visit_status INT, sales_org_code VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_invoice_totals (
            id SERIAL PRIMARY KEY, trx_date DATE,
            route_code VARCHAR(50), route_name VARCHAR(100),
            user_code VARCHAR(50), user_name VARCHAR(200), sales_org_code VARCHAR(50),
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            total_sales NUMERIC(18,4) DEFAULT 0, total_returns NUMERIC(18,4) DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_holidays (
            holiday_id INT PRIMARY KEY, holiday_date DATE,
            name VARCHAR(200), year INT, sales_org_code VARCHAR(50)
        )""",
        # ── Extra tables ────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS dim_user_details (
            id INTEGER PRIMARY KEY,
            user_code VARCHAR(50), sales_org_code VARCHAR(50),
            reports_to VARCHAR(50),
            valid_from TIMESTAMP, valid_to TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS rpt_outstanding_summary (
            year INTEGER, aging_bucket VARCHAR(20),
            org_code VARCHAR(50), user_code VARCHAR(50),
            route_code VARCHAR(50), customer_code VARCHAR(50),
            customer_name TEXT, invoice_count BIGINT, pending_amount NUMERIC
        )""",
        """CREATE TABLE IF NOT EXISTS flat_customer_visit (
            id BIGSERIAL,
            visit_id VARCHAR(50), visit_code VARCHAR(100), journey_code VARCHAR(50),
            visit_date TIMESTAMP, arrival_time TIMESTAMP, out_time TIMESTAMP,
            total_time_mins INTEGER, is_productive_call INTEGER, is_productive INTEGER,
            type_of_call VARCHAR(50), non_productive_reason TEXT,
            visit_latitude DOUBLE PRECISION, visit_longitude DOUBLE PRECISION,
            customer_visit_app_id VARCHAR(50), vehicle_code VARCHAR(50),
            area_development_id VARCHAR(200), trip_date TIMESTAMP,
            customer_group_code VARCHAR(50), visit_modified_date INTEGER,
            visit_modified_time INTEGER,
            customer_code VARCHAR(50), customer_name VARCHAR(200),
            customer_alt_name VARCHAR(200), customer_arabic_name VARCHAR(400),
            contact_person_name VARCHAR(200), contact_no1 VARCHAR(100),
            contact_no2 VARCHAR(100), customer_email VARCHAR(200),
            customer_address1 VARCHAR(500), customer_address2 VARCHAR(500),
            customer_address3 VARCHAR(500), customer_po_box VARCHAR(500),
            customer_latitude DOUBLE PRECISION, customer_longitude DOUBLE PRECISION,
            customer_is_active BOOLEAN, customer_is_blocked BOOLEAN,
            customer_alternate_code VARCHAR(100), customer_zone VARCHAR(200),
            customer_area_code VARCHAR(100), customer_division_name VARCHAR(200),
            customer_group_name VARCHAR(200), customer_sub_classification VARCHAR(200),
            customer_type VARCHAR(10), outlet_size INTEGER, no_of_cashier INTEGER,
            customer_trn VARCHAR(50), customer_trade_license VARCHAR(50),
            user_code VARCHAR(50), user_name VARCHAR(100), user_email VARCHAR(150),
            user_mobile VARCHAR(50), user_department VARCHAR(50),
            user_type VARCHAR(50), user_sub_type VARCHAR(50), emp_code VARCHAR(50),
            user_sales_group VARCHAR(50), depot_code VARCHAR(50),
            user_location_code VARCHAR(50), user_ad_id VARCHAR(100),
            route_code VARCHAR(50), route_name VARCHAR(50), route_type VARCHAR(100),
            route_area_code VARCHAR(50), sub_area_code VARCHAR(50),
            route_sales_org_code VARCHAR(50), route_warehouse_code VARCHAR(50),
            route_capacity INTEGER, city_code VARCHAR(200), city_name VARCHAR(200),
            city_arabic_name VARCHAR(50), district_code VARCHAR(50),
            region_code VARCHAR(50), region_name VARCHAR(200),
            region_arabic_name VARCHAR(50), country_code VARCHAR(100),
            sales_org_code VARCHAR(50), sales_office_code VARCHAR(50),
            division_code VARCHAR(50), payment_term_code VARCHAR(50),
            price_list_code VARCHAR(50), payment_mode VARCHAR(50),
            detail_customer_type VARCHAR(50), payment_type VARCHAR(50),
            credit_limit NUMERIC, credit_days INTEGER,
            no_of_outstanding_invoices INTEGER, detail_is_blocked BOOLEAN,
            detail_sales_group VARCHAR(50), is_perfect_store BOOLEAN,
            sc_type VARCHAR(50), permanent_visibility INTEGER,
            off_shelf_visibility INTEGER, iatco_store_grade VARCHAR(10),
            bp_store_grade VARCHAR(10), channel_code VARCHAR(50),
            channel_name VARCHAR(200), channel_arabic_name VARCHAR(100),
            channel_category_code VARCHAR(50),
            sync_created_at TIMESTAMP, sync_updated_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS flat_daily_sales_report (
            id BIGSERIAL,
            trx_trxcode VARCHAR(50), trx_orgcode VARCHAR(50),
            trx_usercode VARCHAR(50), trx_clientcode VARCHAR(50),
            trx_trxdate TIMESTAMP, trx_trxtype INTEGER,
            trx_currencycode VARCHAR(50), trx_paymenttype INTEGER,
            trx_totalamount DOUBLE PRECISION,
            trx_totaldiscountamount DOUBLE PRECISION,
            trx_totaltaxamount DOUBLE PRECISION,
            trx_status INTEGER, trx_createdon TIMESTAMP, trx_trxstatus INTEGER,
            trx_lpocode VARCHAR(50), trx_deliverynumber VARCHAR(50),
            trx_invoicenumber VARCHAR(50), trx_routecode VARCHAR(50),
            trx_tripdate TIMESTAMP, line_lineno INTEGER,
            line_itemcode VARCHAR(50), line_baseprice DOUBLE PRECISION,
            line_uom VARCHAR(20), line_quantitybu DOUBLE PRECISION,
            line_quantitysu DOUBLE PRECISION, line_taxpercentage DOUBLE PRECISION,
            line_totaldiscountpercentage DOUBLE PRECISION,
            line_totaldiscountamount DOUBLE PRECISION,
            line_itemdescription VARCHAR(100), line_itemaltdescription VARCHAR(100),
            line_promoid NUMERIC, line_promotype VARCHAR(50),
            line_expirydate TIMESTAMP, line_batchnumber VARCHAR(50),
            line_taxamount DOUBLE PRECISION,
            customer_code VARCHAR(50), customer_description VARCHAR(200),
            customer_parentcode VARCHAR(50), customer_citycode VARCHAR(200),
            customer_regioncode VARCHAR(50), customer_isactive BOOLEAN,
            customer_customerarabicname VARCHAR(400), customer_divisionname VARCHAR(200),
            customer_groupname VARCHAR(200), customer_subclassification VARCHAR(200),
            customer_zone VARCHAR(200), customer_type VARCHAR(10),
            customer_jdecustomertype VARCHAR(50),
            customer_contactpersonname VARCHAR(200),
            customer_contactno1 VARCHAR(50), customer_contactno2 VARCHAR(50),
            customer_email VARCHAR(150), customer_address1 VARCHAR(200),
            customer_address2 VARCHAR(200), customer_address3 VARCHAR(200),
            customer_longitude DOUBLE PRECISION, customer_latitude DOUBLE PRECISION,
            customer_routecode VARCHAR(50), customer_salesmancode VARCHAR(50),
            customer_alternatecode VARCHAR(50), customer_channelcode VARCHAR(50),
            customer_channel_description VARCHAR(200),
            customer_subchannelcode VARCHAR(50),
            customer_subchannel_description VARCHAR(200),
            customer_subsubchannelcode VARCHAR(50),
            customer_subsubchannel_description VARCHAR(200),
            user_description VARCHAR(100), user_email VARCHAR(150),
            user_mobileno VARCHAR(50), user_isactive BOOLEAN, user_usertype VARCHAR(50),
            item_description VARCHAR(100),
            item_grouplevel1 VARCHAR(50), item_grouplevel2 VARCHAR(50),
            item_grouplevel3 VARCHAR(50), item_grouplevel4 VARCHAR(50),
            item_grouplevel5 VARCHAR(50),
            item_brand_description VARCHAR(250),
            item_subbrand_description VARCHAR(250),
            item_category_description VARCHAR(250),
            route_name VARCHAR(200), route_salesmancode VARCHAR(50),
            route_areacode VARCHAR(100), route_subareacode VARCHAR(100),
            route_isactive BOOLEAN,
            city_description VARCHAR(200), region_description VARCHAR(200),
            region_isactive BOOLEAN,
            warehouse_description VARCHAR(400), warehouse_isactive BOOLEAN,
            sync_created_at TIMESTAMP, sync_updated_at TIMESTAMP,
            trx_collectiontype VARCHAR(50)
        )""",
        """CREATE TABLE IF NOT EXISTS flat_payment (
            receipt_id BIGINT, receipt_number VARCHAR(50),
            app_id VARCHAR(50), site_number VARCHAR(50),
            receipt_date TIMESTAMP, trip_date TIMESTAMP, emp_no VARCHAR(50),
            amount DOUBLE PRECISION, currency_code VARCHAR(50), rate DOUBLE PRECISION,
            journey_code VARCHAR(50), visit_code VARCHAR(50),
            payment_status INTEGER, payment_type VARCHAR(20),
            approved_by_code VARCHAR(50), approved_date TIMESTAMP,
            consolidated_payment_code VARCHAR(50), pushed_on TIMESTAMP,
            settlement_code VARCHAR(50), app_payment_header_id VARCHAR(50),
            settled_amount DOUBLE PRECISION, created_on TIMESTAMP, modified_on TIMESTAMP,
            status INTEGER, route_code VARCHAR(50), vehicle_code VARCHAR(50),
            collected_by VARCHAR(50), sales_org_code VARCHAR(50),
            reason VARCHAR(1000), ad_id VARCHAR(200), sap_reference_number VARCHAR(50),
            pushed_status VARCHAR(50), pushed_message VARCHAR(1000),
            cancelled_document_number VARCHAR(50), is_cancelled BOOLEAN,
            comments VARCHAR(500), settled_on TIMESTAMP, settled_by VARCHAR(50),
            settlement_id INTEGER, manually_pushed_on TIMESTAMP,
            manually_pushed_by VARCHAR(50), jdetrx_number VARCHAR(50),
            qlikview_status INTEGER, qlikview_generated_date TIMESTAMP,
            attribute1 VARCHAR(100), attribute2 VARCHAR(100), attribute3 VARCHAR(100),
            attribute4 VARCHAR(100), attribute5 VARCHAR(100),
            is_settled INTEGER, phy_collected_date TIMESTAMP,
            phy_collected_by VARCHAR(100), cheque_to_bank_date TIMESTAMP,
            cheque_to_bank_by VARCHAR(100), is_cheque_to_bank INTEGER,
            invoice_number VARCHAR(50), trx_type VARCHAR(50),
            inv_amount DOUBLE PRECISION, inv_currency_code VARCHAR(50),
            inv_rate DOUBLE PRECISION, inv_payment_status INTEGER,
            cash_discount DOUBLE PRECISION, inv_status INTEGER,
            inv_pushed_on TIMESTAMP, inv_payment_type VARCHAR(20),
            inv_settled_amount DOUBLE PRECISION, inv_created_on TIMESTAMP,
            inv_modified_on TIMESTAMP, inv_sales_org_code VARCHAR(50),
            invoice_date TIMESTAMP, van_invoice_number VARCHAR(50),
            remarks VARCHAR(1000), actual_paid_amount DOUBLE PRECISION,
            customer_description VARCHAR(500), customer_arabic_name VARCHAR(500),
            customer_parent_code VARCHAR(50), customer_city_code VARCHAR(50),
            customer_region_code VARCHAR(50), customer_is_active BOOLEAN,
            customer_division_name VARCHAR(200), customer_group_name VARCHAR(200),
            customer_zone VARCHAR(100), customer_type VARCHAR(100),
            customer_jde_type VARCHAR(100), customer_route_code VARCHAR(50),
            customer_channel_code VARCHAR(50), customer_channel_description VARCHAR(200),
            customer_sub_channel_code VARCHAR(50),
            customer_sub_channel_description VARCHAR(200),
            customer_sub_sub_channel_code VARCHAR(50),
            customer_sub_sub_channel_description VARCHAR(200),
            user_description VARCHAR(500), user_email VARCHAR(200),
            user_mobile_no VARCHAR(50), user_is_active BOOLEAN, user_type VARCHAR(50),
            route_name VARCHAR(200), route_area_code VARCHAR(50),
            route_sub_area_code VARCHAR(50), route_is_active BOOLEAN,
            city_description VARCHAR(200), region_description VARCHAR(200)
        )""",
    ]

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_sd_date_org      ON rpt_sales_detail(trx_date, sales_org_code)",
        "CREATE INDEX IF NOT EXISTS idx_sd_route_date    ON rpt_sales_detail(route_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_user_date     ON rpt_sales_detail(user_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_item_date     ON rpt_sales_detail(item_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_customer_date ON rpt_sales_detail(customer_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_trxtype       ON rpt_sales_detail(trx_type)",
        "CREATE INDEX IF NOT EXISTS idx_sd_brand         ON rpt_sales_detail(brand_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_date         ON rpt_daily_sales_summary(date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_date_org     ON rpt_daily_sales_summary(date, sales_org_code)",
        "CREATE INDEX IF NOT EXISTS idx_dss_route_date   ON rpt_daily_sales_summary(route_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_user_date    ON rpt_daily_sales_summary(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_customer     ON rpt_daily_sales_summary(customer_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_item         ON rpt_daily_sales_summary(item_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_dss_brand        ON rpt_daily_sales_summary(brand_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_coll_date        ON rpt_collections(receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_coll_user        ON rpt_collections(user_code, receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_coll_route       ON rpt_collections(route_code, receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_coll_org         ON rpt_collections(sales_org_code, receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_cv_date          ON rpt_customer_visits(date)",
        "CREATE INDEX IF NOT EXISTS idx_cv_user_date     ON rpt_customer_visits(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_cv_route_date    ON rpt_customer_visits(route_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_cv_customer      ON rpt_customer_visits(customer_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_j_date           ON rpt_journeys(date)",
        "CREATE INDEX IF NOT EXISTS idx_j_user           ON rpt_journeys(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_cs_date          ON rpt_coverage_summary(visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_cs_route         ON rpt_coverage_summary(route_code, visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_cs_user          ON rpt_coverage_summary(user_code, visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_rsc_date         ON rpt_route_sales_collection(date)",
        "CREATE INDEX IF NOT EXISTS idx_rsc_route        ON rpt_route_sales_collection(route_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rssi_date        ON rpt_route_sales_summary_by_item(date)",
        "CREATE INDEX IF NOT EXISTS idx_rssi_route_date  ON rpt_route_sales_summary_by_item(route_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rssi_item_date   ON rpt_route_sales_summary_by_item(item_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rssi_user_date   ON rpt_route_sales_summary_by_item(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rssi_org_date    ON rpt_route_sales_summary_by_item(sales_org_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rsic_date        ON rpt_route_sales_by_item_customer(date)",
        "CREATE INDEX IF NOT EXISTS idx_rsic_route_date  ON rpt_route_sales_by_item_customer(route_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rsic_user_date   ON rpt_route_sales_by_item_customer(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_rsic_item_date   ON rpt_route_sales_by_item_customer(item_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_it_date          ON rpt_invoice_totals(trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_it_user_date     ON rpt_invoice_totals(user_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_it_route_date    ON rpt_invoice_totals(route_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_it_org_date      ON rpt_invoice_totals(sales_org_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_out_customer     ON rpt_outstanding(customer_code)",
        "CREATE INDEX IF NOT EXISTS idx_out_aging        ON rpt_outstanding(aging_bucket)",
        "CREATE INDEX IF NOT EXISTS idx_out_org          ON rpt_outstanding(org_code)",
        "CREATE INDEX IF NOT EXISTS idx_out_user         ON rpt_outstanding(user_code)",
        "CREATE INDEX IF NOT EXISTS idx_eot_date         ON rpt_eot(trip_date)",
        "CREATE INDEX IF NOT EXISTS idx_eot_user         ON rpt_eot(user_code, trip_date)",
        "CREATE INDEX IF NOT EXISTS idx_jp_date          ON rpt_journey_plan(date)",
        "CREATE INDEX IF NOT EXISTS idx_jp_user          ON rpt_journey_plan(user_code, date)",
        "CREATE INDEX IF NOT EXISTS idx_tgt_salesman     ON rpt_targets(salesman_code)",
        "CREATE INDEX IF NOT EXISTS idx_tgt_route        ON rpt_targets(route_code)",
        "CREATE INDEX IF NOT EXISTS idx_tgt_dates        ON rpt_targets(start_date, end_date)",
        # flat_customer_visit — unique on visit_id for upsert
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fcv_visit_id ON flat_customer_visit(visit_id)",
        "CREATE INDEX IF NOT EXISTS idx_fcv_date         ON flat_customer_visit(visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_fcv_user         ON flat_customer_visit(user_code, visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_fcv_route        ON flat_customer_visit(route_code, visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_fcv_customer     ON flat_customer_visit(customer_code, visit_date)",
        # flat_daily_sales_report — unique on (trx_trxcode, line_lineno) for upsert
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fdsr_trx ON flat_daily_sales_report(trx_trxcode, line_lineno)",
        "CREATE INDEX IF NOT EXISTS idx_fdsr_date        ON flat_daily_sales_report(trx_trxdate)",
        "CREATE INDEX IF NOT EXISTS idx_fdsr_user        ON flat_daily_sales_report(trx_usercode, trx_trxdate)",
        "CREATE INDEX IF NOT EXISTS idx_fdsr_route       ON flat_daily_sales_report(trx_routecode, trx_trxdate)",
        # flat_payment — unique on receipt_id for upsert
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fp_receipt ON flat_payment(receipt_id)",
        "CREATE INDEX IF NOT EXISTS idx_fp_date          ON flat_payment(receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_fp_emp           ON flat_payment(emp_no, receipt_date)",
        "CREATE INDEX IF NOT EXISTS idx_fp_route         ON flat_payment(route_code, receipt_date)",
        # rpt_outstanding_summary
        "CREATE INDEX IF NOT EXISTS idx_os_org           ON rpt_outstanding_summary(org_code)",
        "CREATE INDEX IF NOT EXISTS idx_os_user          ON rpt_outstanding_summary(user_code)",
        "CREATE INDEX IF NOT EXISTS idx_os_aging         ON rpt_outstanding_summary(aging_bucket)",
    ]

    # Patch columns that were added after initial schema creation
    patches = [
        "ALTER TABLE dim_route        ADD COLUMN IF NOT EXISTS has_active_assignment BOOLEAN DEFAULT false",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS alt_name        VARCHAR(200)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS arabic_name     VARCHAR(200)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS sales_org_code  VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS agency_code     VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS agency_name     VARCHAR(200)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS pack_size_code  VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS flavor_code     VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS flavor_name     VARCHAR(200)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS item_type       VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS classification  VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS size            VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS order_category  VARCHAR(50)",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS case_conversion FLOAT",
        "ALTER TABLE dim_item         ADD COLUMN IF NOT EXISTS pc_conversion   FLOAT",
        "ALTER TABLE rpt_sales_detail ADD COLUMN IF NOT EXISTS trx_status      INT",
        "ALTER TABLE rpt_eot          ADD COLUMN IF NOT EXISTS route_start_datetime TIMESTAMP",
        "ALTER TABLE rpt_eot          ADD COLUMN IF NOT EXISTS unload_datetime      TIMESTAMP",
        "ALTER TABLE rpt_eot          ADD COLUMN IF NOT EXISTS eot_status           VARCHAR(50)",
    ]

    created = 0
    for stmt in tables:
        cur.execute(stmt)
        created += 1

    for stmt in indexes:
        cur.execute(stmt)

    for stmt in patches:
        cur.execute(stmt)

    pg_conn.commit()
    cur.close()
    log(f"  Schema OK — {created} tables verified, patches applied.")


# ============================================================
# BATCH LOADER
# ============================================================

def build_upsert(columns, pk_cols):
    """Build ON CONFLICT (...) DO UPDATE SET clause for upsert mode."""
    non_pk = [c for c in columns if c not in pk_cols]
    set_clause = ', '.join(f'{c}=EXCLUDED.{c}' for c in non_pk)
    return f'({", ".join(pk_cols)}) DO UPDATE SET {set_clause}'


def extract_batch(ms_cursor, query, params, pg_conn, table, columns, batch_size=10000, on_conflict='DO NOTHING'):
    """Execute MSSQL query and batch-insert into Postgres with progress reporting."""
    log_debug(f"  SQL: {query[:200]}...")
    log(f"  Querying MSSQL (this may take a while for large tables)...")
    query_start = time.time()

    if params:
        ms_cursor.execute(query, params)
    else:
        ms_cursor.execute(query)

    query_elapsed = time.time() - query_start
    log(f"  MSSQL query returned in {query_elapsed:.1f}s - starting load...")

    pg_cur = pg_conn.cursor()
    total = 0
    cols_str = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    template = f"({placeholders})"
    insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES %s ON CONFLICT {on_conflict}"

    while True:
        rows = ms_cursor.fetchmany(batch_size)
        if not rows:
            break

        execute_values(pg_cur, insert_sql, rows, template=template, page_size=batch_size)
        total += len(rows)

        # Report every 10K rows, or every 50K for very large tables
        report_interval = 50000 if progress.current_step and (progress.current_step.get('expected_rows') or 0) > 500000 else 10000
        if total % report_interval == 0:
            pg_conn.commit()
            progress.update_rows(total)

    pg_conn.commit()
    pg_cur.close()
    return total


# ============================================================
# DIMENSION LOADERS
# ============================================================

def load_dimensions(ms_conn, pg_conn):
    """Load all dimension/lookup tables."""
    ms_cur = ms_conn.cursor()
    pg_cur = pg_conn.cursor()

    dims = [
        ('dim_sales_org', "DELETE FROM dim_sales_org",
         "SELECT Code, Description, CountryCode, CurrencyCode, IsActive FROM tblSalesOrganization",
         "INSERT INTO dim_sales_org (code, name, country_code, currency_code, is_active) VALUES %s"),

        ('dim_route', "DELETE FROM dim_route",
         "SELECT Code, Name, SalesOrgCode, RouteType, AreaCode, SubAreaCode, RouteCatCode, SalesmanCode, WHCode, IsActive FROM tblRoute",
         "INSERT INTO dim_route (code, name, sales_org_code, route_type, area_code, sub_area_code, route_cat_code, salesman_code, wh_code, is_active) VALUES %s"),

        ('dim_channel', "DELETE FROM dim_channel",
         "SELECT Code, Description FROM tblChannel",
         "INSERT INTO dim_channel (code, name) VALUES %s"),

        ('dim_country', "DELETE FROM dim_country",
         "SELECT Code, Description FROM tblCountry",
         "INSERT INTO dim_country (code, name) VALUES %s"),

        ('dim_region', "DELETE FROM dim_region",
         "SELECT Code, Description, CountryCode FROM tblRegion",
         "INSERT INTO dim_region (code, name, country_code) VALUES %s"),

        ('dim_city', "DELETE FROM dim_city",
         "SELECT Code, Description, RegionCode FROM tblCity",
         "INSERT INTO dim_city (code, name, region_code) VALUES %s"),
    ]

    progress.start_step('Dimensions (6 simple tables)', expected_rows=2000)
    total = 0
    for name, delete_sql, select_sql, insert_sql in dims:
        pg_cur.execute(delete_sql)
        ms_cur.execute(select_sql)
        rows = ms_cur.fetchall()
        if rows:
            execute_values(pg_cur, insert_sql, rows)
        pg_conn.commit()
        total += len(rows)
        log(f"    {name}: {len(rows)} rows")

    # Set dim_route.has_active_assignment from tblUserLocations
    # Routes in tblUserLocations = routes with active salesman assignments
    # This matches the filter used by MSSQL coverage dashboard SPs
    ms_cur.execute("""
        SELECT DISTINCT RouteCode FROM tblUserLocations
        WHERE IsActive = 1 AND RouteCode IS NOT NULL AND RouteCode != ''
    """)
    active_route_codes = [r[0] for r in ms_cur.fetchall()]
    pg_cur.execute("UPDATE dim_route SET has_active_assignment = false")
    if active_route_codes:
        ph = ','.join(['%s'] * len(active_route_codes))
        pg_cur.execute(f"UPDATE dim_route SET has_active_assignment = true WHERE code IN ({ph})",
                       active_route_codes)
    pg_conn.commit()
    log(f"    dim_route.has_active_assignment: {len(active_route_codes)} active routes")

    progress.finish_step(total)

    # dim_user (flat join across tblUser + tblUserRole + tblUserDetails + DepotMaster + tblUserLocations)
    # NOTE: tblUser.ReportsTo is NULL for all users. The actual hierarchy is in tblUserDetails.ReportsTo.
    # We use COALESCE(sup.Code, ud.ReportsTo) for reports_to to preserve the exact case of the user code.
    progress.start_step('dim_user (flat with roles/details/depot/location)', expected_rows=1200)
    pg_cur.execute("DELETE FROM dim_user")
    ms_cur.execute("""
        SELECT
            u.Code,
            u.Description,
            u.Email,
            u.Username,
            u.MobileNo,
            COALESCE(u.SalesOrgCode, ud.SalesOrgCode),
            u.RouteCode,
            COALESCE(rt.AreaCode, ul.RegionCode),
            COALESCE(rg.Description, ul.RegionCode),
            COALESCE(sup.Code, ud.ReportsTo),
            sup.Description,
            u.UserType,
            u.UserSubType,
            u.Department,
            u.SalesGroup,
            u.EmpCode,
            u.EmpFileNo,
            COALESCE(ur2.RoleCode, u.RoleCode),
            rl.Name,
            u.LocationCode,
            u.VanCode,
            ul.CountryCode,
            ul.RegionCode,
            ud.SalesOrgCode,
            ud.ReportsTo,
            u.IsActive
        FROM tblUser u
        LEFT JOIN (
            SELECT UserCode, RoleCode,
                   ROW_NUMBER() OVER (PARTITION BY UserCode ORDER BY CreatedOn DESC) AS rn
            FROM tblUserRole
        ) ur2 ON ur2.UserCode = u.Code AND ur2.rn = 1
        LEFT JOIN tblRole rl ON rl.Code = COALESCE(ur2.RoleCode, u.RoleCode)
        LEFT JOIN tblRoute rt ON rt.Code = u.RouteCode
        LEFT JOIN tblRegion rg ON rg.Code = rt.AreaCode
        LEFT JOIN (
            SELECT UserCode, SalesOrgCode, ReportsTo,
                   ROW_NUMBER() OVER (PARTITION BY UserCode ORDER BY UserDetailsID DESC) AS rn
            FROM tblUserDetails
        ) ud ON ud.UserCode = u.Code AND ud.rn = 1
        LEFT JOIN tblUser sup ON sup.Code = ud.ReportsTo COLLATE SQL_Latin1_General_CP1_CI_AS
        LEFT JOIN (
            SELECT UserCode, CountryCode, RegionCode, Site,
                   ROW_NUMBER() OVER (PARTITION BY UserCode ORDER BY UserLocationId DESC) AS rn
            FROM tblUserLocations
        ) ul ON ul.UserCode = u.Code AND ul.rn = 1
    """)
    rows = ms_cur.fetchall()
    if rows:
        execute_values(pg_cur,
            """INSERT INTO dim_user (code, name, email, username, mobile_no,
               sales_org_code, route_code, depot_code, depot_name,
               reports_to, reports_to_name, user_type, user_sub_type,
               department, sales_group, emp_code, emp_file_no,
               role_code, role_name, location_code, van_code,
               country_code, region_code, ud_sales_org_code, ud_reports_to,
               is_active) VALUES %s""",
            rows)
    pg_conn.commit()
    log(f"    dim_user: {len(rows)} rows")
    progress.finish_step(len(rows))

    # dim_item (flat with correct GroupLevel -> ItemGroupLevel mapping + UOM)
    # GroupLevel1=Agency(0), GL2=Brand(1), GL3=SubBrand(2), GL4=Category(3),
    # GL5=PackType(5), GL6=PackSize, GL7=Flavor(7), GL8=Segment(8)
    progress.start_step('dim_item (flat with groups + UOM)', expected_rows=10000)
    pg_cur.execute("DELETE FROM dim_item")
    ms_cur.execute("""
        SELECT i.Code, i.Description, i.AltDescription, i.ArabicName,
            i.SalesOrgCode, i.BaseUOM, i.IsActive,
            RTRIM(i.GroupLevel1), g0.Description,
            RTRIM(i.GroupLevel2), g1.Description,
            RTRIM(i.GroupLevel3), g2.Description,
            RTRIM(i.GroupLevel4), g3.Description,
            RTRIM(i.GroupLevel5), g5.Description,
            RTRIM(i.GroupLevel6),
            RTRIM(i.GroupLevel7), g7.Description,
            RTRIM(i.GroupLevel8), g8.Description,
            i.ItemType, i.Classification, i.Size,
            i.Liter, i.LiterPerUnit, i.OrderCategory,
            u_ct.Conversion, u_pc.Conversion
        FROM tblItem i
        LEFT JOIN tblItemGroup g0 ON RTRIM(i.GroupLevel1) = RTRIM(g0.Code) AND g0.ItemGroupLevelId = 0
        LEFT JOIN tblItemGroup g1 ON RTRIM(i.GroupLevel2) = RTRIM(g1.Code) AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g2 ON RTRIM(i.GroupLevel3) = RTRIM(g2.Code) AND g2.ItemGroupLevelId = 2
        LEFT JOIN tblItemGroup g3 ON RTRIM(i.GroupLevel4) = RTRIM(g3.Code) AND g3.ItemGroupLevelId = 3
        LEFT JOIN tblItemGroup g5 ON RTRIM(i.GroupLevel5) = RTRIM(g5.Code) AND g5.ItemGroupLevelId = 5
        LEFT JOIN tblItemGroup g7 ON RTRIM(i.GroupLevel7) = RTRIM(g7.Code) AND g7.ItemGroupLevelId = 7
        LEFT JOIN tblItemGroup g8 ON RTRIM(i.GroupLevel8) = RTRIM(g8.Code) AND g8.ItemGroupLevelId = 8
        LEFT JOIN tblItemUom u_ct ON i.Code = u_ct.ItemCode AND u_ct.UOM = 'CT' AND i.SalesOrgCode = u_ct.SalesOrgCode
        LEFT JOIN tblItemUom u_pc ON i.Code = u_pc.ItemCode AND u_pc.UOM = 'PC' AND i.SalesOrgCode = u_pc.SalesOrgCode
    """)
    rows = ms_cur.fetchall()
    seen = set()
    unique_rows = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique_rows.append(r)
    execute_values(pg_cur,
        """INSERT INTO dim_item (code, name, alt_name, arabic_name,
           sales_org_code, base_uom, is_active,
           agency_code, agency_name,
           brand_code, brand_name,
           sub_brand_code, sub_brand_name,
           category_code, category_name,
           pack_type_code, pack_type_name,
           pack_size_code,
           flavor_code, flavor_name,
           segment_code, segment_name,
           item_type, classification, size,
           liter, liter_per_unit, order_category,
           case_conversion, pc_conversion) VALUES %s""",
        unique_rows)
    pg_conn.commit()
    log(f"    Deduped {len(rows)} -> {len(unique_rows)} items")
    progress.finish_step(len(unique_rows))

    # dim_customer
    progress.start_step('dim_customer', expected_rows=120000)
    pg_cur.execute("DELETE FROM dim_customer")
    ms_cur.execute("""
        SELECT c.Code, cd.SalesOrgCode, c.Description,
            cd.ChannelCode, ch.Description,
            cd.SubChannelCode, sc.Description,
            cd.CustomerGroupCode, cd.CustomerType, cd.PaymentType,
            c.CityCode, ci.Description,
            c.RegionCode, r.Description,
            c.CountryCode, co.Description,
            c.Latitude, c.Longitude, c.IsActive
        FROM tblCustomer c
        JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sc ON cd.SubChannelCode = sc.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblRegion r ON c.RegionCode = r.Code
        LEFT JOIN tblCountry co ON c.CountryCode = co.Code
    """)
    rows = ms_cur.fetchall()
    execute_values(pg_cur,
        """INSERT INTO dim_customer (code, sales_org_code, name, channel_code, channel_name,
           sub_channel_code, sub_channel_name, customer_group, customer_type, payment_type,
           city_code, city_name, region_code, region_name, country_code, country_name,
           latitude, longitude, is_active) VALUES %s ON CONFLICT DO NOTHING""",
        rows)
    pg_conn.commit()
    progress.finish_step(len(rows))
    pg_cur.close()


# ============================================================
# FACT TABLE LOADERS
# ============================================================

def load_sales_detail(ms_conn, pg_conn):
    """Load rpt_sales_detail - denormalized transaction lines. LARGEST TABLE."""
    progress.start_step('rpt_sales_detail', expected_rows=12_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_sales_detail WHERE trx_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT
            h.TrxCode, d.[LineNo], CAST(h.TrxDate AS DATE), CAST(h.TripDate AS DATE),
            h.TrxType, h.PaymentType, h.TRXStatus,
            h.UserCode, u.Description,
            h.OrgCode, so.Description, u.DepotCode,
            h.RouteCode, rt.Name, rt.RouteType, rt.AreaCode, rt.SubAreaCode,
            h.ClientCode, c.Description,
            cd.ChannelCode, ch.Description, cd.SubChannelCode, sc.Description,
            cd.CustomerGroupCode, cd.CustomerType,
            c.CountryCode, co.Description, c.RegionCode, rg.Description,
            c.CityCode, ci.Description,
            d.ItemCode, i.Description,
            i.GroupLevel1, g1.Description, i.GroupLevel3, g3.Description,
            i.GroupLevel2, g2.Description, i.GroupLevel5, g5.Description,
            i.GroupLevel8, g8.Description, i.BaseUOM,
            d.QuantityLevel1, d.QuantityBU,
            COALESCE(i.LiterPerUnit, 0) * d.QuantityBU,
            d.BasePrice, h.TotalAmount, d.TotalDiscountAmount, d.TaxAmount,
            d.BasePrice * d.QuantityBU,
            h.InvoiceNumber, h.VisitCode, d.CreatedOn
        FROM tblTrxHeader h
        JOIN tblTrxDetail d ON h.TrxCode = d.TrxCode
        LEFT JOIN tblUser u ON h.UserCode = u.Code
        LEFT JOIN tblSalesOrganization so ON h.OrgCode = so.Code
        LEFT JOIN tblRoute rt ON h.RouteCode = rt.Code
        LEFT JOIN tblCustomer c ON h.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sc ON cd.SubChannelCode = sc.Code
        LEFT JOIN tblCountry co ON c.CountryCode = co.Code
        LEFT JOIN tblRegion rg ON c.RegionCode = rg.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblItem i ON d.ItemCode = i.Code
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g2 ON i.GroupLevel2 = g2.Code AND g2.ItemGroupLevelId = 2
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        LEFT JOIN tblItemGroup g5 ON i.GroupLevel5 = g5.Code AND g5.ItemGroupLevelId = 5
        LEFT JOIN tblItemGroup g8 ON i.GroupLevel8 = g8.Code AND g8.ItemGroupLevelId = 8
        WHERE h.TrxDate >= %s AND h.TrxDate < %s
    """
    columns = [
        'trx_code', 'line_no', 'trx_date', 'trip_date', 'trx_type', 'payment_type', 'trx_status',
        'user_code', 'user_name', 'sales_org_code', 'sales_org_name', 'depot_code',
        'route_code', 'route_name', 'route_type', 'area_code', 'sub_area_code',
        'customer_code', 'customer_name',
        'channel_code', 'channel_name', 'sub_channel_code', 'sub_channel_name',
        'customer_group', 'customer_type',
        'country_code', 'country_name', 'region_code', 'region_name', 'city_code', 'city_name',
        'item_code', 'item_name', 'brand_code', 'brand_name', 'category_code', 'category_name',
        'sub_brand_code', 'sub_brand_name', 'pack_type_code', 'pack_type_name',
        'segment_code', 'segment_name', 'base_uom',
        'qty_cases', 'qty_pieces', 'qty_volume',
        'base_price', 'net_amount', 'discount_amount', 'tax_amount', 'gross_amount',
        'invoice_number', 'visit_code', 'created_on'
    ]
    # Process in 2-week chunks to avoid MSSQL tempdb overflow
    from datetime import datetime
    start = datetime.strptime(DATE_FROM, '%Y-%m-%d').date()
    end = datetime.strptime(DATE_TO, '%Y-%m-%d').date()

    grand_total = 0
    chunk_start = start
    chunk_days = 14  # 2-week chunks
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_days), end)
        log(f"    Processing {chunk_start} to {chunk_end}...")
        ms_cur = ms_conn.cursor()
        conflict = build_upsert(columns, ['trx_code', 'line_no']) if UPSERT_MODE else 'DO NOTHING'
        total = extract_batch(ms_cur, query, (str(chunk_start), str(chunk_end)),
                              pg_conn, 'rpt_sales_detail', columns, on_conflict=conflict)
        grand_total += total
        log(f"    {chunk_start} to {chunk_end}: {total:,} rows")
        chunk_start = chunk_end

    pg_cur.close()
    progress.finish_step(grand_total)


def load_daily_sales_summary(ms_conn, pg_conn):
    """Aggregated from tblTrxHeader/Detail - processes month by month to avoid tempdb overflow."""
    progress.start_step('rpt_daily_sales_summary', expected_rows=5_000_000)
    pg_cur = pg_conn.cursor()
    # Aggregate table — always delete+insert atomically (no natural source PK for true upsert)
    pg_cur.execute("DELETE FROM rpt_daily_sales_summary WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
    pg_conn.commit()

    query = """
        SELECT
            CAST(h.TrxDate AS DATE), h.RouteCode, rt.Name,
            h.UserCode, u.Description, h.OrgCode, so.Description,
            h.ClientCode, c.Description, cd.ChannelCode, ch.Description,
            d.ItemCode, i.Description,
            i.GroupLevel1, g1.Description, i.GroupLevel3, g3.Description,
            SUM(CASE WHEN h.TrxType = 1 THEN d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType = 1 THEN d.BasePrice * d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType = 4 THEN d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType = 4 THEN d.BasePrice * d.QuantityBU ELSE 0 END),
            0, 0, 0, 0
        FROM tblTrxHeader h
        JOIN tblTrxDetail d ON h.TrxCode = d.TrxCode
        LEFT JOIN tblRoute rt ON h.RouteCode = rt.Code
        LEFT JOIN tblUser u ON h.UserCode = u.Code
        LEFT JOIN tblSalesOrganization so ON h.OrgCode = so.Code
        LEFT JOIN tblCustomer c ON h.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblItem i ON d.ItemCode = i.Code
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        WHERE h.TrxDate >= %s AND h.TrxDate < %s AND h.TrxType IN (1, 4)
        GROUP BY CAST(h.TrxDate AS DATE), h.RouteCode, rt.Name,
            h.UserCode, u.Description, h.OrgCode, so.Description,
            h.ClientCode, c.Description, cd.ChannelCode, ch.Description,
            d.ItemCode, i.Description, i.GroupLevel1, g1.Description,
            i.GroupLevel3, g3.Description
    """
    columns = [
        'date', 'route_code', 'route_name', 'user_code', 'user_name',
        'sales_org_code', 'sales_org_name',
        'customer_code', 'customer_name', 'channel_code', 'channel_name',
        'item_code', 'item_name', 'brand_code', 'brand_name',
        'category_code', 'category_name',
        'total_qty', 'total_sales', 'total_gr_qty', 'total_gr_sales',
        'total_damage_qty', 'total_damage_sales', 'total_expiry_qty', 'total_expiry_sales'
    ]

    # Process month by month to avoid MSSQL tempdb overflow
    from datetime import datetime, timedelta
    def relativedelta_months(d, n):
        """Add n months to date d."""
        m = d.month + n
        y = d.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        import calendar
        day = min(d.day, calendar.monthrange(y, m)[1])
        return d.replace(year=y, month=m, day=day)
    start = datetime.strptime(DATE_FROM, '%Y-%m-%d').date()
    end = datetime.strptime(DATE_TO, '%Y-%m-%d').date()

    grand_total = 0
    month_start = start
    while month_start < end:
        month_end = min(relativedelta_months(month_start, 1), end)
        log(f"    Processing {month_start} to {month_end}...")
        ms_cur = ms_conn.cursor()
        total = extract_batch(ms_cur, query, (str(month_start), str(month_end)),
                              pg_conn, 'rpt_daily_sales_summary', columns)
        grand_total += total
        log(f"    {month_start.strftime('%Y-%m')}: {total:,} rows")
        month_start = month_end

    pg_cur.close()
    progress.finish_step(grand_total)


def load_collections(ms_conn, pg_conn):
    progress.start_step('rpt_collections', expected_rows=1_500_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_collections WHERE receipt_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT ph.ReceiptId, ph.Receipt_Number,
            CAST(ph.ReceiptDate AS DATE), CAST(ph.TripDate AS DATE),
            ph.EmpNo, u.Description, ph.RouteCode, rt.Name,
            ph.SalesOrgCode, so.Description,
            ph.SITE_NUMBER, c.Description,
            ph.Amount, ph.SettledAmount, ph.PaymentType, ph.PaymentStatus, ph.CurrencyCode
        FROM tblPaymentHeader ph
        LEFT JOIN tblUser u ON ph.EmpNo = u.Code
        LEFT JOIN tblRoute rt ON ph.RouteCode = rt.Code
        LEFT JOIN tblSalesOrganization so ON ph.SalesOrgCode = so.Code
        LEFT JOIN tblCustomer c ON ph.SITE_NUMBER = c.Code
        WHERE ph.ReceiptDate >= %s AND ph.ReceiptDate < %s
    """
    columns = [
        'receipt_id', 'receipt_number', 'receipt_date', 'trip_date',
        'user_code', 'user_name', 'route_code', 'route_name',
        'sales_org_code', 'sales_org_name', 'customer_code', 'customer_name',
        'amount', 'settled_amount', 'payment_type', 'payment_status', 'currency_code'
    ]
    conflict = build_upsert(columns, ['receipt_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_collections', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_customer_visits(ms_conn, pg_conn):
    progress.start_step('rpt_customer_visits', expected_rows=3_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_customer_visits WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT CAST(cv.CustomerVisitId AS VARCHAR(50)),
            CAST(cv.Date AS DATE), CAST(cv.TripDate AS DATE),
            cv.UserCode, u.Description, cv.RouteCode, rt.Name,
            COALESCE(rt.SalesOrgCode, u.SalesOrgCode), so.Description,
            cv.ClientCode, c.Description,
            ch.Description, ci.Description, rg.Description,
            cv.ArrivalTime, cv.OutTime, cv.TotalTimeInMins,
            CAST(CASE WHEN cv.IsProductive = 1 THEN 1 ELSE 0 END AS BIT),
            CAST(CASE WHEN cv.TypeOfCall = 'Planned' THEN 1 ELSE 0 END AS BIT),
            cv.Latitude, cv.Longitude, cv.JourneyCode,
            cv.VisitCode
        FROM tblCustomerVisit cv
        LEFT JOIN tblUser u ON cv.UserCode = u.Code
        LEFT JOIN tblRoute rt ON cv.RouteCode = rt.Code
        LEFT JOIN tblSalesOrganization so ON COALESCE(rt.SalesOrgCode, u.SalesOrgCode) = so.Code
        LEFT JOIN tblCustomer c ON cv.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND COALESCE(rt.SalesOrgCode, u.SalesOrgCode) = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblRegion rg ON c.RegionCode = rg.Code
        WHERE cv.Date >= %s AND cv.Date < %s
    """
    columns = [
        'visit_id', 'date', 'trip_date', 'user_code', 'user_name', 'route_code', 'route_name',
        'sales_org_code', 'sales_org_name', 'customer_code', 'customer_name',
        'channel_name', 'city_name', 'region_name',
        'arrival_time', 'out_time', 'total_time_mins',
        'is_productive', 'is_planned', 'latitude', 'longitude', 'journey_code',
        'visit_code'
    ]
    conflict = build_upsert(columns, ['visit_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_customer_visits', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_journeys(ms_conn, pg_conn):
    progress.start_step('rpt_journeys', expected_rows=80_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_journeys WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT j.JourneyId, j.JourneyCode, CAST(j.Date AS DATE),
            j.UserCode, u.Description, rt.Code, rt.Name, u.SalesOrgCode,
            j.StartTime, j.EndTime, j.VehicleCode
        FROM tblJourney j
        LEFT JOIN tblUser u ON j.UserCode = u.Code
        LEFT JOIN tblRoute rt ON j.RCode = rt.Code
        WHERE j.Date >= %s AND j.Date < %s
    """
    columns = [
        'journey_id', 'journey_code', 'date', 'user_code', 'user_name',
        'route_code', 'route_name', 'sales_org_code',
        'start_time', 'end_time', 'vehicle_code'
    ]
    conflict = build_upsert(columns, ['journey_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_journeys', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_coverage_summary(ms_conn, pg_conn):
    progress.start_step('rpt_coverage_summary', expected_rows=25_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_coverage_summary WHERE visit_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT cs.Id, CAST(cs.VisitDate AS DATE),
            cs.RouteCode, cs.RouteDescription, cs.UserCode, cs.UserDescription,
            rt.SalesOrgCode,
            cs.ScheduledCalls, cs.TotalActualCalls, cs.ActualCalls,
            cs.TotalActualCalls - cs.ActualCalls,
            cs.SellingCalls, cs.PlannedSellingCalls
        FROM tblRouteCoverageSummary cs
        LEFT JOIN tblRoute rt ON cs.RouteCode = rt.Code
        WHERE cs.VisitDate >= %s AND cs.VisitDate < %s
    """
    columns = [
        'id', 'visit_date', 'route_code', 'route_name', 'user_code', 'user_name',
        'sales_org_code', 'scheduled_calls', 'total_actual_calls', 'planned_calls',
        'unplanned_calls', 'selling_calls', 'planned_selling_calls'
    ]
    conflict = build_upsert(columns, ['id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_coverage_summary', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_route_sales_collection(ms_conn, pg_conn):
    progress.start_step('rpt_route_sales_collection', expected_rows=25_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_route_sales_collection WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT rsc.Id, CAST(rsc.Date AS DATE),
            rsc.RouteCode, rsc.RouteDescription, rsc.UserCode, rsc.UserDescription,
            rt.SalesOrgCode,
            rsc.TotalSales, rsc.TotalCollection, rsc.TotalSalesWithTax, rsc.TotalWastage, rsc.TargetAmount
        FROM tblRouteSalesCollectionSummary rsc
        LEFT JOIN tblRoute rt ON rsc.RouteCode = rt.Code
        WHERE rsc.Date >= %s AND rsc.Date < %s
    """
    columns = [
        'id', 'date', 'route_code', 'route_name', 'user_code', 'user_name',
        'sales_org_code', 'total_sales', 'total_collection', 'total_sales_with_tax',
        'total_wastage', 'target_amount'
    ]
    conflict = build_upsert(columns, ['id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_route_sales_collection', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_targets(ms_conn, pg_conn):
    progress.start_step('rpt_targets', expected_rows=100)
    pg_cur = pg_conn.cursor()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT t.TargetId, t.TimeFrame, CAST(t.StartDate AS DATE), CAST(t.EndDate AS DATE),
            t.Year, t.Month, t.SalesmanCode, u.Description,
            t.RouteCode, rt.Name, t.SalesorgCode,
            t.ItemKey, i.Description, t.CustomerKey,
            t.Amount, t.Quantity, t.IsActive
        FROM tblCommonTarget t
        LEFT JOIN tblUser u ON t.SalesmanCode = u.Code
        LEFT JOIN tblRoute rt ON t.RouteCode = rt.Code
        LEFT JOIN tblItem i ON t.ItemKey = i.Code
    """
    ms_cur.execute(query)
    rows = ms_cur.fetchall()
    if rows:
        execute_values(pg_cur,
            """INSERT INTO rpt_targets (target_id, time_frame, start_date, end_date, year, month,
               salesman_code, salesman_name, route_code, route_name, sales_org_code,
               item_key, item_name, customer_key, amount, quantity, is_active) VALUES %s
               ON CONFLICT (target_id) DO UPDATE SET
                 time_frame=EXCLUDED.time_frame, start_date=EXCLUDED.start_date,
                 end_date=EXCLUDED.end_date, year=EXCLUDED.year, month=EXCLUDED.month,
                 salesman_code=EXCLUDED.salesman_code, salesman_name=EXCLUDED.salesman_name,
                 route_code=EXCLUDED.route_code, route_name=EXCLUDED.route_name,
                 sales_org_code=EXCLUDED.sales_org_code, item_key=EXCLUDED.item_key,
                 item_name=EXCLUDED.item_name, customer_key=EXCLUDED.customer_key,
                 amount=EXCLUDED.amount, quantity=EXCLUDED.quantity, is_active=EXCLUDED.is_active""",
            rows)
    pg_conn.commit()
    pg_cur.close()
    progress.finish_step(len(rows) if rows else 0)


def jde_to_date(jde_int):
    """Convert JDE Julian integer (e.g. 126066) to Python date."""
    if not jde_int or jde_int <= 0:
        return None
    try:
        century = (jde_int // 100000) * 100
        yy = (jde_int % 100000) // 1000
        ddd = jde_int % 1000
        year = 1900 + century + yy
        from datetime import date, timedelta
        return date(year, 1, 1) + timedelta(days=ddd - 1)
    except Exception:
        return None


def load_outstanding(ms_conn, pg_conn):
    progress.start_step('rpt_outstanding', expected_rows=5_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_outstanding WHERE trx_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    # Filter by TrxDateTime to keep within the ETL date range (table has 22M+ rows total)
    # Aging buckets are computed from due_date relative to today
    date_filter = ""
    if DATE_FROM:
        date_filter += f" AND mpi.TrxDateTime >= '{DATE_FROM}'"
    if DATE_TO:
        date_filter += f" AND mpi.TrxDateTime < DATEADD(day, 1, '{DATE_TO}')"
    query = f"""
        SELECT mpi.MiddleWarePendingInvoiceId, mpi.TrxCode,
            mpi.OrgCode, so.Description, mpi.ClientCode, c.Description, ch.Description,
            mpi.TrxDate, mpi.DueDate,
            mpi.OriginalAmount, mpi.BalanceAmount, mpi.PendingAmount, mpi.CollectedAmount,
            mpi.UserCode, u.Description, mpi.RouteCode, rt.Name, mpi.CurrencyCode
        FROM tblMiddleWarePendingInvoice mpi
        LEFT JOIN tblSalesOrganization so ON mpi.OrgCode = so.Code
        LEFT JOIN tblCustomer c ON mpi.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND mpi.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblUser u ON mpi.UserCode = u.Code
        LEFT JOIN tblRoute rt ON mpi.RouteCode = rt.Code
        WHERE mpi.BalanceAmount != 0{date_filter}
    """
    log_debug(f"  SQL: {query[:200]}...")
    log(f"  Querying MSSQL (this may take a while for large tables)...")
    ms_cur.execute(query)
    log(f"  MSSQL query returned - starting load with Python date conversion...")

    from datetime import date as dt_date
    today = dt_date.today()
    pg_ins = pg_conn.cursor()
    columns = [
        'id', 'trx_code', 'org_code', 'sales_org_name', 'customer_code', 'customer_name',
        'channel_name', 'trx_date', 'due_date',
        'original_amount', 'balance_amount', 'pending_amount', 'collected_amount',
        'days_overdue', 'aging_bucket',
        'user_code', 'user_name', 'route_code', 'route_name', 'currency_code'
    ]
    cols_str = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    _out_conflict = build_upsert(columns, ['id']) if UPSERT_MODE else 'DO NOTHING'
    insert_sql = f"INSERT INTO rpt_outstanding ({cols_str}) VALUES %s ON CONFLICT {_out_conflict}"
    template = f"({placeholders})"

    total = 0
    while True:
        rows = ms_cur.fetchmany(10000)
        if not rows:
            break

        converted = []
        for r in rows:
            (mid, trx_code, org, org_name, cust, cust_name, chan_name,
             trx_date_jde, due_date_jde,
             orig_amt, bal_amt, pend_amt, coll_amt,
             user_code, user_name, route_code, route_name, currency) = r

            trx_date = jde_to_date(trx_date_jde)
            due_date = jde_to_date(due_date_jde)
            ref_date = due_date if due_date else trx_date
            days_overdue = (today - ref_date).days if ref_date else 0

            if days_overdue <= 0:
                aging = 'Current'
            elif days_overdue <= 30:
                aging = '1-30'
            elif days_overdue <= 60:
                aging = '31-60'
            elif days_overdue <= 90:
                aging = '61-90'
            elif days_overdue <= 120:
                aging = '91-120'
            else:
                aging = '120+'

            converted.append((
                mid, trx_code, org, org_name, cust, cust_name, chan_name,
                trx_date, due_date,
                orig_amt, bal_amt, pend_amt, coll_amt,
                days_overdue, aging,
                user_code, user_name, route_code, route_name, currency
            ))

        execute_values(pg_ins, insert_sql, converted, template=template, page_size=10000)
        total += len(converted)

        if total % 50000 == 0:
            pg_conn.commit()
            progress.update_rows(total)

    pg_conn.commit()
    pg_ins.close()
    pg_cur.close()
    progress.finish_step(total)


def load_eot(ms_conn, pg_conn):
    progress.start_step('rpt_eot', expected_rows=80_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_eot WHERE trip_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
    pg_cur.execute("""
        ALTER TABLE rpt_eot
            ADD COLUMN IF NOT EXISTS route_start_datetime TIMESTAMP,
            ADD COLUMN IF NOT EXISTS unload_datetime TIMESTAMP,
            ADD COLUMN IF NOT EXISTS eot_status VARCHAR(50)
    """)
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT e.EOTId, e.UserCode, u.Description,
            e.RouteCode, rt.Name, e.SalesOrgCode,
            e.EOTType, e.EOTTime, CAST(e.TripDate AS DATE),
            j.Date AS RouteStartDatetime,
            rud.CreatedOn AS UnloadDatetime,
            CASE WHEN e.EOTTime IS NOT NULL THEN 'Submitted' ELSE 'Pending' END AS EotStatus
        FROM tblEOT e
        LEFT JOIN tblUser u ON e.UserCode = u.Code
        LEFT JOIN tblRoute rt ON e.RouteCode = rt.Code
        LEFT JOIN tblJourney j ON j.UserCode = e.UserCode
            AND CAST(j.Date AS DATE) = CAST(e.TripDate AS DATE)
        LEFT JOIN tblRouteUnloadData rud ON rud.RouteCode = e.RouteCode
            AND CAST(rud.TripDate AS DATE) = CAST(e.TripDate AS DATE)
        WHERE e.TripDate >= %s AND e.TripDate < %s
    """
    columns = [
        'eot_id', 'user_code', 'user_name', 'route_code', 'route_name',
        'sales_org_code', 'eot_type', 'eot_time', 'trip_date',
        'route_start_datetime', 'unload_datetime', 'eot_status'
    ]
    conflict = build_upsert(columns, ['eot_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_eot', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_journey_plan(ms_conn, pg_conn):
    progress.start_step('rpt_journey_plan', expected_rows=2_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM rpt_journey_plan WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    # NOTE: In tblDailyJourneyPlan, UserCode = route code, SalesmanCode = actual user
    query = """
        SELECT jp.DailyJourneyPlanId, CAST(jp.JourneyDate AS DATE),
            ISNULL(jp.SalesmanCode, jp.UserCode),
            ISNULL(u.Description, ''),
            jp.CustomerCode, ISNULL(c.Description, ''),
            jp.UserCode,
            jp.Sequence, jp.VisitStatus,
            ISNULL(rt.SalesOrgCode, '')
        FROM tblDailyJourneyPlan jp (NOLOCK)
        LEFT JOIN tblUser u (NOLOCK) ON jp.SalesmanCode = u.Code
        LEFT JOIN tblCustomer c (NOLOCK) ON jp.CustomerCode = c.Code
        LEFT JOIN tblRoute rt (NOLOCK) ON jp.UserCode = rt.Code
        WHERE jp.JourneyDate >= %s AND jp.JourneyDate < %s
            AND (jp.IsDeleted = 0 OR jp.IsDeleted IS NULL)
    """
    columns = [
        'id', 'date',
        'user_code',       # = jp.SalesmanCode (the actual salesman)
        'user_name',
        'customer_code', 'customer_name',
        'route_code',      # = jp.UserCode (this IS the route code)
        'sequence', 'visit_status',
        'sales_org_code'   # from tblRoute via jp.UserCode
    ]
    conflict = build_upsert(columns, ['id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_journey_plan', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_invoice_totals(ms_conn, pg_conn):
    """Load rpt_invoice_totals - aggregated from tblTrxHeader with correct net formula.
    Matches: sp_tblOrder_Total_SalesAndCollection_Dashboard_Reports_V1
    Formula: TotalAmount + TotalTAXAmount - TotalDiscountAmount
    TrxType=1 → TotalSales, TrxType IN (4,12) → TotalReturns
    """
    progress.start_step('rpt_invoice_totals', expected_rows=500_000)
    pg_cur = pg_conn.cursor()
    # Aggregate table — atomic delete+insert (no stable source PK for true upsert)
    pg_cur.execute("DELETE FROM rpt_invoice_totals WHERE trx_date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
    pg_conn.commit()

    query = """
        SELECT
            CAST(h.TrxDate AS DATE),
            h.RouteCode, ISNULL(rt.Name, ''),
            h.UserCode, ISNULL(u.Description, ''),
            ISNULL(rt.SalesOrgCode, h.OrgCode),
            h.ClientCode, ISNULL(c.Description, ''),
            SUM(CASE WHEN h.TrxType = 1
                THEN h.TotalAmount + ISNULL(h.TotalTAXAmount,0) - ISNULL(h.TotalDiscountAmount,0)
                ELSE 0 END),
            SUM(CASE WHEN h.TrxType IN (4, 12)
                THEN h.TotalAmount + ISNULL(h.TotalTAXAmount,0) - ISNULL(h.TotalDiscountAmount,0)
                ELSE 0 END)
        FROM tblTrxHeader h (NOLOCK)
        LEFT JOIN tblRoute rt (NOLOCK) ON h.RouteCode = rt.Code
        LEFT JOIN tblUser u (NOLOCK) ON h.UserCode = u.Code
        LEFT JOIN tblCustomer c (NOLOCK) ON h.ClientCode = c.Code
        WHERE h.TrxType IN (1, 4, 12) AND h.TRXStatus = 200
            AND h.TrxDate >= %s AND h.TrxDate < %s
        GROUP BY CAST(h.TrxDate AS DATE), h.RouteCode, rt.Name,
            h.UserCode, u.Description, ISNULL(rt.SalesOrgCode, h.OrgCode),
            h.ClientCode, c.Description
    """
    columns = [
        'trx_date', 'route_code', 'route_name', 'user_code', 'user_name',
        'sales_org_code', 'customer_code', 'customer_name',
        'total_sales', 'total_returns'
    ]

    # Process in 2-week chunks to avoid MSSQL tempdb overflow
    from datetime import datetime
    start = datetime.strptime(DATE_FROM, '%Y-%m-%d').date()
    end = datetime.strptime(DATE_TO, '%Y-%m-%d').date()

    grand_total = 0
    chunk_start = start
    chunk_days = 14
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_days), end)
        log(f"    Processing {chunk_start} to {chunk_end}...")
        ms_cur = ms_conn.cursor()
        total = extract_batch(ms_cur, query, (str(chunk_start), str(chunk_end)),
                              pg_conn, 'rpt_invoice_totals', columns)
        grand_total += total
        log(f"    {chunk_start} to {chunk_end}: {total:,} rows")
        chunk_start = chunk_end

    pg_cur.close()
    progress.finish_step(grand_total)


def load_route_sales_summary_by_item(ms_conn, pg_conn):
    """Load rpt_route_sales_summary_by_item - primary dashboard source for sales/targets."""
    progress.start_step('rpt_route_sales_summary_by_item', expected_rows=500_000)
    pg_cur = pg_conn.cursor()
    # Aggregate table — atomic delete+insert (no stable source PK for true upsert)
    pg_cur.execute("DELETE FROM rpt_route_sales_summary_by_item WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT CAST(R.Date AS DATE), R.RouteCode, RR.Name,
            R.UserCode, U.Description, RR.SalesOrgCode,
            R.ItemCode, I.Description, I.GroupLevel3, I.GroupLevel1,
            R.TotalSales, R.TotalCollection, R.TotalSalesWithTax,
            R.TotalWastage, R.TargetAmount
        FROM tblRouteSalesSummaryByItem R WITH(NOLOCK)
        LEFT JOIN tblRoute RR ON RR.Code = R.RouteCode
        LEFT JOIN tblUser U ON R.UserCode = U.Code
        LEFT JOIN (SELECT Code, MIN(Description) AS Description, MIN(GroupLevel3) AS GroupLevel3, MIN(GroupLevel1) AS GroupLevel1 FROM tblItem GROUP BY Code) I ON R.ItemCode = I.Code
        WHERE R.Date >= %s AND R.Date < %s
    """
    columns = [
        'date', 'route_code', 'route_name', 'user_code', 'user_name',
        'sales_org_code', 'item_code', 'item_name', 'category_code', 'brand_code',
        'total_sales', 'total_collection', 'total_sales_with_tax',
        'total_wastage', 'target_amount'
    ]
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn,
                          'rpt_route_sales_summary_by_item', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_route_sales_by_item_customer(ms_conn, pg_conn):
    """Load rpt_route_sales_by_item_customer from tblRouteSalesSummaryByItemCustomer."""
    progress.start_step('rpt_route_sales_by_item_customer', expected_rows=2_500_000)
    pg_cur = pg_conn.cursor()
    # Aggregate table — atomic delete+insert (no stable source PK for true upsert)
    pg_cur.execute("DELETE FROM rpt_route_sales_by_item_customer WHERE date BETWEEN %s AND %s", (DATE_FROM, DATE_TO))
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT RouteCode, UserCode, CustomerCode, ItemCode,
            CAST(Date AS DATE), TotalQty, TotalGRQty, TotalDamageQty, TotalExpiryQty,
            TotalSales, TotalGRSales, TotalDamageSales, TotalExpirySales
        FROM tblRouteSalesSummaryByItemCustomer WITH(NOLOCK)
        WHERE Date >= %s AND Date < %s
    """
    columns = [
        'route_code', 'user_code', 'customer_code', 'item_code',
        'date', 'total_qty', 'total_gr_qty', 'total_damage_qty', 'total_expiry_qty',
        'total_sales', 'total_gr_sales', 'total_damage_sales', 'total_expiry_sales'
    ]
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn,
                          'rpt_route_sales_by_item_customer', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_holidays(ms_conn, pg_conn):
    progress.start_step('rpt_holidays', expected_rows=60)
    pg_cur = pg_conn.cursor()

    ms_cur = ms_conn.cursor()
    ms_cur.execute("SELECT HolidayId, CAST(HolidayDate AS DATE), Name, Year, SalesOrgCode FROM tblHoliday WHERE IsActive = 1")
    rows = ms_cur.fetchall()
    if rows:
        execute_values(pg_cur,
            """INSERT INTO rpt_holidays (holiday_id, holiday_date, name, year, sales_org_code) VALUES %s
               ON CONFLICT (holiday_id) DO UPDATE SET
                 holiday_date=EXCLUDED.holiday_date, name=EXCLUDED.name,
                 year=EXCLUDED.year, sales_org_code=EXCLUDED.sales_org_code""",
            rows)
    pg_conn.commit()
    pg_cur.close()
    progress.finish_step(len(rows) if rows else 0)


# ============================================================
# EXTRA TABLE LOADERS (flat_ tables, rpt_outstanding_summary, dim_user_details)
# conversations & messages are app-generated tables — NOT sourced from MSSQL, skipped.
# ============================================================

def load_dim_user_details(ms_conn, pg_conn):
    """Full reload of dim_user_details from tblUserDetails."""
    progress.start_step('dim_user_details', expected_rows=2000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("DELETE FROM dim_user_details")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    ms_cur.execute("""
        SELECT UserDetailsId, UserCode, SalesOrgCode, ReportsTo, CreatedOn, ModifiedOn
        FROM tblUserDetails WITH(NOLOCK)
    """)
    rows = ms_cur.fetchall()
    if rows:
        execute_values(pg_cur,
            """INSERT INTO dim_user_details
               (id, user_code, sales_org_code, reports_to, valid_from, valid_to)
               VALUES %s ON CONFLICT (id) DO UPDATE SET
                 user_code=EXCLUDED.user_code, sales_org_code=EXCLUDED.sales_org_code,
                 reports_to=EXCLUDED.reports_to, valid_from=EXCLUDED.valid_from,
                 valid_to=EXCLUDED.valid_to""",
            rows)
    pg_conn.commit()
    pg_cur.close()
    progress.finish_step(len(rows) if rows else 0)


def load_flat_customer_visit(ms_conn, pg_conn):
    """Detailed flat customer visit table — upsert on visit_id (UUID from source)."""
    progress.start_step('flat_customer_visit', expected_rows=3_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute("DELETE FROM flat_customer_visit WHERE visit_date BETWEEN %s AND %s",
                       (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT
            CAST(cv.CustomerVisitAppId AS VARCHAR(50)),
            cv.VisitCode,
            cv.JourneyCode,
            cv.Date,
            cv.ArrivalTime,
            cv.OutTime,
            cv.TotalTimeInMins,
            cv.IsProductiveCall,
            cv.IsProductive,
            cv.TypeOfCall,
            cv.NonProductiveReason,
            cv.Latitude,
            cv.Longitude,
            CAST(cv.CustomerVisitAppId AS VARCHAR(50)),
            cv.VehicleCode,
            cv.AreaDevelopmentId,
            cv.TripDate,
            ISNULL(cd.CustomerGroupCode, ''),
            cv.ModifiedDate,
            cv.ModifiedTime,
            c.Code,
            c.Description,
            ISNULL(c.AltDescription, ''),
            ISNULL(c.ArabicName, ''),
            ISNULL(c.ContactPersonName, ''),
            ISNULL(c.ContactNo1, ''),
            ISNULL(c.ContactNo2, ''),
            ISNULL(c.Email, ''),
            ISNULL(c.Address1, ''),
            ISNULL(c.Address2, ''),
            ISNULL(c.Address3, ''),
            ISNULL(c.POBox, ''),
            c.Latitude,
            c.Longitude,
            CAST(c.IsActive AS BIT),
            ISNULL(CAST(c.IsBlocked AS BIT), 0),
            ISNULL(c.AlternateCode, ''),
            ISNULL(c.Zone, ''),
            ISNULL(c.AreaCode, ''),
            ISNULL(c.DivisionName, ''),
            ISNULL(cd.CustomerGroupName, ''),
            ISNULL(cd.CustomerSubClassification, ''),
            ISNULL(c.CustomerType, ''),
            ISNULL(c.OutletSize, 0),
            ISNULL(c.NoOfCashier, 0),
            ISNULL(c.TRN, ''),
            ISNULL(c.TradeLicense, ''),
            u.Code,
            ISNULL(u.Description, ''),
            ISNULL(u.Email, ''),
            ISNULL(u.MobileNo, ''),
            ISNULL(u.Department, ''),
            ISNULL(u.UserType, ''),
            ISNULL(u.UserSubType, ''),
            ISNULL(u.EmpCode, ''),
            ISNULL(u.SalesGroup, ''),
            ISNULL(u.DepotCode, ''),
            ISNULL(u.LocationCode, ''),
            ISNULL(u.ADId, ''),
            ISNULL(rt.Code, ''),
            ISNULL(rt.Name, ''),
            ISNULL(rt.RouteType, ''),
            ISNULL(rt.AreaCode, ''),
            ISNULL(rt.SubAreaCode, ''),
            ISNULL(rt.SalesOrgCode, ''),
            ISNULL(rt.WHCode, ''),
            ISNULL(rt.Capacity, 0),
            ISNULL(ci.Code, ''),
            ISNULL(ci.Description, ''),
            ISNULL(ci.ArabicName, ''),
            NULL,
            ISNULL(rg.Code, ''),
            ISNULL(rg.Description, ''),
            ISNULL(rg.ArabicName, ''),
            ISNULL(co.Code, ''),
            ISNULL(cd.SalesOrgCode, ''),
            ISNULL(cd.SalesOfficeCode, ''),
            ISNULL(cd.DivisionCode, ''),
            ISNULL(cd.PaymentTermCode, ''),
            ISNULL(cd.PriceListCode, ''),
            ISNULL(cd.PaymentMode, ''),
            ISNULL(cd.CustomerType, ''),
            ISNULL(cd.PaymentType, ''),
            ISNULL(cd.CreditLimit, 0),
            ISNULL(cd.CreditDays, 0),
            ISNULL(cd.NoOfOutstandingInvoices, 0),
            ISNULL(CAST(cd.IsBlocked AS BIT), 0),
            ISNULL(cd.SalesGroup, ''),
            ISNULL(CAST(cd.IsPerfectStore AS BIT), 0),
            ISNULL(cd.SCType, ''),
            ISNULL(cd.PermanentVisibility, 0),
            ISNULL(cd.OffShelfVisibility, 0),
            ISNULL(cd.IATCOStoreGrade, ''),
            ISNULL(cd.BPStoreGrade, ''),
            ISNULL(ch.Code, ''),
            ISNULL(ch.Description, ''),
            ISNULL(ch.ArabicName, ''),
            ISNULL(ch.CategoryCode, ''),
            cv.CreatedOn,
            ISNULL(cv.ModifiedOn, cv.CreatedOn)
        FROM tblCustomerVisit cv WITH(NOLOCK)
        LEFT JOIN tblUser u WITH(NOLOCK) ON cv.UserCode = u.Code
        LEFT JOIN tblRoute rt WITH(NOLOCK) ON cv.RouteCode = rt.Code
        LEFT JOIN tblCustomer c WITH(NOLOCK) ON cv.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd WITH(NOLOCK)
            ON c.Code = cd.CustomerCode AND ISNULL(rt.SalesOrgCode, u.SalesOrgCode) = cd.SalesOrgCode
        LEFT JOIN tblChannel ch WITH(NOLOCK) ON cd.ChannelCode = ch.Code
        LEFT JOIN tblCity ci WITH(NOLOCK) ON c.CityCode = ci.Code
        LEFT JOIN tblRegion rg WITH(NOLOCK) ON c.RegionCode = rg.Code
        LEFT JOIN tblCountry co WITH(NOLOCK) ON c.CountryCode = co.Code
        WHERE cv.Date >= %s AND cv.Date < %s
    """
    columns = [
        'visit_id', 'visit_code', 'journey_code', 'visit_date',
        'arrival_time', 'out_time', 'total_time_mins',
        'is_productive_call', 'is_productive', 'type_of_call', 'non_productive_reason',
        'visit_latitude', 'visit_longitude', 'customer_visit_app_id',
        'vehicle_code', 'area_development_id', 'trip_date', 'customer_group_code',
        'visit_modified_date', 'visit_modified_time',
        'customer_code', 'customer_name', 'customer_alt_name', 'customer_arabic_name',
        'contact_person_name', 'contact_no1', 'contact_no2', 'customer_email',
        'customer_address1', 'customer_address2', 'customer_address3', 'customer_po_box',
        'customer_latitude', 'customer_longitude', 'customer_is_active', 'customer_is_blocked',
        'customer_alternate_code', 'customer_zone', 'customer_area_code',
        'customer_division_name', 'customer_group_name', 'customer_sub_classification',
        'customer_type', 'outlet_size', 'no_of_cashier', 'customer_trn', 'customer_trade_license',
        'user_code', 'user_name', 'user_email', 'user_mobile', 'user_department',
        'user_type', 'user_sub_type', 'emp_code', 'user_sales_group', 'depot_code',
        'user_location_code', 'user_ad_id',
        'route_code', 'route_name', 'route_type', 'route_area_code', 'sub_area_code',
        'route_sales_org_code', 'route_warehouse_code', 'route_capacity',
        'city_code', 'city_name', 'city_arabic_name', 'district_code',
        'region_code', 'region_name', 'region_arabic_name', 'country_code',
        'sales_org_code', 'sales_office_code', 'division_code',
        'payment_term_code', 'price_list_code', 'payment_mode', 'detail_customer_type',
        'payment_type', 'credit_limit', 'credit_days', 'no_of_outstanding_invoices',
        'detail_is_blocked', 'detail_sales_group', 'is_perfect_store', 'sc_type',
        'permanent_visibility', 'off_shelf_visibility', 'iatco_store_grade', 'bp_store_grade',
        'channel_code', 'channel_name', 'channel_arabic_name', 'channel_category_code',
        'sync_created_at', 'sync_updated_at',
    ]
    conflict = build_upsert(columns, ['visit_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO),
                          pg_conn, 'flat_customer_visit', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_flat_daily_sales_report(ms_conn, pg_conn):
    """Detailed flat sales report — upsert on (trx_trxcode, line_lineno)."""
    progress.start_step('flat_daily_sales_report', expected_rows=12_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute(
            "DELETE FROM flat_daily_sales_report WHERE trx_trxdate BETWEEN %s AND %s",
            (DATE_FROM, DATE_TO))
        pg_conn.commit()

    query = """
        SELECT
            h.TrxCode, h.OrgCode, h.UserCode, h.ClientCode,
            h.TrxDate, h.TrxType, ISNULL(h.CurrencyCode,''),
            h.PaymentType, h.TotalAmount,
            ISNULL(h.TotalDiscountAmount,0), ISNULL(h.TotalTAXAmount,0),
            ISNULL(h.Status,0), h.CreatedOn, ISNULL(h.TRXStatus,0),
            ISNULL(h.LPOCode,''), ISNULL(h.DeliveryNumber,''), ISNULL(h.InvoiceNumber,''),
            ISNULL(h.RouteCode,''), h.TripDate,
            d.LineNo, d.ItemCode, ISNULL(d.BasePrice,0), ISNULL(d.UOM,''),
            ISNULL(d.QuantityBU,0), ISNULL(d.QuantitySU,0),
            ISNULL(d.TaxPercentage,0), ISNULL(d.TotalDiscountPercentage,0),
            ISNULL(d.TotalDiscountAmount,0),
            ISNULL(i.Description,''), ISNULL(i.AltDescription,''),
            ISNULL(d.PromoId,0), ISNULL(d.PromoType,''),
            d.ExpiryDate, ISNULL(d.BatchNumber,''), ISNULL(d.TaxAmount,0),
            c.Code, ISNULL(c.Description,''), ISNULL(c.ParentCode,''),
            ISNULL(c.CityCode,''), ISNULL(c.RegionCode,''),
            CAST(c.IsActive AS BIT),
            ISNULL(c.ArabicName,''), ISNULL(c.DivisionName,''),
            ISNULL(cd.CustomerGroupName,''), ISNULL(cd.CustomerSubClassification,''),
            ISNULL(c.Zone,''), ISNULL(c.CustomerType,''), ISNULL(c.JDEType,''),
            ISNULL(c.ContactPersonName,''), ISNULL(c.ContactNo1,''), ISNULL(c.ContactNo2,''),
            ISNULL(c.Email,''), ISNULL(c.Address1,''), ISNULL(c.Address2,''), ISNULL(c.Address3,''),
            ISNULL(c.Longitude,0), ISNULL(c.Latitude,0),
            ISNULL(c.RouteCode,''), ISNULL(c.SalesmanCode,''), ISNULL(c.AlternateCode,''),
            ISNULL(cd.ChannelCode,''), ISNULL(ch.Description,''),
            ISNULL(cd.SubChannelCode,''), ISNULL(sch.Description,''),
            ISNULL(cd.SubSubChannelCode,''), ISNULL(ssch.Description,''),
            ISNULL(u.Description,''), ISNULL(u.Email,''), ISNULL(u.MobileNo,''),
            CAST(u.IsActive AS BIT), ISNULL(u.UserType,''),
            ISNULL(i.Description,''),
            ISNULL(i.GroupLevel1,''), ISNULL(i.GroupLevel2,''),
            ISNULL(i.GroupLevel3,''), ISNULL(i.GroupLevel4,''), ISNULL(i.GroupLevel5,''),
            ISNULL(g1.Description,''), ISNULL(g2.Description,''), ISNULL(g3.Description,''),
            ISNULL(rt.Name,''), ISNULL(rt.SalesmanCode,''),
            ISNULL(rt.AreaCode,''), ISNULL(rt.SubAreaCode,''), CAST(rt.IsActive AS BIT),
            ISNULL(ci.Description,''), ISNULL(rg.Description,''),
            ISNULL(CAST(rg.IsActive AS BIT),0),
            ISNULL(wh.Description,''), ISNULL(CAST(wh.IsActive AS BIT),0),
            d.CreatedOn, ISNULL(d.ModifiedOn, d.CreatedOn),
            ISNULL(h.CollectionType,'')
        FROM tblTrxHeader h WITH(NOLOCK)
        JOIN tblTrxDetail d WITH(NOLOCK) ON h.TrxCode = d.TrxCode
        LEFT JOIN tblUser u WITH(NOLOCK) ON h.UserCode = u.Code
        LEFT JOIN tblRoute rt WITH(NOLOCK) ON h.RouteCode = rt.Code
        LEFT JOIN tblCustomer c WITH(NOLOCK) ON h.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd WITH(NOLOCK)
            ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch WITH(NOLOCK) ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sch WITH(NOLOCK) ON cd.SubChannelCode = sch.Code
        LEFT JOIN tblSubChannel ssch WITH(NOLOCK) ON cd.SubSubChannelCode = ssch.Code
        LEFT JOIN tblItem i WITH(NOLOCK) ON d.ItemCode = i.Code
        LEFT JOIN tblItemGroup g1 WITH(NOLOCK)
            ON RTRIM(i.GroupLevel1)=RTRIM(g1.Code) AND g1.ItemGroupLevelId=1
        LEFT JOIN tblItemGroup g2 WITH(NOLOCK)
            ON RTRIM(i.GroupLevel2)=RTRIM(g2.Code) AND g2.ItemGroupLevelId=2
        LEFT JOIN tblItemGroup g3 WITH(NOLOCK)
            ON RTRIM(i.GroupLevel3)=RTRIM(g3.Code) AND g3.ItemGroupLevelId=3
        LEFT JOIN tblCity ci WITH(NOLOCK) ON c.CityCode = ci.Code
        LEFT JOIN tblRegion rg WITH(NOLOCK) ON c.RegionCode = rg.Code
        LEFT JOIN tblWarehouse wh WITH(NOLOCK) ON rt.WHCode = wh.Code
        WHERE h.TrxDate >= %s AND h.TrxDate < %s
    """
    columns = [
        'trx_trxcode', 'trx_orgcode', 'trx_usercode', 'trx_clientcode',
        'trx_trxdate', 'trx_trxtype', 'trx_currencycode',
        'trx_paymenttype', 'trx_totalamount',
        'trx_totaldiscountamount', 'trx_totaltaxamount',
        'trx_status', 'trx_createdon', 'trx_trxstatus',
        'trx_lpocode', 'trx_deliverynumber', 'trx_invoicenumber',
        'trx_routecode', 'trx_tripdate',
        'line_lineno', 'line_itemcode', 'line_baseprice', 'line_uom',
        'line_quantitybu', 'line_quantitysu',
        'line_taxpercentage', 'line_totaldiscountpercentage', 'line_totaldiscountamount',
        'line_itemdescription', 'line_itemaltdescription',
        'line_promoid', 'line_promotype', 'line_expirydate', 'line_batchnumber', 'line_taxamount',
        'customer_code', 'customer_description', 'customer_parentcode',
        'customer_citycode', 'customer_regioncode', 'customer_isactive',
        'customer_customerarabicname', 'customer_divisionname',
        'customer_groupname', 'customer_subclassification',
        'customer_zone', 'customer_type', 'customer_jdecustomertype',
        'customer_contactpersonname', 'customer_contactno1', 'customer_contactno2',
        'customer_email', 'customer_address1', 'customer_address2', 'customer_address3',
        'customer_longitude', 'customer_latitude',
        'customer_routecode', 'customer_salesmancode', 'customer_alternatecode',
        'customer_channelcode', 'customer_channel_description',
        'customer_subchannelcode', 'customer_subchannel_description',
        'customer_subsubchannelcode', 'customer_subsubchannel_description',
        'user_description', 'user_email', 'user_mobileno', 'user_isactive', 'user_usertype',
        'item_description',
        'item_grouplevel1', 'item_grouplevel2', 'item_grouplevel3',
        'item_grouplevel4', 'item_grouplevel5',
        'item_brand_description', 'item_subbrand_description', 'item_category_description',
        'route_name', 'route_salesmancode', 'route_areacode', 'route_subareacode', 'route_isactive',
        'city_description', 'region_description', 'region_isactive',
        'warehouse_description', 'warehouse_isactive',
        'sync_created_at', 'sync_updated_at',
        'trx_collectiontype',
    ]

    # Process in 2-week chunks to avoid tempdb overflow
    start = datetime.strptime(DATE_FROM, '%Y-%m-%d').date()
    end = datetime.strptime(DATE_TO, '%Y-%m-%d').date()
    grand_total = 0
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=14), end)
        log(f"    Processing {chunk_start} to {chunk_end}...")
        ms_cur = ms_conn.cursor()
        conflict = (build_upsert(columns, ['trx_trxcode', 'line_lineno'])
                    if UPSERT_MODE else 'DO NOTHING')
        total = extract_batch(ms_cur, query, (str(chunk_start), str(chunk_end)),
                              pg_conn, 'flat_daily_sales_report', columns,
                              on_conflict=conflict)
        grand_total += total
        log(f"    {chunk_start} to {chunk_end}: {total:,} rows")
        chunk_start = chunk_end

    pg_cur.close()
    progress.finish_step(grand_total)


def load_flat_payment(ms_conn, pg_conn):
    """Detailed flat payment table — upsert on receipt_id."""
    progress.start_step('flat_payment', expected_rows=2_000_000)
    pg_cur = pg_conn.cursor()
    if not UPSERT_MODE:
        pg_cur.execute(
            "DELETE FROM flat_payment WHERE receipt_date BETWEEN %s AND %s",
            (DATE_FROM, DATE_TO))
        pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT
            ph.ReceiptId, ph.Receipt_Number,
            ISNULL(ph.AppId,''), ph.SITE_NUMBER,
            ph.ReceiptDate, ph.TripDate, ph.EmpNo,
            ph.Amount, ISNULL(ph.CurrencyCode,''), ISNULL(ph.Rate,1),
            ISNULL(ph.JourneyCode,''), ISNULL(ph.VisitCode,''),
            ph.PaymentStatus, ISNULL(ph.PaymentType,''),
            ISNULL(ph.ApprovedByCode,''), ph.ApprovedDate,
            ISNULL(ph.ConsolidatedPaymentCode,''), ph.PushedOn,
            ISNULL(ph.SettlementCode,''), ISNULL(ph.AppPaymentHeaderId,''),
            ISNULL(ph.SettledAmount,0),
            ph.CreatedOn, ph.ModifiedOn, ISNULL(ph.Status,0),
            ISNULL(ph.RouteCode,''), ISNULL(ph.VehicleCode,''),
            ISNULL(ph.CollectedBy,''), ISNULL(ph.SalesOrgCode,''),
            ISNULL(ph.Reason,''), ISNULL(ph.ADId,''),
            ISNULL(ph.SAPReferenceNumber,''),
            ISNULL(ph.PushedStatus,''), ISNULL(ph.PushedMessage,''),
            ISNULL(ph.CancelledDocumentNumber,''),
            ISNULL(CAST(ph.IsCancelled AS BIT),0),
            ISNULL(ph.Comments,''), ph.SettledOn, ISNULL(ph.SettledBy,''),
            ISNULL(ph.SettlementId,0), ph.ManuallyPushedOn,
            ISNULL(ph.ManuallyPushedBy,''), ISNULL(ph.JDETrxNumber,''),
            ISNULL(ph.QlikviewStatus,0), ph.QlikviewGeneratedDate,
            ISNULL(ph.Attribute1,''), ISNULL(ph.Attribute2,''),
            ISNULL(ph.Attribute3,''), ISNULL(ph.Attribute4,''), ISNULL(ph.Attribute5,''),
            ISNULL(ph.IsSettled,0), ph.PhyCollectedDate, ISNULL(ph.PhyCollectedBy,''),
            ph.ChequeToBankDate, ISNULL(ph.ChequeToBankBy,''), ISNULL(ph.IsChequeToBank,0),
            ISNULL(mpi.TrxCode,''), ISNULL(mpi.TrxType,''),
            ISNULL(mpi.OriginalAmount,0), ISNULL(mpi.CurrencyCode,''),
            ISNULL(mpi.Rate,1), ISNULL(mpi.PaymentStatus,0),
            ISNULL(mpi.CashDiscount,0), ISNULL(mpi.Status,0),
            mpi.PushedOn, ISNULL(mpi.PaymentType,''),
            ISNULL(mpi.SettledAmount,0), mpi.CreatedOn, mpi.ModifiedOn,
            ISNULL(mpi.OrgCode,''), mpi.TrxDate,
            ISNULL(mpi.VanInvoiceNumber,''), ISNULL(mpi.Remarks,''),
            ISNULL(mpi.ActualPaidAmount,0),
            ISNULL(c.Description,''), ISNULL(c.ArabicName,''),
            ISNULL(c.ParentCode,''), ISNULL(c.CityCode,''), ISNULL(c.RegionCode,''),
            CAST(c.IsActive AS BIT),
            ISNULL(c.DivisionName,''), ISNULL(cd.CustomerGroupName,''),
            ISNULL(c.Zone,''), ISNULL(cd.CustomerType,''), ISNULL(c.JDEType,''),
            ISNULL(c.RouteCode,''), ISNULL(cd.ChannelCode,''),
            ISNULL(ch.Description,''), ISNULL(cd.SubChannelCode,''),
            ISNULL(sch.Description,''), ISNULL(cd.SubSubChannelCode,''),
            ISNULL(ssch.Description,''),
            ISNULL(u.Description,''), ISNULL(u.Email,''), ISNULL(u.MobileNo,''),
            CAST(u.IsActive AS BIT), ISNULL(u.UserType,''),
            ISNULL(rt.Name,''), ISNULL(rt.AreaCode,''), ISNULL(rt.SubAreaCode,''),
            CAST(rt.IsActive AS BIT),
            ISNULL(ci.Description,''), ISNULL(rg.Description,'')
        FROM tblPaymentHeader ph WITH(NOLOCK)
        LEFT JOIN tblMiddleWarePendingInvoice mpi WITH(NOLOCK)
            ON ph.SITE_NUMBER = mpi.ClientCode AND ph.SalesOrgCode = mpi.OrgCode
            AND ph.ReceiptId = mpi.ReceiptId
        LEFT JOIN tblUser u WITH(NOLOCK) ON ph.EmpNo = u.Code
        LEFT JOIN tblRoute rt WITH(NOLOCK) ON ph.RouteCode = rt.Code
        LEFT JOIN tblCustomer c WITH(NOLOCK) ON ph.SITE_NUMBER = c.Code
        LEFT JOIN tblCustomerDetail cd WITH(NOLOCK)
            ON c.Code = cd.CustomerCode AND ph.SalesOrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch WITH(NOLOCK) ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sch WITH(NOLOCK) ON cd.SubChannelCode = sch.Code
        LEFT JOIN tblSubChannel ssch WITH(NOLOCK) ON cd.SubSubChannelCode = ssch.Code
        LEFT JOIN tblCity ci WITH(NOLOCK) ON c.CityCode = ci.Code
        LEFT JOIN tblRegion rg WITH(NOLOCK) ON c.RegionCode = rg.Code
        WHERE ph.ReceiptDate >= %s AND ph.ReceiptDate < %s
    """
    columns = [
        'receipt_id', 'receipt_number', 'app_id', 'site_number',
        'receipt_date', 'trip_date', 'emp_no',
        'amount', 'currency_code', 'rate',
        'journey_code', 'visit_code',
        'payment_status', 'payment_type',
        'approved_by_code', 'approved_date',
        'consolidated_payment_code', 'pushed_on',
        'settlement_code', 'app_payment_header_id',
        'settled_amount', 'created_on', 'modified_on', 'status',
        'route_code', 'vehicle_code', 'collected_by', 'sales_org_code',
        'reason', 'ad_id', 'sap_reference_number',
        'pushed_status', 'pushed_message',
        'cancelled_document_number', 'is_cancelled',
        'comments', 'settled_on', 'settled_by',
        'settlement_id', 'manually_pushed_on', 'manually_pushed_by',
        'jdetrx_number', 'qlikview_status', 'qlikview_generated_date',
        'attribute1', 'attribute2', 'attribute3', 'attribute4', 'attribute5',
        'is_settled', 'phy_collected_date', 'phy_collected_by',
        'cheque_to_bank_date', 'cheque_to_bank_by', 'is_cheque_to_bank',
        'invoice_number', 'trx_type',
        'inv_amount', 'inv_currency_code', 'inv_rate', 'inv_payment_status',
        'cash_discount', 'inv_status', 'inv_pushed_on', 'inv_payment_type',
        'inv_settled_amount', 'inv_created_on', 'inv_modified_on',
        'inv_sales_org_code', 'invoice_date',
        'van_invoice_number', 'remarks', 'actual_paid_amount',
        'customer_description', 'customer_arabic_name',
        'customer_parent_code', 'customer_city_code', 'customer_region_code',
        'customer_is_active',
        'customer_division_name', 'customer_group_name',
        'customer_zone', 'customer_type', 'customer_jde_type',
        'customer_route_code', 'customer_channel_code', 'customer_channel_description',
        'customer_sub_channel_code', 'customer_sub_channel_description',
        'customer_sub_sub_channel_code', 'customer_sub_sub_channel_description',
        'user_description', 'user_email', 'user_mobile_no', 'user_is_active', 'user_type',
        'route_name', 'route_area_code', 'route_sub_area_code', 'route_is_active',
        'city_description', 'region_description',
    ]
    conflict = build_upsert(columns, ['receipt_id']) if UPSERT_MODE else 'DO NOTHING'
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO),
                          pg_conn, 'flat_payment', columns, on_conflict=conflict)
    pg_cur.close()
    progress.finish_step(total)


def load_rpt_outstanding_summary(ms_conn, pg_conn):
    """Recompute rpt_outstanding_summary from rpt_outstanding in PostgreSQL (no MSSQL query)."""
    progress.start_step('rpt_outstanding_summary', expected_rows=5000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE TABLE rpt_outstanding_summary")
    pg_cur.execute("""
        INSERT INTO rpt_outstanding_summary
            (year, aging_bucket, org_code, user_code, route_code,
             customer_code, customer_name, invoice_count, pending_amount)
        SELECT
            EXTRACT(YEAR FROM trx_date)::INT AS year,
            aging_bucket,
            org_code,
            user_code,
            route_code,
            customer_code,
            MAX(customer_name) AS customer_name,
            COUNT(*) AS invoice_count,
            SUM(pending_amount) AS pending_amount
        FROM rpt_outstanding
        GROUP BY
            EXTRACT(YEAR FROM trx_date)::INT,
            aging_bucket, org_code, user_code, route_code, customer_code
    """)
    pg_conn.commit()
    pg_cur.execute("SELECT COUNT(*) FROM rpt_outstanding_summary")
    total = pg_cur.fetchone()[0]
    pg_cur.close()
    progress.finish_step(total)


# ============================================================
# MAIN
# ============================================================

ALL_STEPS = [
    ('dimensions',                   load_dimensions),
    ('dim_item',                     None),  # handled inside load_dimensions
    ('dim_customer',                 None),  # handled inside load_dimensions
    ('dim_user_details',             load_dim_user_details),
    ('holidays',                     load_holidays),
    ('targets',                      load_targets),
    ('coverage_summary',             load_coverage_summary),
    ('route_sales_collection',       load_route_sales_collection),
    ('route_sales_summary_by_item',  load_route_sales_summary_by_item),
    ('route_sales_by_item_customer', load_route_sales_by_item_customer),
    ('invoice_totals',               load_invoice_totals),
    ('eot',                          load_eot),
    ('journeys',                     load_journeys),
    ('collections',                  load_collections),
    ('customer_visits',              load_customer_visits),
    ('journey_plan',                 load_journey_plan),
    ('outstanding',                  load_outstanding),
    ('outstanding_summary',          load_rpt_outstanding_summary),
    ('daily_sales_summary',          load_daily_sales_summary),
    ('sales_detail',                 load_sales_detail),
    ('flat_customer_visit',          load_flat_customer_visit),
    ('flat_daily_sales_report',      load_flat_daily_sales_report),
    ('flat_payment',                 load_flat_payment),
    # NOTE: 'conversations' and 'messages' are app-generated AI chat tables.
    #       They have no MSSQL source and are managed entirely by the application.
    #       They are intentionally excluded from ETL.
]

# Only steps with actual loader functions
LOADABLE_STEPS = [(name, fn) for name, fn in ALL_STEPS if fn is not None]

def main():
    global DATE_FROM, DATE_TO, UPSERT_MODE

    parser = argparse.ArgumentParser(description='NFPC Reports ETL')
    parser.add_argument('--table', help='Load a single table only (e.g., sales_detail)')
    parser.add_argument('--dry-run', action='store_true', help='Show plan without executing')
    parser.add_argument('--from-date', default=DATE_FROM, help=f'Start date (default: {DATE_FROM})')
    parser.add_argument('--to-date', default=DATE_TO, help=f'End date (default: {DATE_TO})')
    parser.add_argument('--days', type=int, help='Sync last N days ending today (e.g. --days 7 = last 6 days + today). Enables upsert mode automatically.')
    parser.add_argument('--upsert', action='store_true', help='Upsert mode: update existing rows, insert new ones — never delete')
    parser.add_argument('--parallel', action='store_true', help='Run fact tables in parallel')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers (default: 4)')
    args = parser.parse_args()

    # --days N: dynamically compute date range (last N-1 days + today)
    if args.days:
        if args.days < 1:
            log_error("--days must be >= 1")
            sys.exit(1)
        DATE_FROM = (_date.today() - timedelta(days=args.days - 1)).strftime('%Y-%m-%d')
        DATE_TO = _date.today().strftime('%Y-%m-%d')
        UPSERT_MODE = True  # --days always uses upsert (no delete)
    else:
        DATE_FROM = args.from_date
        DATE_TO = args.to_date

    if args.upsert:
        UPSERT_MODE = True

    log(f"{'═' * 60}")
    log(f"  NFPC Reports ETL")
    log(f"  Date range: {DATE_FROM} to {DATE_TO}")
    log(f"  Sync mode:  {'UPSERT (no delete)' if UPSERT_MODE else 'DELETE + INSERT'}")
    log(f"  Exec mode:  {'parallel (workers=' + str(args.workers) + ')' if args.parallel else 'sequential (one table at a time)'}")
    log(f"  Log file:   {log_file}")
    log(f"{'═' * 60}")

    if args.table:
        steps = [(n, f) for n, f in LOADABLE_STEPS if n == args.table]
        if not steps:
            log_error(f"Unknown table: {args.table}")
            log(f"Available: {[n for n, _ in LOADABLE_STEPS]}")
            sys.exit(1)
    else:
        steps = LOADABLE_STEPS

    if args.dry_run:
        log("\n  DRY RUN - would execute these steps:")
        for i, (name, _) in enumerate(steps, 1):
            log(f"    {i}. {name}")
        return

    # Auto-create tables / patch missing columns before loading
    log("\nInitializing schema...")
    _pg = get_pg_conn()
    ensure_schema(_pg)
    _pg.close()

    progress.start_etl(len(steps))

    failed = []

    if args.parallel and not args.table:
        # Dimensions first (sequential, fast, needed by fact tables)
        DIM_STEPS = ['dimensions', 'holidays', 'targets', 'coverage_summary']
        dim_steps = [(n, f) for n, f in steps if n in DIM_STEPS]
        fact_steps = [(n, f) for n, f in steps if n not in DIM_STEPS]

        log(f"\n  [Phase 1] Loading {len(dim_steps)} dimension tables sequentially...")
        ms_conn = get_mssql_conn()
        pg_conn = get_pg_conn()
        for name, loader_fn in dim_steps:
            try:
                loader_fn(ms_conn, pg_conn)
            except Exception as e:
                log_error(f"FAILED on {name}: {e}")
                progress.finish_step(0, error=str(e))
                failed.append(name)
        ms_conn.close()
        pg_conn.close()

        log(f"\n  [Phase 2] Loading {len(fact_steps)} fact tables in parallel (workers={args.workers})...")

        def run_table(name, loader_fn):
            ms_c = get_mssql_conn()
            pg_c = get_pg_conn()
            try:
                loader_fn(ms_c, pg_c)
                return name, None
            except Exception as e:
                log_error(f"FAILED on {name}: {e}")
                progress.finish_step(0, error=str(e))
                return name, str(e)
            finally:
                try: ms_c.close()
                except Exception: pass
                try: pg_c.close()
                except Exception: pass

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_table, name, fn): name for name, fn in fact_steps}
            for future in as_completed(futures):
                name, err = future.result()
                if err:
                    failed.append(name)
    else:
        ms_conn = get_mssql_conn()
        pg_conn = get_pg_conn()

        for name, loader_fn in steps:
            try:
                loader_fn(ms_conn, pg_conn)
            except Exception as e:
                log_error(f"FAILED on {name}: {e}")
                log_debug(f"Traceback:", exc_info=True)
                progress.finish_step(0, error=str(e))
                failed.append(name)
                # Recover PG connection
                try:
                    pg_conn.rollback()
                except Exception:
                    try:
                        pg_conn = get_pg_conn()
                    except Exception:
                        pass
                # Recover MSSQL connection (likely dropped after long query)
                try:
                    ms_conn.close()
                except Exception:
                    pass
                try:
                    log("  Reconnecting to MSSQL...")
                    ms_conn = get_mssql_conn()
                    log("  MSSQL reconnected")
                except Exception as re:
                    log_error(f"  MSSQL reconnect failed: {re}")

        ms_conn.close()
        pg_conn.close()

    progress.finish_etl()

    if failed:
        log(f"\n  FAILED STEPS: {failed}")
        log(f"  Re-run with: python etl/extract.py --table <name>")
        sys.exit(1)


if __name__ == '__main__':
    main()
