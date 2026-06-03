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
DATE_TO = (_date.today() + timedelta(days=1)).strftime('%Y-%m-%d')  # exclusive upper bound — includes today
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
    ]

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_sd_date_org      ON rpt_sales_detail(trx_date, sales_org_code)",
        "CREATE INDEX IF NOT EXISTS idx_sd_route_date    ON rpt_sales_detail(route_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_user_date     ON rpt_sales_detail(user_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_item_date     ON rpt_sales_detail(item_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_customer_date ON rpt_sales_detail(customer_code, trx_date)",
        "CREATE INDEX IF NOT EXISTS idx_sd_trxtype       ON rpt_sales_detail(trx_type)",
        "CREATE INDEX IF NOT EXISTS idx_sd_brand         ON rpt_sales_detail(brand_code, trx_date)",        "CREATE INDEX IF NOT EXISTS idx_coll_date        ON rpt_collections(receipt_date)",
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
        "CREATE INDEX IF NOT EXISTS idx_tgt_dates        ON rpt_targets(start_date, end_date)",    ]

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


def extract_batch(ms_cursor, query, params, pg_conn, table, columns, batch_size=10000, on_conflict='DO NOTHING', dedup_keys=None):
    """Execute MSSQL query and batch-insert into Postgres with progress reporting.

    dedup_keys: list of column names forming the PK. When set and on_conflict is not
    DO NOTHING, duplicate rows within each batch are removed before insert — prevents
    'ON CONFLICT DO UPDATE cannot affect row a second time' errors caused by upstream
    JOIN duplicates in MSSQL.
    """
    log_debug(f"  SQL: {query[:200]}...")
    log(f"  Querying MSSQL (this may take a while for large tables)...")
    query_start = time.time()

    if params:
        ms_cursor.execute(query, params)
    else:
        ms_cursor.execute(query)

    query_elapsed = time.time() - query_start
    log(f"  MSSQL query returned in {query_elapsed:.1f}s - starting load...")

    # Pre-compute PK column indices for deduplication
    dedup_indices = None
    if dedup_keys and on_conflict != 'DO NOTHING':
        dedup_indices = [columns.index(k) for k in dedup_keys]

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

        # Deduplicate within batch by PK — last occurrence wins (most recent MSSQL data)
        if dedup_indices:
            seen = {}
            for row in rows:
                key = tuple(row[i] for i in dedup_indices)
                seen[key] = row
            rows = list(seen.values())

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

    # dim_user: one row per user, sourced from:
    #   tblUser          — master (code, name, route, is_active)
    #   tblUserRole      — role assignment (latest by CreatedOn)
    #   tblUserDetails   — org + hierarchy chain (latest active row by UserDetailsID)
    #   tblUser sup      — manager's display name via tblUserDetails.ReportsTo
    #   tblUserLocations — depot zone (RegionCode = EAD / N.E / S.E)
    #   tblRegion        — depot name
    #
    # Fixes vs previous ETL:
    #   sales_org_code: use ud.SalesOrgCode (tblUser.SalesOrgCode is wrong for HOS/ASM)
    #   depot_code:     use ul.RegionCode only (tblRoute.AreaCode was wrong for non-salesmen)
    #   reports_to:     UPPER(sup.Code) for case-normalised manager code
    #   role_code:      use tblUserRole only (tblUser.RoleCode may be stale)
    #   For multi-org users (HOS/ASM): dim_user holds the latest org row only.
    #   Multi-org filtering uses tbl_user_details (synced from NFPCsfaV3) directly.
    progress.start_step('dim_user (flat with roles/details/depot/location)', expected_rows=1200)
    pg_cur.execute("DELETE FROM dim_user")
    ms_cur.execute("""
        SELECT
            u.Code,
            u.Description,
            u.Email,
            u.Username,
            u.MobileNo,
            ud.SalesOrgCode,
            u.RouteCode,
            ul.RegionCode,
            rg.Description,
            UPPER(COALESCE(sup.Code, ud.ReportsTo)),
            sup.Description,
            u.UserType,
            u.UserSubType,
            u.Department,
            u.SalesGroup,
            u.EmpCode,
            u.EmpFileNo,
            ur2.RoleCode,
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
        LEFT JOIN tblRole rl ON rl.Code = ur2.RoleCode
        LEFT JOIN (
            SELECT UserCode, SalesOrgCode, ReportsTo,
                   ROW_NUMBER() OVER (PARTITION BY UserCode ORDER BY UserDetailsID DESC) AS rn
            FROM tblUserDetails
            WHERE ValidTo IS NULL OR ValidTo >= GETDATE()
        ) ud ON ud.UserCode = u.Code AND ud.rn = 1
        LEFT JOIN tblUser sup ON sup.Code = ud.ReportsTo COLLATE SQL_Latin1_General_CP1_CI_AS
        LEFT JOIN (
            SELECT UserCode, CountryCode, RegionCode,
                   ROW_NUMBER() OVER (PARTITION BY UserCode ORDER BY UserLocationId DESC) AS rn
            FROM tblUserLocations
        ) ul ON ul.UserCode = u.Code AND ul.rn = 1
        LEFT JOIN tblRegion rg ON rg.Code = ul.RegionCode
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
        LEFT JOIN (
            SELECT CustomerCode, SalesOrgCode, ChannelCode, SubChannelCode,
                   CustomerGroupCode, CustomerType,
                   ROW_NUMBER() OVER (PARTITION BY CustomerCode, SalesOrgCode
                                      ORDER BY CustomerDetailId DESC) AS rn
            FROM tblCustomerDetail
        ) cd ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode AND cd.rn = 1
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sc ON cd.SubChannelCode = sc.Code
        LEFT JOIN tblCountry co ON c.CountryCode = co.Code
        LEFT JOIN tblRegion rg ON c.RegionCode = rg.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN (
            SELECT Code, Description, GroupLevel1, GroupLevel2, GroupLevel3,
                   GroupLevel5, GroupLevel8, BaseUOM, LiterPerUnit,
                   ROW_NUMBER() OVER (PARTITION BY Code ORDER BY ItemId DESC) AS rn
            FROM tblItem
        ) i ON d.ItemCode = i.Code AND i.rn = 1
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
                              pg_conn, 'rpt_sales_detail', columns,
                              on_conflict=conflict, dedup_keys=['trx_code', 'line_no'])
        grand_total += total
        log(f"    {chunk_start} to {chunk_end}: {total:,} rows")
        chunk_start = chunk_end

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
        LEFT JOIN (
            SELECT Code, MIN(Description) AS Description
            FROM tblItem GROUP BY Code
        ) i ON t.ItemKey = i.Code
    """
    ms_cur.execute(query)
    rows = ms_cur.fetchall()
    # Deduplicate by target_id — tblCommonTarget can have duplicates via joins
    if rows:
        seen = {}
        for row in rows:
            seen[row[0]] = row  # row[0] = TargetId, last wins
        rows = list(seen.values())
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
        date_filter += f" AND mpi.TrxDateTime < '{DATE_TO}'"
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
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_eot', columns,
                          on_conflict=conflict, dedup_keys=['eot_id'])
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
    """Load rpt_route_sales_by_item_customer from raw transactions (tblTrxHeader + tblTrxDetail).
    Source changed from tblRouteSalesSummaryByItemCustomer — that table has incorrect/missing
    returns data. Raw transactions give correct returns breakdown by TD.Reason field.
    Chunked in 14-day windows to avoid MSSQL tempdb overflow on large date ranges.
    """
    progress.start_step('rpt_route_sales_by_item_customer', expected_rows=2_500_000)

    query = """
        SELECT
            TH.RouteCode,
            TH.UserCode,
            TH.ClientCode AS CustomerCode,
            TD.ItemCode,
            CAST(TH.TrxDate AS DATE) AS TrxDate,

            SUM(CASE WHEN TH.TrxType = 4 THEN -1 ELSE 1 END
                * ABS(TD.QuantityBU)) AS TotalQty,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Good return'
                     THEN ABS(TD.QuantityBU) ELSE 0 END) AS TotalGRQty,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Damaged'
                     THEN ABS(TD.QuantityBU) ELSE 0 END) AS TotalDamageQty,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Expiry'
                     THEN ABS(TD.QuantityBU) ELSE 0 END) AS TotalExpiryQty,

            SUM(CASE WHEN TH.TrxType = 4 THEN -1 ELSE 1 END *
                ABS((TD.QuantityLevel1 * TD.PriceUsedLevel1)
                    - ISNULL(TD.TotalDiscountAmount, 0)
                    + ISNULL(TD.ExciseDutyTaxAmount, 0)
                    + ISNULL(TD.Attribute17, 0))) AS TotalSales,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Good return'
                THEN ABS((TD.QuantityLevel1 * TD.PriceUsedLevel1)
                    - ISNULL(TD.TotalDiscountAmount, 0)
                    + ISNULL(TD.ExciseDutyTaxAmount, 0)
                    + ISNULL(TD.Attribute17, 0))
                ELSE 0 END) AS TotalGRSales,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Damaged'
                THEN ABS((TD.QuantityLevel1 * TD.PriceUsedLevel1)
                    - ISNULL(TD.TotalDiscountAmount, 0)
                    + ISNULL(TD.ExciseDutyTaxAmount, 0)
                    + ISNULL(TD.Attribute17, 0))
                ELSE 0 END) AS TotalDamageSales,

            SUM(CASE WHEN TH.TrxType = 4 AND TD.Reason = 'Expiry'
                THEN ABS((TD.QuantityLevel1 * TD.PriceUsedLevel1)
                    - ISNULL(TD.TotalDiscountAmount, 0)
                    + ISNULL(TD.ExciseDutyTaxAmount, 0)
                    + ISNULL(TD.Attribute17, 0))
                ELSE 0 END) AS TotalExpirySales

        FROM tblTrxHeader TH WITH(NOLOCK)
        INNER JOIN tblTrxDetail TD WITH(NOLOCK) ON TD.TrxCode = TH.TrxCode
        WHERE TH.TRXStatus = 200
          AND CAST(TH.TrxDate AS DATE) >= %s
          AND CAST(TH.TrxDate AS DATE) < %s
        GROUP BY
            TH.ClientCode,
            CAST(TH.TrxDate AS DATE),
            TH.RouteCode,
            TD.ItemCode,
            TH.UserCode
    """
    columns = [
        'route_code', 'user_code', 'customer_code', 'item_code',
        'date', 'total_qty', 'total_gr_qty', 'total_damage_qty', 'total_expiry_qty',
        'total_sales', 'total_gr_sales', 'total_damage_sales', 'total_expiry_sales'
    ]

    # Process in 14-day chunks — raw TH+TD JOIN is large; chunking avoids MSSQL tempdb overflow
    from datetime import datetime as _dt
    start = _dt.strptime(DATE_FROM, '%Y-%m-%d').date()
    end   = _dt.strptime(DATE_TO,   '%Y-%m-%d').date()
    chunk_days = 14
    grand_total = 0
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_days), end)
        log(f"    RSIC chunk {chunk_start} → {chunk_end}...")
        # DELETE the chunk window then INSERT fresh (safe for aggregate table — no stable PK)
        pg_cur = pg_conn.cursor()
        pg_cur.execute(
            "DELETE FROM rpt_route_sales_by_item_customer WHERE date >= %s AND date < %s",
            (str(chunk_start), str(chunk_end))
        )
        pg_conn.commit()
        pg_cur.close()

        ms_cur = ms_conn.cursor()
        chunk_total = extract_batch(
            ms_cur, query, (str(chunk_start), str(chunk_end)),
            pg_conn, 'rpt_route_sales_by_item_customer', columns
        )
        ms_cur.close()
        grand_total += chunk_total
        log(f"    {chunk_start} → {chunk_end}: {chunk_total:,} rows")
        chunk_start = chunk_end

    progress.finish_step(grand_total)


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
# USER TABLES SYNC (tblUser, tblUserDetails, tblUserRole)
# These are the authoritative source for hierarchy and role data.
# Synced fresh every ETL run — full replace, no date filter.
# ============================================================

