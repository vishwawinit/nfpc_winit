#!/usr/bin/env python3
"""
Coverage metrics comparison for 2026-01-15
Compares:
  1. MSSQL SP logic (computed from raw tables)
  2. MSSQL tblRouteCoverageSummary (stored summary values)
  3. PostgreSQL API logic (from replicated rpt_* tables)

READ-ONLY on MSSQL. All queries are SELECT only.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

TARGET_DATE = '2026-01-15'

# ── Connection helpers ───────────────────────────────────────────────────────

def get_mssql():
    import pymssql
    return pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        timeout=120,
    )

def get_pg():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        host=os.environ['PG_HOST'],
        port=int(os.environ.get('PG_PORT', 5432)),
        dbname=os.environ['PG_DATABASE'],
        user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD'],
        connect_timeout=30,
    )
    return conn

# ── MSSQL queries ────────────────────────────────────────────────────────────

def run_mssql_sp_logic(cur, d):
    """Replicate the SP logic by querying raw MSSQL tables (READ-ONLY SELECT)."""
    results = {}

    # 1. ScheduledCalls
    cur.execute("""
        SELECT COUNT(*) AS scheduled
        FROM (
            SELECT DISTINCT CAST(D.JourneyDate AS DATE) AS JourneyDate, D.UserCode, D.CustomerCode
            FROM tblDailyJourneyPlan D WITH(NOLOCK)
            WHERE CAST(D.JourneyDate AS DATE) = %s
            AND (D.IsDeleted = 0 OR D.IsDeleted IS NULL)
        ) T
    """, (d,))
    results['scheduled_calls'] = cur.fetchone()[0]

    # 2. TotalActualCalls
    cur.execute("""
        SELECT COUNT(*) AS total_actual
        FROM (
            SELECT DISTINCT CAST(CV.[Date] AS DATE) AS [Date], CV.ClientCode, CV.RouteCode
            FROM tblCustomerVisit CV WITH(NOLOCK)
            WHERE CAST(CV.[Date] AS DATE) = %s
        ) T
    """, (d,))
    results['total_actual_calls'] = cur.fetchone()[0]

    # 3. ActualCalls (planned customers that were visited)
    cur.execute("""
        SELECT COUNT(V.ClientCode) AS actual_calls
        FROM (
            SELECT DISTINCT CAST(D.JourneyDate AS DATE) AS JourneyDate, D.UserCode, D.CustomerCode
            FROM tblDailyJourneyPlan D WITH(NOLOCK)
            WHERE CAST(D.JourneyDate AS DATE) = %s
            AND (D.IsDeleted = 0 OR D.IsDeleted IS NULL)
        ) T
        LEFT JOIN (
            SELECT DISTINCT CAST(CV.[Date] AS DATE) AS [Date], CV.ClientCode, CV.RouteCode
            FROM tblCustomerVisit CV WITH(NOLOCK)
            WHERE CAST(CV.[Date] AS DATE) = %s
        ) V ON V.ClientCode = T.CustomerCode AND V.RouteCode = T.UserCode
    """, (d, d))
    results['actual_calls'] = cur.fetchone()[0]

    # 4. SellingCalls
    cur.execute("""
        SELECT COUNT(*) AS selling
        FROM (
            SELECT DISTINCT CAST(TH.TrxDate AS DATE) AS TrxDate, TH.ClientCode, TH.RouteCode
            FROM tblTrxHeader TH WITH(NOLOCK)
            INNER JOIN tblCustomerVisit CV WITH(NOLOCK)
                ON CV.RouteCode = TH.RouteCode
                AND CV.ClientCode = TH.ClientCode
                AND TH.VisitCode = CV.VisitCode
                AND CAST(TH.TrxDate AS DATE) = CAST(CV.[Date] AS DATE)
            WHERE TH.TrxType = 1 AND TH.TrxStatus = 200
            AND CAST(TH.TrxDate AS DATE) = %s
        ) T
    """, (d,))
    results['selling_calls'] = cur.fetchone()[0]

    # 5. PlannedSellingCalls
    cur.execute("""
        SELECT COUNT(*) AS planned_selling
        FROM (
            SELECT DISTINCT CAST(TH.TrxDate AS DATE) AS TrxDate, TH.ClientCode, TH.RouteCode
            FROM tblTrxHeader TH WITH(NOLOCK)
            INNER JOIN tblCustomerVisit CV WITH(NOLOCK)
                ON CV.RouteCode = TH.RouteCode
                AND CV.ClientCode = TH.ClientCode
                AND TH.VisitCode = CV.VisitCode
                AND CAST(TH.TrxDate AS DATE) = CAST(CV.[Date] AS DATE)
            INNER JOIN tblDailyJourneyPlan DJP WITH(NOLOCK)
                ON TH.ClientCode = DJP.CustomerCode
                AND CAST(TH.TrxDate AS DATE) = CAST(DJP.JourneyDate AS DATE)
                AND DJP.UserCode = TH.RouteCode
            WHERE TH.TrxType = 1 AND TH.TrxStatus = 200
            AND CAST(TH.TrxDate AS DATE) = %s
        ) T
    """, (d,))
    results['planned_selling_calls'] = cur.fetchone()[0]

    return results


def run_mssql_summary_table(cur, d):
    """Read stored values from tblRouteCoverageSummary (READ-ONLY SELECT)."""
    cur.execute("""
        SELECT
            SUM(ScheduledCalls)      AS scheduled,
            SUM(TotalActualCalls)    AS total_actual,
            SUM(ActualCalls)         AS actual,
            SUM(SellingCalls)        AS selling,
            SUM(PlannedSellingCalls) AS planned_selling
        FROM tblRouteCoverageSummary WITH(NOLOCK)
        WHERE CAST(VisitDate AS DATE) = %s
    """, (d,))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return {k: 0 for k in
                ['scheduled_calls', 'total_actual_calls', 'actual_calls',
                 'selling_calls', 'planned_selling_calls']}
    return {
        'scheduled_calls':       int(row[0] or 0),
        'total_actual_calls':    int(row[1] or 0),
        'actual_calls':          int(row[2] or 0),
        'selling_calls':         int(row[3] or 0),
        'planned_selling_calls': int(row[4] or 0),
    }


# ── PostgreSQL queries ───────────────────────────────────────────────────────

def run_pg_logic(cur, d):
    """
    Replicate coverage metric logic against PostgreSQL rpt_* tables.

    rpt_journey_plan columns:
        date, user_code (SalesmanCode), route_code (UserCode/route), customer_code

    rpt_customer_visits columns:
        date, customer_code, route_code, is_planned, is_productive, journey_code

    rpt_sales_detail columns:
        trx_date, customer_code, route_code, trx_type, (invoice/trx level)
        Note: no direct VisitCode link — we join by date+customer+route like the summary ETL
    """
    results = {}

    # 1. ScheduledCalls — distinct (date, route_code, customer_code) from journey plan
    cur.execute("""
        SELECT COUNT(*) AS scheduled_calls
        FROM (
            SELECT DISTINCT date, route_code, customer_code
            FROM rpt_journey_plan
            WHERE date = %s
        ) T
    """, (d,))
    results['scheduled_calls'] = cur.fetchone()[0]

    # 2. TotalActualCalls — distinct (date, customer_code, route_code) from visits
    cur.execute("""
        SELECT COUNT(*) AS total_actual_calls
        FROM (
            SELECT DISTINCT date, customer_code, route_code
            FROM rpt_customer_visits
            WHERE date = %s
        ) T
    """, (d,))
    results['total_actual_calls'] = cur.fetchone()[0]

    # 3. ActualCalls — planned customers that were visited (join journey plan to visits)
    cur.execute("""
        SELECT COUNT(V.customer_code) AS actual_calls
        FROM (
            SELECT DISTINCT date, route_code, customer_code
            FROM rpt_journey_plan
            WHERE date = %s
        ) T
        LEFT JOIN (
            SELECT DISTINCT date, customer_code, route_code
            FROM rpt_customer_visits
            WHERE date = %s
        ) V ON V.customer_code = T.customer_code AND V.route_code = T.route_code
    """, (d, d))
    results['actual_calls'] = cur.fetchone()[0]

    # 4. SellingCalls — distinct (date, customer_code, route_code) from sales that have a visit
    #    rpt_sales_detail does not carry VisitCode; use rpt_coverage_summary if available,
    #    otherwise count distinct (trx_date, customer_code, route_code) with trx_type=1
    #    filtered to customers that also appear in rpt_customer_visits on the same date.
    cur.execute("""
        SELECT COUNT(*) AS selling_calls
        FROM (
            SELECT DISTINCT sd.trx_date, sd.customer_code, sd.route_code
            FROM rpt_sales_detail sd
            WHERE sd.trx_date = %s
              AND sd.trx_type = 1
              AND EXISTS (
                  SELECT 1 FROM rpt_customer_visits cv
                  WHERE cv.date = sd.trx_date
                    AND cv.customer_code = sd.customer_code
                    AND cv.route_code = sd.route_code
              )
        ) T
    """, (d,))
    results['selling_calls'] = cur.fetchone()[0]

    # 5. PlannedSellingCalls — selling calls that also have a journey plan entry
    cur.execute("""
        SELECT COUNT(*) AS planned_selling_calls
        FROM (
            SELECT DISTINCT sd.trx_date, sd.customer_code, sd.route_code
            FROM rpt_sales_detail sd
            WHERE sd.trx_date = %s
              AND sd.trx_type = 1
              AND EXISTS (
                  SELECT 1 FROM rpt_customer_visits cv
                  WHERE cv.date = sd.trx_date
                    AND cv.customer_code = sd.customer_code
                    AND cv.route_code = sd.route_code
              )
              AND EXISTS (
                  SELECT 1 FROM rpt_journey_plan jp
                  WHERE jp.date = sd.trx_date
                    AND jp.customer_code = sd.customer_code
                    AND jp.route_code = sd.route_code
              )
        ) T
    """, (d,))
    results['planned_selling_calls'] = cur.fetchone()[0]

    return results


def run_pg_coverage_summary(cur, d):
    """Read stored values from rpt_coverage_summary (PostgreSQL mirror of MSSQL summary table)."""
    cur.execute("""
        SELECT
            COALESCE(SUM(scheduled_calls), 0)      AS scheduled_calls,
            COALESCE(SUM(total_actual_calls), 0)   AS total_actual_calls,
            COALESCE(SUM(planned_calls), 0)        AS actual_calls,
            COALESCE(SUM(selling_calls), 0)        AS selling_calls,
            COALESCE(SUM(planned_selling_calls), 0) AS planned_selling_calls
        FROM rpt_coverage_summary
        WHERE visit_date = %s
    """, (d,))
    row = cur.fetchone()
    if row is None:
        return {k: 0 for k in
                ['scheduled_calls', 'total_actual_calls', 'actual_calls',
                 'selling_calls', 'planned_selling_calls']}
    return {
        'scheduled_calls':       int(row[0]),
        'total_actual_calls':    int(row[1]),
        'actual_calls':          int(row[2]),
        'selling_calls':         int(row[3]),
        'planned_selling_calls': int(row[4]),
    }


# ── Formatting ───────────────────────────────────────────────────────────────

METRICS = [
    ('scheduled_calls',       'Scheduled Calls'),
    ('total_actual_calls',    'Total Actual Calls'),
    ('actual_calls',          'Actual Calls (planned visited)'),
    ('selling_calls',         'Selling Calls'),
    ('planned_selling_calls', 'Planned Selling Calls'),
]

def print_table(mssql_sp, mssql_summary, pg_logic, pg_summary):
    col_w = [32, 14, 14, 14, 14]
    headers = ['Metric', 'MSSQL SP', 'MSSQL Stored', 'PG Logic', 'PG Stored']

    sep = '+' + '+'.join('-' * w for w in col_w) + '+'
    fmt = '|' + '|'.join(f'{{:<{w}}}' for w in col_w) + '|'

    print()
    print(f"  Coverage Metrics Comparison — {TARGET_DATE}")
    print(sep)
    print(fmt.format(*headers))
    print(sep)

    for key, label in METRICS:
        v_ms_sp  = mssql_sp.get(key, 'N/A')
        v_ms_st  = mssql_summary.get(key, 'N/A')
        v_pg_lg  = pg_logic.get(key, 'N/A')
        v_pg_st  = pg_summary.get(key, 'N/A')

        # Flag mismatches
        vals = [v for v in [v_ms_sp, v_ms_st, v_pg_lg, v_pg_st] if isinstance(v, int)]
        mismatch = len(set(vals)) > 1
        marker = ' *' if mismatch else '  '

        row_label = label + marker
        print(fmt.format(
            row_label,
            str(v_ms_sp), str(v_ms_st), str(v_pg_lg), str(v_pg_st)
        ))

    print(sep)
    print("  * = values differ across sources")
    print()

    # Derived coverage %
    print("  Derived Coverage % (Total Actual / Scheduled * 100):")
    for label, sched_k, actual_k, data in [
        ('MSSQL SP',     'scheduled_calls', 'total_actual_calls', mssql_sp),
        ('MSSQL Stored', 'scheduled_calls', 'total_actual_calls', mssql_summary),
        ('PG Logic',     'scheduled_calls', 'total_actual_calls', pg_logic),
        ('PG Stored',    'scheduled_calls', 'total_actual_calls', pg_summary),
    ]:
        s = data.get(sched_k, 0) or 0
        a = data.get(actual_k, 0) or 0
        pct = round(a / s * 100, 2) if s else 0.0
        print(f"    {label:<14}: {a}/{s} = {pct}%")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    d = TARGET_DATE
    print(f"\nConnecting to MSSQL ({os.environ['DB_SERVER']}) ...")
    try:
        ms_conn = get_mssql()
        ms_cur = ms_conn.cursor()
        print("  Connected.")

        print("  Running SP logic queries ...")
        mssql_sp = run_mssql_sp_logic(ms_cur, d)
        print(f"    scheduled={mssql_sp['scheduled_calls']}, "
              f"total_actual={mssql_sp['total_actual_calls']}, "
              f"actual={mssql_sp['actual_calls']}, "
              f"selling={mssql_sp['selling_calls']}, "
              f"planned_selling={mssql_sp['planned_selling_calls']}")

        print("  Reading tblRouteCoverageSummary ...")
        mssql_summary = run_mssql_summary_table(ms_cur, d)
        print(f"    scheduled={mssql_summary['scheduled_calls']}, "
              f"total_actual={mssql_summary['total_actual_calls']}, "
              f"actual={mssql_summary['actual_calls']}, "
              f"selling={mssql_summary['selling_calls']}, "
              f"planned_selling={mssql_summary['planned_selling_calls']}")

        ms_conn.close()
    except Exception as e:
        print(f"  ERROR connecting to MSSQL: {e}", file=sys.stderr)
        mssql_sp = {k: 'ERR' for k, _ in METRICS}
        mssql_summary = {k: 'ERR' for k, _ in METRICS}

    print(f"\nConnecting to PostgreSQL ({os.environ['PG_HOST']}) ...")
    try:
        pg_conn = get_pg()
        pg_cur = pg_conn.cursor()
        print("  Connected.")

        print("  Running PG raw logic queries ...")
        pg_logic = run_pg_logic(pg_cur, d)
        print(f"    scheduled={pg_logic['scheduled_calls']}, "
              f"total_actual={pg_logic['total_actual_calls']}, "
              f"actual={pg_logic['actual_calls']}, "
              f"selling={pg_logic['selling_calls']}, "
              f"planned_selling={pg_logic['planned_selling_calls']}")

        print("  Reading rpt_coverage_summary ...")
        pg_summary = run_pg_coverage_summary(pg_cur, d)
        print(f"    scheduled={pg_summary['scheduled_calls']}, "
              f"total_actual={pg_summary['total_actual_calls']}, "
              f"actual={pg_summary['actual_calls']}, "
              f"selling={pg_summary['selling_calls']}, "
              f"planned_selling={pg_summary['planned_selling_calls']}")

        pg_conn.close()
    except Exception as e:
        print(f"  ERROR connecting to PostgreSQL: {e}", file=sys.stderr)
        pg_logic = {k: 'ERR' for k, _ in METRICS}
        pg_summary = {k: 'ERR' for k, _ in METRICS}

    print_table(mssql_sp, mssql_summary, pg_logic, pg_summary)


if __name__ == '__main__':
    main()
