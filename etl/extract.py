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
from datetime import datetime, timedelta
from pathlib import Path

import pymssql
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Date range: last 6 months
DATE_FROM = '2025-10-01'
DATE_TO = '2026-03-31'

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
# BATCH LOADER
# ============================================================

def extract_batch(ms_cursor, query, params, pg_conn, table, columns, batch_size=10000):
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
    insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES %s ON CONFLICT DO NOTHING"

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

        ('dim_user', "DELETE FROM dim_user",
         "SELECT Code, Description, SalesOrgCode, RouteCode, DepotCode, ReportsTo, UserType, IsActive FROM tblUser",
         "INSERT INTO dim_user (code, name, sales_org_code, route_code, depot_code, reports_to, user_type, is_active) VALUES %s"),

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

    progress.start_step('Dimensions (7 tables)', expected_rows=2000)
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
    progress.finish_step(total)

    # dim_item (needs dedup)
    progress.start_step('dim_item (with group lookups)', expected_rows=5000)
    pg_cur.execute("DELETE FROM dim_item")
    ms_cur.execute("""
        SELECT i.Code, i.Description, i.BaseUOM,
            i.GroupLevel1, g1.Description,
            i.GroupLevel2, g2.Description,
            i.GroupLevel3, g3.Description,
            i.GroupLevel4, g4.Description,
            i.GroupLevel5, g5.Description,
            i.GroupLevel8, g8.Description,
            i.Liter, i.LiterPerUnit, i.IsActive
        FROM tblItem i
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g2 ON i.GroupLevel2 = g2.Code AND g2.ItemGroupLevelId = 2
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        LEFT JOIN tblItemGroup g4 ON i.GroupLevel4 = g4.Code AND g4.ItemGroupLevelId = 4
        LEFT JOIN tblItemGroup g5 ON i.GroupLevel5 = g5.Code AND g5.ItemGroupLevelId = 5
        LEFT JOIN tblItemGroup g8 ON i.GroupLevel8 = g8.Code AND g8.ItemGroupLevelId = 8
    """)
    rows = ms_cur.fetchall()
    seen = set()
    unique_rows = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique_rows.append(r)
    execute_values(pg_cur,
        """INSERT INTO dim_item (code, name, base_uom, brand_code, brand_name, sub_brand_code, sub_brand_name,
           category_code, category_name, sub_category_code, sub_category_name, pack_type_code, pack_type_name,
           segment_code, segment_name, liter, liter_per_unit, is_active) VALUES %s""",
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
    pg_cur.execute("TRUNCATE rpt_sales_detail")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT
            h.TrxCode, d.[LineNo], CAST(h.TrxDate AS DATE), CAST(h.TripDate AS DATE),
            h.TrxType, h.PaymentType,
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
            h.InvoiceNumber, d.CreatedOn
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
        'trx_code', 'line_no', 'trx_date', 'trip_date', 'trx_type', 'payment_type',
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
        'invoice_number', 'created_on'
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
        total = extract_batch(ms_cur, query, (str(chunk_start), str(chunk_end)),
                              pg_conn, 'rpt_sales_detail', columns)
        grand_total += total
        log(f"    {chunk_start} to {chunk_end}: {total:,} rows")
        chunk_start = chunk_end

    pg_cur.close()
    progress.finish_step(grand_total)


def load_daily_sales_summary(ms_conn, pg_conn):
    """Aggregated from tblTrxHeader/Detail - processes month by month to avoid tempdb overflow."""
    progress.start_step('rpt_daily_sales_summary', expected_rows=5_000_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_daily_sales_summary")
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
    pg_cur.execute("TRUNCATE rpt_collections")
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
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_collections', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_customer_visits(ms_conn, pg_conn):
    progress.start_step('rpt_customer_visits', expected_rows=3_000_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_customer_visits")
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
            cv.Latitude, cv.Longitude, cv.JourneyCode
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
        'is_productive', 'is_planned', 'latitude', 'longitude', 'journey_code'
    ]
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_customer_visits', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_journeys(ms_conn, pg_conn):
    progress.start_step('rpt_journeys', expected_rows=80_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_journeys")
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
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_journeys', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_coverage_summary(ms_conn, pg_conn):
    progress.start_step('rpt_coverage_summary', expected_rows=25_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_coverage_summary")
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
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_coverage_summary', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_route_sales_collection(ms_conn, pg_conn):
    progress.start_step('rpt_route_sales_collection', expected_rows=25_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_route_sales_collection")
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
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_route_sales_collection', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_targets(ms_conn, pg_conn):
    progress.start_step('rpt_targets', expected_rows=100)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_targets")
    pg_conn.commit()

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
    columns = [
        'target_id', 'time_frame', 'start_date', 'end_date', 'year', 'month',
        'salesman_code', 'salesman_name', 'route_code', 'route_name', 'sales_org_code',
        'item_key', 'item_name', 'customer_key', 'amount', 'quantity', 'is_active'
    ]
    total = extract_batch(ms_cur, query, None, pg_conn, 'rpt_targets', columns)
    pg_cur.close()
    progress.finish_step(total)


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
    pg_cur.execute("TRUNCATE rpt_outstanding")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    # Simplified query: pull raw JDE dates, convert in Python
    query = """
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
        WHERE mpi.BalanceAmount != 0
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
    insert_sql = f"INSERT INTO rpt_outstanding ({cols_str}) VALUES %s ON CONFLICT DO NOTHING"
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
            days_overdue = (today - trx_date).days if trx_date else 0

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
    pg_cur.execute("TRUNCATE rpt_eot")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT e.EOTId, e.UserCode, u.Description,
            e.RouteCode, rt.Name, e.SalesOrgCode,
            e.EOTType, e.EOTTime, CAST(e.TripDate AS DATE)
        FROM tblEOT e
        LEFT JOIN tblUser u ON e.UserCode = u.Code
        LEFT JOIN tblRoute rt ON e.RouteCode = rt.Code
        WHERE e.TripDate >= %s AND e.TripDate < %s
    """
    columns = [
        'eot_id', 'user_code', 'user_name', 'route_code', 'route_name',
        'sales_org_code', 'eot_type', 'eot_time', 'trip_date'
    ]
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_eot', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_journey_plan(ms_conn, pg_conn):
    progress.start_step('rpt_journey_plan', expected_rows=2_000_000)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_journey_plan")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    query = """
        SELECT jp.DailyJourneyPlanId, CAST(jp.JourneyDate AS DATE),
            jp.UserCode, u.Description, jp.CustomerCode, c.Description,
            rt.Code, jp.Sequence, jp.VisitStatus, u.SalesOrgCode
        FROM tblDailyJourneyPlan jp
        LEFT JOIN tblUser u ON jp.UserCode = u.Code
        LEFT JOIN tblCustomer c ON jp.CustomerCode = c.Code
        LEFT JOIN tblRoute rt ON u.RouteCode = rt.Code
        WHERE jp.JourneyDate >= %s AND jp.JourneyDate < %s
            AND (jp.IsDeleted = 0 OR jp.IsDeleted IS NULL)
    """
    columns = [
        'id', 'date', 'user_code', 'user_name', 'customer_code', 'customer_name',
        'route_code', 'sequence', 'visit_status', 'sales_org_code'
    ]
    total = extract_batch(ms_cur, query, (DATE_FROM, DATE_TO), pg_conn, 'rpt_journey_plan', columns)
    pg_cur.close()
    progress.finish_step(total)


def load_holidays(ms_conn, pg_conn):
    progress.start_step('rpt_holidays', expected_rows=60)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE rpt_holidays")
    pg_conn.commit()

    ms_cur = ms_conn.cursor()
    ms_cur.execute("SELECT HolidayId, CAST(HolidayDate AS DATE), Name, Year, SalesOrgCode FROM tblHoliday WHERE IsActive = 1")
    rows = ms_cur.fetchall()
    if rows:
        execute_values(pg_cur,
            "INSERT INTO rpt_holidays (holiday_id, holiday_date, name, year, sales_org_code) VALUES %s", rows)
    pg_conn.commit()
    pg_cur.close()
    progress.finish_step(len(rows))


# ============================================================
# MAIN
# ============================================================

ALL_STEPS = [
    ('dimensions', load_dimensions),
    ('dim_item', None),  # handled inside load_dimensions
    ('dim_customer', None),  # handled inside load_dimensions
    ('holidays', load_holidays),
    ('targets', load_targets),
    ('coverage_summary', load_coverage_summary),
    ('route_sales_collection', load_route_sales_collection),
    ('eot', load_eot),
    ('journeys', load_journeys),
    ('collections', load_collections),
    ('customer_visits', load_customer_visits),
    ('journey_plan', load_journey_plan),
    ('outstanding', load_outstanding),
    ('daily_sales_summary', load_daily_sales_summary),
    ('sales_detail', load_sales_detail),
]

# Only steps with actual loader functions
LOADABLE_STEPS = [(name, fn) for name, fn in ALL_STEPS if fn is not None]

def main():
    global DATE_FROM, DATE_TO

    parser = argparse.ArgumentParser(description='NFPC Reports ETL')
    parser.add_argument('--table', help='Load a single table only (e.g., sales_detail)')
    parser.add_argument('--dry-run', action='store_true', help='Show plan without executing')
    parser.add_argument('--from-date', default=DATE_FROM, help=f'Start date (default: {DATE_FROM})')
    parser.add_argument('--to-date', default=DATE_TO, help=f'End date (default: {DATE_TO})')
    args = parser.parse_args()

    DATE_FROM = args.from_date
    DATE_TO = args.to_date

    log(f"{'═' * 60}")
    log(f"  NFPC Reports ETL")
    log(f"  Date range: {DATE_FROM} to {DATE_TO}")
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

    progress.start_etl(len(steps))

    ms_conn = get_mssql_conn()
    pg_conn = get_pg_conn()

    failed = []
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
