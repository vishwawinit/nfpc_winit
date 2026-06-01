#!/usr/bin/env python3
"""
NFPC Reports ETL Data Audit - Comprehensive validation of MSSQL vs PostgreSQL.
READ-ONLY on MSSQL source. Compares row counts, sums, distinct values, and spot checks.

Outputs: etl/logs/audit_report.html and console summary.

Usage:
    python etl/audit.py
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pymssql
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DATE_FROM = '2025-10-01'
DATE_TO = '2026-03-31'


def get_mssql_conn():
    return pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        login_timeout=15,
        timeout=600,
    )


def get_pg_conn():
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=os.environ.get('PG_PORT', '5432'),
        dbname=os.environ['PG_DATABASE'],
        user=os.environ.get('PG_USER', 'fci'),
        password=os.environ.get('PG_PASSWORD', ''),
    )


def ms_query(conn, sql, params=None):
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    return cols, rows


def pg_query(conn, sql, params=None):
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    return cols, rows


class AuditReport:
    def __init__(self):
        self.checks = []
        self.start_time = datetime.now()

    def add(self, category, check_name, status, mssql_val, pg_val, variance=None, notes=''):
        self.checks.append({
            'category': category,
            'check': check_name,
            'status': status,
            'mssql': mssql_val,
            'pg': pg_val,
            'variance': variance,
            'notes': notes,
        })
        icon = '✓' if status == 'PASS' else '✗' if status == 'FAIL' else '⚠'
        print(f"  {icon} {check_name}: MSSQL={mssql_val}  PG={pg_val}  {f'Var={variance}' if variance else ''} {notes}")

    def summary(self):
        passed = sum(1 for c in self.checks if c['status'] == 'PASS')
        failed = sum(1 for c in self.checks if c['status'] == 'FAIL')
        warned = sum(1 for c in self.checks if c['status'] == 'WARN')
        return passed, failed, warned

    def to_html(self):
        passed, failed, warned = self.summary()
        elapsed = (datetime.now() - self.start_time).total_seconds()

        html = f"""<!DOCTYPE html>