def _mssql_to_pg_type(mssql_type, max_length, precision, scale):
    t = (mssql_type or '').lower().strip()
    if t in ('nvarchar', 'varchar', 'nchar', 'char', 'sysname'):
        if max_length is None or max_length <= 0 or max_length == -1:
            return 'TEXT'
        return 'VARCHAR({})'.format(max_length)
    if t in ('int', 'integer'):        return 'INTEGER'
    if t == 'bigint':                  return 'BIGINT'
    if t in ('smallint', 'tinyint'):   return 'SMALLINT'
    if t == 'bit':                     return 'BOOLEAN'
    if t in ('decimal', 'numeric'):
        p = precision if precision and precision > 0 else 18
        s = scale if scale is not None and scale >= 0 else 4
        return 'NUMERIC({},{})'.format(p, s)
    if t == 'money':                   return 'NUMERIC(19,4)'
    if t == 'smallmoney':              return 'NUMERIC(10,4)'
    if t in ('float', 'real'):         return 'DOUBLE PRECISION'
    if t in ('datetime', 'datetime2', 'smalldatetime'): return 'TIMESTAMP'
    if t == 'date':                    return 'DATE'
    if t == 'time':                    return 'TIME'
    if t in ('text', 'ntext', 'xml', 'sql_variant', 'uniqueidentifier'): return 'TEXT'
    if t in ('image', 'varbinary', 'binary'): return 'BYTEA'
    return 'TEXT'


