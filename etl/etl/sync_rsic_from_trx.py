#!/usr/bin/env python3
"""
Sync rpt_route_sales_by_item_customer from raw transactions.
All config comes from .env — no command line args needed.

Usage:
    python sync_rsic_from_trx.py

.env keys used:
    DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME   — MSSQL source (READ-ONLY)
    PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD — PostgreSQL target
    SYNC_FROM_DATE   — start date (default: 2026-01-01)
    SYNC_CHUNK_DAYS  — days per chunk (default: 14)
"""

import os
import sys
import argparse
from datetime import date, timedelta, datetime
from pathlib import Path

import pymssql
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── Config from .env ─────────────────────────────────────────────
DATE_FROM   = os.environ.get('SYNC_FROM_DATE', '2026-01-01')
DATE_TO     = os.environ.get('SYNC_TO_DATE', (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'))
CHUNK_DAYS  = int(os.environ.get('SYNC_CHUNK_DAYS', '14'))

# ── MSSQL query ──────────────────────────────────────────────────
QUERY = """
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

COLUMNS = [
    'route_code', 'user_code', 'customer_code', 'item_code', 'date',
    'total_qty', 'total_gr_qty', 'total_damage_qty', 'total_expiry_qty',
    'total_sales', 'total_gr_sales', 'total_damage_sales', 'total_expiry_sales'
]


def get_mssql_conn():
    return pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        login_timeout=15,
        timeout=1800,
    )


def get_pg_conn():
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=os.environ.get('PG_PORT', '5432'),
        dbname=os.environ['PG_DATABASE'],
        user=os.environ.get('PG_USER', 'postgres'),
        password=os.environ.get('PG_PASSWORD', ''),
    )


def sync_chunk(ms_conn, pg_conn, chunk_start, chunk_end):
    print(f"  {chunk_start} -> {chunk_end} ...", end='', flush=True)

    ms_cur = ms_conn.cursor()
    ms_cur.execute(QUERY, (str(chunk_start), str(chunk_end)))
    rows = ms_cur.fetchall()
    ms_cur.close()

    if not rows:
        print(" 0 rows skipped")
        return 0

    pg_cur = pg_conn.cursor()
    pg_cur.execute(
        "DELETE FROM rpt_route_sales_by_item_customer WHERE date >= %s AND date < %s",
        (str(chunk_start), str(chunk_end))
    )
    execute_values(
        pg_cur,
        f"INSERT INTO rpt_route_sales_by_item_customer ({', '.join(COLUMNS)}) VALUES %s",
        rows,
        page_size=5000
    )
    pg_conn.commit()
    pg_cur.close()
    print(f" {len(rows):,} rows OK")
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', default=DATE_FROM, help='Start date YYYY-MM-DD')
    parser.add_argument('--to-date',   default=DATE_TO,   help='End date YYYY-MM-DD (exclusive)')
    args = parser.parse_args()

    date_from = datetime.strptime(args.from_date, '%Y-%m-%d').date()
    date_to   = datetime.strptime(args.to_date,   '%Y-%m-%d').date()

    print("=" * 60)
    print("  RSIC Sync — rpt_route_sales_by_item_customer")
    print(f"  Source : tblTrxHeader + tblTrxDetail (TRXStatus=200)")
    print(f"  Range  : {DATE_FROM} to {date_to - timedelta(days=1)} (inclusive)")
    print(f"  Chunks : {CHUNK_DAYS} days")
    print(f"  DB     : {os.environ.get('PG_DATABASE')} @ {os.environ.get('PG_HOST')}")
    print("=" * 60)

    print("\nConnecting...")
    try:
        ms_conn = get_mssql_conn()
        pg_conn = get_pg_conn()
        print("  MSSQL + PostgreSQL connected\n")
    except Exception as e:
        print(f"  Connection failed: {e}")
        sys.exit(1)

    total = 0
    chunk_start = date_from
    while chunk_start < date_to:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), date_to)
        try:
            total += sync_chunk(ms_conn, pg_conn, chunk_start, chunk_end)
        except Exception as e:
            print(f"\n  ERROR on {chunk_start}: {e}")
            pg_conn.rollback()
        chunk_start = chunk_end

    ms_conn.close()
    pg_conn.close()

    print(f"\n{'=' * 60}")
    print(f"  DONE — {total:,} total rows loaded")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