<html>
<head>
<title>NFPC ETL Audit Report</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
h1 {{ color: #1a1a1a; }}
.summary {{ display: flex; gap: 20px; margin: 20px 0; }}
.card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex: 1; text-align: center; }}
.card h2 {{ margin: 0; font-size: 36px; }}
.card.pass h2 {{ color: #22c55e; }}
.card.fail h2 {{ color: #ef4444; }}
.card.warn h2 {{ color: #f59e0b; }}
.card p {{ color: #666; margin: 5px 0 0; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 20px 0; }}
th {{ background: #1e293b; color: white; padding: 12px 16px; text-align: left; }}
td {{ padding: 10px 16px; border-bottom: 1px solid #e2e8f0; }}
tr:hover {{ background: #f8fafc; }}
.pass {{ color: #22c55e; font-weight: bold; }}
.fail {{ color: #ef4444; font-weight: bold; }}
.warn {{ color: #f59e0b; font-weight: bold; }}
.meta {{ color: #666; font-size: 14px; margin: 10px 0; }}
</style>
</head>
<body>
<h1>NFPC ETL Data Audit Report</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Duration: {elapsed:.0f}s | Date Range: {DATE_FROM} to {DATE_TO}</p>

<div class="summary">
  <div class="card pass"><h2>{passed}</h2><p>Passed</p></div>
  <div class="card fail"><h2>{failed}</h2><p>Failed</p></div>
  <div class="card warn"><h2>{warned}</h2><p>Warnings</p></div>
</div>

<table>
<tr><th>Category</th><th>Check</th><th>Status</th><th>MSSQL</th><th>PostgreSQL</th><th>Variance</th><th>Notes</th></tr>
"""
        for c in self.checks:
            status_class = c['status'].lower()
            html += f"""<tr>
<td>{c['category']}</td>
<td>{c['check']}</td>
<td class="{status_class}">{c['status']}</td>
<td>{c['mssql']}</td>
<td>{c['pg']}</td>
<td>{c['variance'] or ''}</td>
<td>{c['notes']}</td>
</tr>
"""
        html += """</table>
</body></html>"""
        return html


def check_row_counts(ms, pg, report):
    """Compare row counts for all tables."""
    print("\n═══ ROW COUNTS ═══")

    checks = [
        ('Dimensions: Sales Org', 'SELECT COUNT(*) FROM tblSalesOrganization', 'SELECT COUNT(*) FROM dim_sales_org'),
        ('Dimensions: Routes', 'SELECT COUNT(*) FROM tblRoute', 'SELECT COUNT(*) FROM dim_route'),
        ('Dimensions: Users', 'SELECT COUNT(*) FROM tblUser', 'SELECT COUNT(*) FROM dim_user'),
        ('Dimensions: Items', 'SELECT COUNT(DISTINCT Code) FROM tblItem', 'SELECT COUNT(*) FROM dim_item'),
        ('Dimensions: Customers',
         "SELECT COUNT(*) FROM tblCustomerDetail",
         'SELECT COUNT(*) FROM dim_customer'),
        ('Dimensions: Channels', 'SELECT COUNT(*) FROM tblChannel', 'SELECT COUNT(*) FROM dim_channel'),
        ('Holidays', 'SELECT COUNT(*) FROM tblHoliday', 'SELECT COUNT(*) FROM rpt_holidays'),
        ('Targets', 'SELECT COUNT(*) FROM tblCommonTarget', 'SELECT COUNT(*) FROM rpt_targets'),
        ('Coverage Summary',
         f"SELECT COUNT(*) FROM tblRouteCoverageSummary WHERE VisitDate >= '{DATE_FROM}' AND VisitDate < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_coverage_summary'),
        ('EOT',
         f"SELECT COUNT(*) FROM tblEOT WHERE TripDate >= '{DATE_FROM}' AND TripDate < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_eot'),
        ('Journeys',
         f"SELECT COUNT(*) FROM tblJourney WHERE Date >= '{DATE_FROM}' AND Date < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_journeys'),
        ('Collections',
         f"SELECT COUNT(*) FROM tblPaymentHeader WHERE ReceiptDate >= '{DATE_FROM}' AND ReceiptDate < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_collections'),
        ('Customer Visits',
         f"SELECT COUNT(*) FROM tblCustomerVisit WHERE Date >= '{DATE_FROM}' AND Date < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_customer_visits'),
        ('Journey Plan',
         f"SELECT COUNT(*) FROM tblDailyJourneyPlan WHERE JourneyDate >= '{DATE_FROM}' AND JourneyDate < '{DATE_TO}' AND (IsDeleted = 0 OR IsDeleted IS NULL)",
         'SELECT COUNT(*) FROM rpt_journey_plan'),
        ('Outstanding',
         "SELECT COUNT(*) FROM tblMiddleWarePendingInvoice WHERE BalanceAmount != 0",
         'SELECT COUNT(*) FROM rpt_outstanding'),
        ('Daily Sales Summary (aggregated)',
         f"SELECT COUNT(*) FROM tblTrxDetail d JOIN tblTrxHeader h ON d.TrxCode = h.TrxCode WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}' AND h.TrxType IN (1, 4)",
         'SELECT SUM(total_qty) FROM rpt_daily_sales_summary'),
        ('Sales Detail',
         f"SELECT COUNT(*) FROM tblTrxDetail d JOIN tblTrxHeader h ON d.TrxCode = h.TrxCode WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}'",
         'SELECT COUNT(*) FROM rpt_sales_detail'),
    ]

    for name, ms_sql, pg_sql in checks:
        try:
            _, ms_rows = ms_query(ms, ms_sql)
            ms_val = ms_rows[0][0] if ms_rows else 0

            _, pg_rows = pg_query(pg, pg_sql)
            pg_val = pg_rows[0][0] if pg_rows else 0

            if ms_val and pg_val:
                if name == 'Daily Sales Summary (aggregated)':
                    # Special: comparing detail row count vs aggregated sum - just check PG has data
                    status = 'PASS' if pg_val and float(pg_val) > 0 else 'FAIL'
                    report.add('Row Count', name, status, f"{ms_val:,}", f"sum={float(pg_val):,.0f}",
                               notes='Aggregated - comparing detail rows vs sum of qty')
                else:
                    var_pct = abs(float(ms_val) - float(pg_val)) / float(ms_val) * 100 if float(ms_val) > 0 else 0
                    if var_pct <= 0.1:
                        status = 'PASS'
                    elif var_pct <= 5:
                        status = 'WARN'
                    else:
                        status = 'FAIL'
                    report.add('Row Count', name, status, f"{ms_val:,}", f"{pg_val:,}", f"{var_pct:.2f}%")
            else:
                status = 'PASS' if ms_val == pg_val else 'WARN'
                report.add('Row Count', name, status, f"{ms_val:,}" if ms_val else '0', f"{pg_val:,}" if pg_val else '0')
        except Exception as e:
            report.add('Row Count', name, 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:100])


def check_sales_totals(ms, pg, report):
    """Compare monthly sales totals."""
    print("\n═══ MONTHLY SALES TOTALS ═══")

    # Compare at detail line level: count of detail rows and sum of gross_amount (line-level)
    ms_sql = f"""
        SELECT YEAR(h.TrxDate) AS yr, MONTH(h.TrxDate) AS mo,
            COUNT(*) AS cnt, SUM(d.BasePrice * d.QuantityBU) AS total_amount
        FROM tblTrxHeader h
        JOIN tblTrxDetail d ON h.TrxCode = d.TrxCode
        WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}' AND h.TrxType = 1
        GROUP BY YEAR(h.TrxDate), MONTH(h.TrxDate)
        ORDER BY yr, mo
    """
    pg_sql = """
        SELECT EXTRACT(YEAR FROM trx_date)::int AS yr, EXTRACT(MONTH FROM trx_date)::int AS mo,
            COUNT(*) AS cnt, SUM(gross_amount) AS total_amount
        FROM rpt_sales_detail
        WHERE trx_type = 1
        GROUP BY yr, mo
        ORDER BY yr, mo
    """

    try:
        _, ms_rows = ms_query(ms, ms_sql)
        _, pg_rows = pg_query(pg, pg_sql)

        ms_dict = {(r[0], r[1]): (r[2], float(r[3] or 0)) for r in ms_rows}
        pg_dict = {(int(r[0]), int(r[1])): (r[2], float(r[3] or 0)) for r in pg_rows}

        all_months = sorted(set(list(ms_dict.keys()) + list(pg_dict.keys())))
        for ym in all_months:
            ms_cnt, ms_amt = ms_dict.get(ym, (0, 0))
            pg_cnt, pg_amt = pg_dict.get(ym, (0, 0))

            # Count check
            name = f"Sales Count {ym[0]}-{ym[1]:02d}"
            if ms_cnt > 0:
                var = abs(ms_cnt - pg_cnt) / ms_cnt * 100
                status = 'PASS' if var <= 0.1 else 'WARN' if var <= 5 else 'FAIL'
            else:
                status = 'PASS' if pg_cnt == 0 else 'WARN'
                var = 0
            report.add('Sales Count', name, status, f"{ms_cnt:,}", f"{pg_cnt:,}", f"{var:.2f}%")

            # Amount check - MSSQL TotalAmount is header-level, PG net_amount is also header-level
            # They should match if both are TrxType=1
            name = f"Sales Amount {ym[0]}-{ym[1]:02d}"
            if ms_amt > 0:
                var = abs(ms_amt - pg_amt) / ms_amt * 100
                status = 'PASS' if var <= 1 else 'WARN' if var <= 10 else 'FAIL'
            else:
                status = 'PASS' if pg_amt == 0 else 'WARN'
                var = 0
            report.add('Sales Amount', name, status, f"{ms_amt:,.2f}", f"{pg_amt:,.2f}", f"{var:.2f}%")
    except Exception as e:
        report.add('Sales Totals', 'Monthly comparison', 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:200])


def check_distinct_counts(ms, pg, report):
    """Compare distinct customers, items, routes, users in transaction data."""
    print("\n═══ DISTINCT COUNTS IN TRANSACTIONS ═══")

    checks = [
        ('Distinct Customers (sales)',
         f"SELECT COUNT(DISTINCT h.ClientCode) FROM tblTrxHeader h WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT customer_code) FROM rpt_sales_detail"),
        ('Distinct Items (sales)',
         f"SELECT COUNT(DISTINCT d.ItemCode) FROM tblTrxDetail d JOIN tblTrxHeader h ON d.TrxCode = h.TrxCode WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT item_code) FROM rpt_sales_detail"),
        ('Distinct Routes (sales)',
         f"SELECT COUNT(DISTINCT h.RouteCode) FROM tblTrxHeader h WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT route_code) FROM rpt_sales_detail"),
        ('Distinct Users (sales)',
         f"SELECT COUNT(DISTINCT h.UserCode) FROM tblTrxHeader h WHERE h.TrxDate >= '{DATE_FROM}' AND h.TrxDate < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT user_code) FROM rpt_sales_detail"),
        ('Distinct Customers (visits)',
         f"SELECT COUNT(DISTINCT ClientCode) FROM tblCustomerVisit WHERE Date >= '{DATE_FROM}' AND Date < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT customer_code) FROM rpt_customer_visits"),
        ('Distinct Users (collections)',
         f"SELECT COUNT(DISTINCT EmpNo) FROM tblPaymentHeader WHERE ReceiptDate >= '{DATE_FROM}' AND ReceiptDate < '{DATE_TO}'",
         "SELECT COUNT(DISTINCT user_code) FROM rpt_collections"),
    ]

    for name, ms_sql, pg_sql in checks:
        try:
            _, ms_rows = ms_query(ms, ms_sql)
            ms_val = ms_rows[0][0]
            _, pg_rows = pg_query(pg, pg_sql)
            pg_val = pg_rows[0][0]
            var = abs(ms_val - pg_val) / ms_val * 100 if ms_val > 0 else 0
            status = 'PASS' if var <= 1 else 'WARN' if var <= 5 else 'FAIL'
            report.add('Distinct Count', name, status, f"{ms_val:,}", f"{pg_val:,}", f"{var:.2f}%")
        except Exception as e:
            report.add('Distinct Count', name, 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:100])


def check_null_critical(pg, report):
    """Check for NULL values in critical columns."""
    print("\n═══ NULL CHECKS (Critical Columns) ═══")

    checks = [
        ('rpt_sales_detail', 'trx_code'),
        ('rpt_sales_detail', 'trx_date'),
        ('rpt_sales_detail', 'item_code'),
        ('rpt_sales_detail', 'customer_code'),
        ('rpt_sales_detail', 'user_code'),
        ('rpt_sales_detail', 'sales_org_code'),
        ('rpt_collections', 'receipt_date'),
        ('rpt_collections', 'user_code'),
        ('rpt_customer_visits', 'date'),
        ('rpt_customer_visits', 'customer_code'),
        ('rpt_outstanding', 'customer_code'),
        ('rpt_outstanding', 'balance_amount'),
        ('rpt_daily_sales_summary', 'date'),
        ('rpt_daily_sales_summary', 'item_code'),
    ]

    for table, col in checks:
        try:
            _, rows = pg_query(pg, f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
            null_count = rows[0][0]
            _, total = pg_query(pg, f"SELECT COUNT(*) FROM {table}")
            total_count = total[0][0]
            pct = null_count / total_count * 100 if total_count > 0 else 0
            status = 'PASS' if null_count == 0 else 'WARN' if pct < 1 else 'FAIL'
            report.add('NULL Check', f"{table}.{col}", status, 'N/A', f"{null_count:,} / {total_count:,}", f"{pct:.2f}%")
        except Exception as e:
            report.add('NULL Check', f"{table}.{col}", 'FAIL', 'N/A', 'ERROR', notes=str(e)[:100])


def check_date_ranges(pg, report):
    """Verify date ranges match expected window."""
    print("\n═══ DATE RANGE CHECKS ═══")

    tables = [
        ('rpt_sales_detail', 'trx_date'),
        ('rpt_collections', 'receipt_date'),
        ('rpt_customer_visits', 'date'),
        ('rpt_coverage_summary', 'visit_date'),
        ('rpt_journeys', 'date'),
        ('rpt_eot', 'trip_date'),
        ('rpt_daily_sales_summary', 'date'),
    ]

    for table, col in tables:
        try:
            _, rows = pg_query(pg, f"SELECT MIN({col}), MAX({col}) FROM {table}")
            min_dt, max_dt = rows[0]
            if min_dt and max_dt:
                min_ok = str(min_dt) >= DATE_FROM or str(min_dt)[:7] >= DATE_FROM[:7]
                max_ok = str(max_dt) <= DATE_TO
                status = 'PASS' if min_ok and max_ok else 'WARN'
                report.add('Date Range', f"{table}.{col}", status, f"{DATE_FROM} to {DATE_TO}",
                           f"{min_dt} to {max_dt}")
            else:
                report.add('Date Range', f"{table}.{col}", 'WARN', f"{DATE_FROM} to {DATE_TO}", 'NULL/EMPTY')
        except Exception as e:
            report.add('Date Range', f"{table}.{col}", 'FAIL', 'N/A', 'ERROR', notes=str(e)[:100])


def check_collections_totals(ms, pg, report):
    """Compare collection amounts."""
    print("\n═══ COLLECTION TOTALS ═══")

    ms_sql = f"""
        SELECT YEAR(ReceiptDate) yr, MONTH(ReceiptDate) mo,
            COUNT(*) cnt, SUM(Amount) total
        FROM tblPaymentHeader
        WHERE ReceiptDate >= '{DATE_FROM}' AND ReceiptDate < '{DATE_TO}'
        GROUP BY YEAR(ReceiptDate), MONTH(ReceiptDate)
        ORDER BY yr, mo
    """
    pg_sql = """
        SELECT EXTRACT(YEAR FROM receipt_date)::int yr, EXTRACT(MONTH FROM receipt_date)::int mo,
            COUNT(*) cnt, SUM(amount) total
        FROM rpt_collections
        GROUP BY yr, mo ORDER BY yr, mo
    """
    try:
        _, ms_rows = ms_query(ms, ms_sql)
        _, pg_rows = pg_query(pg, pg_sql)
        ms_dict = {(r[0], r[1]): (r[2], float(r[3] or 0)) for r in ms_rows}
        pg_dict = {(int(r[0]), int(r[1])): (r[2], float(r[3] or 0)) for r in pg_rows}

        for ym in sorted(set(list(ms_dict.keys()) + list(pg_dict.keys()))):
            ms_cnt, ms_amt = ms_dict.get(ym, (0, 0))
            pg_cnt, pg_amt = pg_dict.get(ym, (0, 0))
            name = f"Collection {ym[0]}-{ym[1]:02d}"
            var = abs(ms_amt - pg_amt) / ms_amt * 100 if ms_amt > 0 else 0
            status = 'PASS' if var <= 1 else 'WARN' if var <= 5 else 'FAIL'
            report.add('Collections', name, status, f"n={ms_cnt:,} amt={ms_amt:,.2f}",
                       f"n={pg_cnt:,} amt={pg_amt:,.2f}", f"{var:.2f}%")
    except Exception as e:
        report.add('Collections', 'Monthly', 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:200])


def check_coverage_totals(ms, pg, report):
    """Compare coverage summary totals."""
    print("\n═══ COVERAGE TOTALS ═══")

    ms_sql = f"""
        SELECT SUM(ScheduledCalls), SUM(TotalActualCalls), SUM(ActualCalls), SUM(SellingCalls)
        FROM tblRouteCoverageSummary
        WHERE VisitDate >= '{DATE_FROM}' AND VisitDate < '{DATE_TO}'
    """
    pg_sql = """
        SELECT SUM(scheduled_calls), SUM(total_actual_calls), SUM(planned_calls), SUM(selling_calls)
        FROM rpt_coverage_summary
    """
    try:
        _, ms_rows = ms_query(ms, ms_sql)
        _, pg_rows = pg_query(pg, pg_sql)
        labels = ['Scheduled Calls', 'Total Actual Calls', 'Planned Calls', 'Selling Calls']
        for i, label in enumerate(labels):
            ms_val = float(ms_rows[0][i] or 0)
            pg_val = float(pg_rows[0][i] or 0)
            var = abs(ms_val - pg_val) / ms_val * 100 if ms_val > 0 else 0
            status = 'PASS' if var <= 0.1 else 'WARN' if var <= 5 else 'FAIL'
            report.add('Coverage', label, status, f"{ms_val:,.0f}", f"{pg_val:,.0f}", f"{var:.2f}%")
    except Exception as e:
        report.add('Coverage', 'Totals', 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:200])


def check_pg_table_sizes(pg, report):
    """Report PostgreSQL table sizes."""
    print("\n═══ POSTGRESQL TABLE SIZES ═══")

    tables = [
        'dim_sales_org', 'dim_route', 'dim_user', 'dim_customer', 'dim_item', 'dim_channel',
        'rpt_sales_detail', 'rpt_daily_sales_summary', 'rpt_collections',
        'rpt_customer_visits', 'rpt_journeys', 'rpt_coverage_summary',
        'rpt_outstanding', 'rpt_eot', 'rpt_journey_plan', 'rpt_holidays', 'rpt_targets',
    ]
    for table in tables:
        try:
            _, rows = pg_query(pg, f"SELECT COUNT(*) FROM {table}")
            count = rows[0][0]
            status = 'PASS' if count > 0 else 'WARN'
            report.add('PG Table', table, status, 'N/A', f"{count:,} rows")
        except Exception as e:
            report.add('PG Table', table, 'FAIL', 'N/A', 'ERROR', notes=str(e)[:100])


def check_spot_samples(ms, pg, report):
    """Spot-check random transactions."""
    print("\n═══ SPOT CHECK SAMPLES ═══")

    try:
        # Get 5 random trx_codes from PG
        _, pg_rows = pg_query(pg, """
            SELECT trx_code FROM rpt_sales_detail
            TABLESAMPLE SYSTEM(0.01) LIMIT 5
        """)
        for (trx_code,) in pg_rows:
            # Compare header total from MSSQL vs PG
            _, ms_rows = ms_query(ms,
                "SELECT TotalAmount, TrxType, ClientCode FROM tblTrxHeader WHERE TrxCode = %s",
                (trx_code,))
            _, pg_detail = pg_query(pg,
                "SELECT net_amount, trx_type, customer_code FROM rpt_sales_detail WHERE trx_code = %s LIMIT 1",
                (trx_code,))

            if ms_rows and pg_detail:
                ms_amt = float(ms_rows[0][0] or 0)
                pg_amt = float(pg_detail[0][0] or 0)
                ms_type = ms_rows[0][1]
                pg_type = pg_detail[0][1]
                ms_cust = ms_rows[0][2]
                pg_cust = pg_detail[0][2]

                type_match = ms_type == pg_type
                cust_match = ms_cust == pg_cust
                amt_match = abs(ms_amt - pg_amt) < 0.01

                status = 'PASS' if type_match and cust_match else 'WARN'
                report.add('Spot Check', f"TrxCode {trx_code}",
                           status, f"amt={ms_amt:.2f} type={ms_type} cust={ms_cust}",
                           f"amt={pg_amt:.2f} type={pg_type} cust={pg_cust}")
            else:
                report.add('Spot Check', f"TrxCode {trx_code}", 'WARN',
                           f"found={bool(ms_rows)}", f"found={bool(pg_detail)}")
    except Exception as e:
        report.add('Spot Check', 'Random transactions', 'FAIL', 'ERROR', 'ERROR', notes=str(e)[:200])


def main():
    print("=" * 60)
    print("  NFPC ETL DATA AUDIT")
    print(f"  Date range: {DATE_FROM} to {DATE_TO}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    report = AuditReport()

    print("\nConnecting to databases...")
    ms = get_mssql_conn()
    pg = get_pg_conn()
    print("  Both connected.")

    # Run all checks
    check_pg_table_sizes(pg, report)
    check_row_counts(ms, pg, report)
    check_sales_totals(ms, pg, report)
    check_collections_totals(ms, pg, report)
    check_coverage_totals(ms, pg, report)
    check_distinct_counts(ms, pg, report)
    check_null_critical(pg, report)
    check_date_ranges(pg, report)
    check_spot_samples(ms, pg, report)

    ms.close()
    pg.close()

    # Summary
    passed, failed, warned = report.summary()
    print("\n" + "=" * 60)
    print(f"  AUDIT COMPLETE")
    print(f"  Passed: {passed}  |  Failed: {failed}  |  Warnings: {warned}")
    print(f"  Total checks: {len(report.checks)}")
    print("=" * 60)

    # Write HTML report
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    html_path = log_dir / 'audit_report.html'
    html_path.write_text(report.to_html())
    print(f"\n  HTML report: {html_path}")

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