def _coerce_user_val(val, pg_type):
    if val is None:
        return None
    if 'boolean' in pg_type.lower():
        return bool(val)
    if 'bytea' in pg_type.lower():
        return psycopg2.Binary(val)
    return val


def sync_user_tables(ms_conn, pg_conn):
    """Sync tblUser, tblUserDetails, tblUserRole from MSSQL → PostgreSQL.
    Full replace each run — these tables are small (<2K rows) and drive the
    entire hierarchy / filter / auth system.
    """
    TABLES = [
        ('tblUserRole',    'tbl_user_role'),
        ('tblUser',        'tbl_user'),
        ('tblUserDetails', 'tbl_user_details'),
    ]

    progress.start_step('user_tables (tblUser + tblUserRole + tblUserDetails)', expected_rows=4000)
    ms_cur = ms_conn.cursor()
    pg_cur = pg_conn.cursor()
    total = 0

    for ms_table, pg_table in TABLES:
        # Get column definitions from MSSQL
        ms_cur.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,"
            "       NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE"
            " FROM INFORMATION_SCHEMA.COLUMNS"
            " WHERE TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
            (ms_table,)
        )
        cols = ms_cur.fetchall()
        if not cols:
            log_warn(f"    {ms_table}: no columns found — skipping")
            continue

        col_names_ms = [c[0] for c in cols]
        col_names_pg = ['"{}"'.format(c.lower()) for c in col_names_ms]
        pg_types = [_mssql_to_pg_type(c[1], c[2], c[3], c[4]) for c in cols]

        # Build CREATE TABLE DDL
        col_defs = []
        for c in cols:
            name = '"{}"'.format(c[0].lower())
            typ  = _mssql_to_pg_type(c[1], c[2], c[3], c[4])
            null = '' if c[5] == 'YES' else ' NOT NULL'
            col_defs.append('    {} {}{}'.format(name, typ, null))

        # Drop + create
        pg_cur.execute('DROP TABLE IF EXISTS {} CASCADE'.format(pg_table))
        pg_cur.execute('CREATE TABLE {} (\n{}\n)'.format(pg_table, ',\n'.join(col_defs)))
        pg_conn.commit()

        # Read from MSSQL
        ms_cur.execute('SELECT * FROM [{}]'.format(ms_table))
        rows = ms_cur.fetchall()

        if rows:
            data = []
            for row in rows:
                data.append(tuple(
                    _coerce_user_val(row[i], pg_types[i])
                    for i in range(len(col_names_ms))
                ))
            insert_sql = 'INSERT INTO {} ({}) VALUES %s'.format(
                pg_table, ', '.join(col_names_pg)
            )
            execute_values(pg_cur, insert_sql, data, page_size=500)
            pg_conn.commit()

        total += len(rows)
        log(f"    {ms_table} → {pg_table}: {len(rows)} rows")

    pg_cur.close()
    progress.finish_step(total)


# ============================================================
# MAIN
# ============================================================

ALL_STEPS = [
    ('user_tables',                  sync_user_tables),
    ('dimensions',                   load_dimensions),
    ('dim_item',                     None),  # handled inside load_dimensions
    ('dim_customer',                 None),  # handled inside load_dimensions
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
    ('sales_detail',                 load_sales_detail),
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
        DATE_TO = (_date.today() + timedelta(days=1)).strftime('%Y-%m-%d')  # exclusive — includes today
        UPSERT_MODE = True  # --days always uses upsert (no delete)
    else:
        DATE_FROM = args.from_date
        DATE_TO = args.to_date

    if args.upsert:
        UPSERT_MODE = True

    log(f"{'═' * 60}")
    log(f"  NFPC Reports ETL")
    display_to = (_date.fromisoformat(DATE_TO) - timedelta(days=1)).strftime('%Y-%m-%d')
    log(f"  Date range: {DATE_FROM} to {display_to} (inclusive)")
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
