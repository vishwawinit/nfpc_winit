"""
Diagnostic: compare Daily Sales Overview KPI values with MSSQL SP_SalesOverVieweReport_Part2.
Checks: Prod Minutes, Discount, Total Cash Due, Cash/Credit Sales for March 1 2026.
READ-ONLY access to MSSQL.
"""
import pymssql
import psycopg2
import psycopg2.extras
import os
import sys

# ── connections ──────────────────────────────────────────────────────────────
MS_CONF = dict(server="20.203.45.86", user="nfpc", password="nfpc@!23",
               database="NFPCsfaV3_070326", timeout=60)
PG_URL  = os.environ.get("DATABASE_URL", "")

def pg_connect():
    if not PG_URL:
        raise RuntimeError("DATABASE_URL env var not set")
    return psycopg2.connect(PG_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def ms_connect():
    return pymssql.connect(**MS_CONF)

def pg_one(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or [])
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else {}

def pg_all(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or [])
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]

def ms_one(conn, sql):
    cur = conn.cursor(as_dict=True)
    cur.execute(sql)
    row = cur.fetchone()
    cur.close()
    return row or {}

def ms_all(conn, sql):
    cur = conn.cursor(as_dict=True)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return rows

# ── date to test ──────────────────────────────────────────────────────────────
DATE = "2026-03-01"

print("=" * 70)
print(f"Diagnostic: Daily Sales Overview KPI for {DATE}")
print("=" * 70)

# ── MSSQL SP ──────────────────────────────────────────────────────────────────
print("\n[MSSQL] Running SP_SalesOverVieweReport_Part2 ...")
ms_conn = ms_connect()

# Run the SP with correct parameter order
sp_sql = f"""
EXEC SP_SalesOverVieweReport_Part2
    @Area='',
    @SubArea='',
    @Route='',
    @SalesOrgCode='',
    @Supervisor='',
    @Salesman='',
    @Date='{DATE}',
    @UserCode='admin',
    @StartDate='{DATE}'
"""
cur = ms_conn.cursor(as_dict=True)
cur.execute(sp_sql)
sp_rows = cur.fetchall()
while cur.nextset():
    try:
        more = cur.fetchall()
        if more:
            sp_rows.extend(more)
    except:
        break
cur.close()

sp = sp_rows[0] if sp_rows else {}
print("  SP result keys:", list(sp.keys()) if sp else "(no rows)")
if sp:
    for k, v in sp.items():
        print(f"    {k}: {v}")

# ── MSSQL: count visits & prod minutes directly ───────────────────────────────
print("\n[MSSQL] Direct visit/transaction counts for March 1 ...")

ms_cv_count = ms_one(ms_conn, f"SELECT COUNT(*) AS cnt FROM tblCustomerVisit WHERE CAST(Date AS DATE) = '{DATE}'")
print(f"  tblCustomerVisit rows for {DATE}: {ms_cv_count.get('cnt')}")

ms_cv_visit_code_null = ms_one(ms_conn, f"""
    SELECT COUNT(*) AS cnt FROM tblCustomerVisit
    WHERE CAST(Date AS DATE) = '{DATE}' AND (VisitCode IS NULL OR VisitCode = '')
""")
print(f"  tblCustomerVisit rows with NULL/empty VisitCode: {ms_cv_visit_code_null.get('cnt')}")

# Count distinct VisitCodes in tblTrxHeader that match tblCustomerVisit
ms_prod_check = ms_one(ms_conn, f"""
    SELECT
        COUNT(DISTINCT CV.CustomerVisitId) AS visit_count,
        SUM(CV.TotalTimeInMins) AS prod_mins
    FROM tblCustomerVisit CV
    INNER JOIN (
        SELECT DISTINCT ClientCode, UserCode, VisitCode, TrxDate
        FROM tblTrxHeader
        WHERE CAST(TrxDate AS DATE) BETWEEN '{DATE}' AND '{DATE}'
        AND TrxType IN (1,4) AND TrxStatus=200
    ) TH ON TH.ClientCode = CV.ClientCode
        AND TH.UserCode = CV.UserCode
        AND DATEDIFF(DD, CV.Date, TH.TrxDate) = 0
        AND TH.VisitCode = CV.VisitCode
""")
print(f"  SP-style JOIN result: visit_count={ms_prod_check.get('visit_count')}, prod_mins={ms_prod_check.get('prod_mins')}")

ms_prod_exists = ms_one(ms_conn, f"""
    SELECT
        COUNT(*) AS visit_count,
        SUM(CV.TotalTimeInMins) AS prod_mins
    FROM tblCustomerVisit CV
    WHERE CAST(CV.Date AS DATE) = '{DATE}'
    AND CV.VisitCode IS NOT NULL AND CV.VisitCode != ''
    AND EXISTS (
        SELECT 1 FROM tblTrxHeader TH
        WHERE TH.VisitCode = CV.VisitCode
        AND CAST(TH.TrxDate AS DATE) = '{DATE}'
        AND TH.TrxType IN (1,4) AND TH.TrxStatus=200
    )
""")
print(f"  EXISTS result: visit_count={ms_prod_exists.get('visit_count')}, prod_mins={ms_prod_exists.get('prod_mins')}")

# Check if one CV row matches multiple TH rows (causing double-count)
ms_multi = ms_one(ms_conn, f"""
    SELECT COUNT(*) AS multi_count FROM (
        SELECT CV.CustomerVisitId, COUNT(*) AS match_count
        FROM tblCustomerVisit CV
        INNER JOIN (
            SELECT DISTINCT ClientCode, UserCode, VisitCode, TrxDate
            FROM tblTrxHeader
            WHERE CAST(TrxDate AS DATE) BETWEEN '{DATE}' AND '{DATE}'
            AND TrxType IN (1,4) AND TrxStatus=200
        ) TH ON TH.ClientCode = CV.ClientCode
            AND TH.UserCode = CV.UserCode
            AND DATEDIFF(DD, CV.Date, TH.TrxDate) = 0
            AND TH.VisitCode = CV.VisitCode
        GROUP BY CV.CustomerVisitId
        HAVING COUNT(*) > 1
    ) x
""")
print(f"  CV rows matching >1 TH row (causing double-count): {ms_multi.get('multi_count')}")

# Discount: header-level vs line-level
print("\n[MSSQL] Discount check ...")
ms_disc_header = ms_one(ms_conn, f"""
    SELECT SUM(TotalDiscountAmount) AS disc_header
    FROM tblTrxHeader
    WHERE CAST(TrxDate AS DATE) = '{DATE}'
    AND TrxType IN (1,4) AND TrxStatus=200
""")
print(f"  SUM(TotalDiscountAmount) from tblTrxHeader: {ms_disc_header.get('disc_header')}")

ms_disc_line = ms_one(ms_conn, f"""
    SELECT SUM(d.DiscountAmount) AS disc_line
    FROM tblTrxHeader h
    JOIN tblTrxDetail d ON d.TrxCode = h.TrxCode
    WHERE CAST(h.TrxDate AS DATE) = '{DATE}'
    AND h.TrxType IN (1,4) AND h.TrxStatus=200
""")
print(f"  SUM(DiscountAmount) from tblTrxDetail: {ms_disc_line.get('disc_line')}")

# Total Cash Due
print("\n[MSSQL] Total Cash Due check ...")
ms_mid_pending = ms_one(ms_conn, f"""
    SELECT COUNT(*) AS cnt, SUM(PendingAmount) AS total
    FROM tblMiddlewarePendingInvoice
    WHERE CAST(InvoiceDate AS DATE) = '{DATE}'
""")
print(f"  tblMiddlewarePendingInvoice for {DATE}: cnt={ms_mid_pending.get('cnt')}, total={ms_mid_pending.get('total')}")

ms_pending = ms_one(ms_conn, f"""
    SELECT COUNT(*) AS cnt, SUM(PendingAmount) AS total
    FROM tblPendingInvoice
    WHERE CAST(InvoiceDate AS DATE) = '{DATE}'
""")
print(f"  tblPendingInvoice for {DATE}: cnt={ms_pending.get('cnt')}, total={ms_pending.get('total')}")

ms_conn.close()

# ── PostgreSQL ────────────────────────────────────────────────────────────────
print("\n[PostgreSQL] Checking PG values ...")
pg_conn = pg_connect()

# Visit counts
pg_cv = pg_one(pg_conn, f"SELECT COUNT(*) AS cnt FROM rpt_customer_visits WHERE date = '{DATE}'")
print(f"\n  rpt_customer_visits rows for {DATE}: {pg_cv.get('cnt')}")

pg_cv_null = pg_one(pg_conn, f"""
    SELECT COUNT(*) AS cnt FROM rpt_customer_visits
    WHERE date = '{DATE}' AND (visit_code IS NULL OR visit_code = '')
""")
print(f"  rpt_customer_visits with NULL/empty visit_code: {pg_cv_null.get('cnt')}")

# Prod minutes - current impl (EXISTS)
pg_prod = pg_one(pg_conn, f"""
    SELECT COALESCE(SUM(cv.total_time_mins), 0) AS prod_minutes, COUNT(*) AS visit_count
    FROM rpt_customer_visits cv
    WHERE cv.date = '{DATE}'
    AND cv.visit_code IS NOT NULL AND cv.visit_code != ''
    AND EXISTS (
        SELECT 1 FROM rpt_sales_detail sd
        WHERE sd.visit_code = cv.visit_code
        AND sd.trx_type IN (1, 4) AND sd.trx_status = 200
    )
""")
print(f"\n  PG prod_minutes (EXISTS): {pg_prod.get('prod_minutes')}, visits={pg_prod.get('visit_count')}")

# Prod minutes - SP-style JOIN
pg_prod_join = pg_one(pg_conn, f"""
    SELECT COALESCE(SUM(cv.total_time_mins), 0) AS prod_minutes, COUNT(*) AS visit_count
    FROM rpt_customer_visits cv
    JOIN (
        SELECT DISTINCT visit_code, user_code, customer_code, trx_date::date AS trx_date
        FROM rpt_sales_detail
        WHERE trx_date::date = '{DATE}'
        AND trx_type IN (1,4) AND trx_status = 200
    ) sd ON sd.visit_code = cv.visit_code
        AND sd.user_code = cv.user_code
        AND sd.trx_date = cv.date
""")
print(f"  PG prod_minutes (JOIN replica): {pg_prod_join.get('prod_minutes')}, visits={pg_prod_join.get('visit_count')}")

# Discount
pg_disc = pg_one(pg_conn, f"""
    SELECT COALESCE(SUM(discount_amount), 0) AS discount
    FROM (
        SELECT DISTINCT trx_code, line_no, discount_amount
        FROM rpt_sales_detail
        WHERE trx_type IN (1, 4) AND trx_status = 200
        AND trx_date::date = '{DATE}'
    ) t
""")
print(f"\n  PG discount (line-level dedup): {pg_disc.get('discount')}")

# Check if invoice_totals has discount
pg_disc2 = pg_one(pg_conn, f"""
    SELECT COALESCE(SUM(total_returns), 0) AS total_returns, COALESCE(SUM(total_sales), 0) AS total_sales
    FROM rpt_invoice_totals WHERE trx_date = '{DATE}'
""")
print(f"  rpt_invoice_totals: sales={pg_disc2.get('total_sales')}, returns={pg_disc2.get('total_returns')}")

# Total Cash Due
pg_due = pg_one(pg_conn, f"""
    SELECT COALESCE(SUM(pending_amount), 0) AS total_cash_due, COUNT(*) AS cnt
    FROM rpt_outstanding WHERE trx_date = '{DATE}'
""")
print(f"\n  PG total_cash_due (rpt_outstanding): {pg_due.get('total_cash_due')}, cnt={pg_due.get('cnt')}")

pg_due_total = pg_one(pg_conn, f"SELECT COALESCE(SUM(pending_amount), 0) AS total FROM rpt_outstanding")
print(f"  rpt_outstanding total (all dates): {pg_due_total.get('total')}")

# Check outstanding table structure
pg_out_sample = pg_all(pg_conn, f"SELECT trx_date, COUNT(*) AS cnt, SUM(pending_amount) AS total FROM rpt_outstanding GROUP BY trx_date ORDER BY trx_date DESC LIMIT 5")
print(f"  rpt_outstanding recent dates:")
for r in pg_out_sample:
    print(f"    {r['trx_date']}: cnt={r['cnt']}, total={r['total']}")

# Cash/Credit breakdown
pg_cash_credit = pg_one(pg_conn, f"""
    SELECT
        COALESCE(SUM(CASE WHEN dc.customer_type = 'Cash' THEN r.total_sales ELSE 0 END), 0) AS cash_sales,
        COALESCE(SUM(CASE WHEN dc.customer_type = 'Credit' THEN r.total_sales ELSE 0 END), 0) AS credit_sales,
        COALESCE(SUM(r.total_sales), 0) AS total_sales
    FROM rpt_route_sales_by_item_customer r
    JOIN dim_route dr ON r.route_code = dr.code
    JOIN dim_customer dc ON r.customer_code = dc.code AND dc.sales_org_code = dr.sales_org_code
    WHERE r.date = '{DATE}'
""")
print(f"\n  PG cash={pg_cash_credit.get('cash_sales')}, credit={pg_cash_credit.get('credit_sales')}, total={pg_cash_credit.get('total_sales')}")

# Check visit code coverage: how many SD visit_codes match CV visit_codes
pg_match = pg_one(pg_conn, f"""
    SELECT
        COUNT(DISTINCT sd.visit_code) AS sd_distinct_codes,
        COUNT(DISTINCT cv.visit_code) AS cv_distinct_codes,
        COUNT(DISTINCT CASE WHEN cv.visit_code IS NOT NULL THEN sd.visit_code END) AS matched_codes
    FROM rpt_sales_detail sd
    LEFT JOIN rpt_customer_visits cv ON cv.visit_code = sd.visit_code AND cv.date = sd.trx_date::date
    WHERE sd.trx_date::date = '{DATE}'
    AND sd.trx_type IN (1,4) AND sd.trx_status = 200
    AND sd.visit_code IS NOT NULL AND sd.visit_code != ''
""")
print(f"\n  visit_code match: sd_distinct={pg_match.get('sd_distinct_codes')}, cv_distinct={pg_match.get('cv_distinct_codes')}, matched={pg_match.get('matched_codes')}")

# Find visit_codes in SD that are NOT in CV
pg_missing = pg_one(pg_conn, f"""
    SELECT COUNT(DISTINCT sd.visit_code) AS missing_in_cv
    FROM rpt_sales_detail sd
    WHERE sd.trx_date::date = '{DATE}'
    AND sd.trx_type IN (1,4) AND sd.trx_status = 200
    AND sd.visit_code IS NOT NULL AND sd.visit_code != ''
    AND NOT EXISTS (
        SELECT 1 FROM rpt_customer_visits cv
        WHERE cv.visit_code = sd.visit_code
    )
""")
print(f"  SD visit_codes NOT found in CV at all: {pg_missing.get('missing_in_cv')}")

# Sample missing visit_codes
pg_missing_sample = pg_all(pg_conn, f"""
    SELECT DISTINCT sd.visit_code, sd.user_code, sd.customer_code
    FROM rpt_sales_detail sd
    WHERE sd.trx_date::date = '{DATE}'
    AND sd.trx_type IN (1,4) AND sd.trx_status = 200
    AND sd.visit_code IS NOT NULL AND sd.visit_code != ''
    AND NOT EXISTS (
        SELECT 1 FROM rpt_customer_visits cv
        WHERE cv.visit_code = sd.visit_code
    )
    LIMIT 5
""")
if pg_missing_sample:
    print("  Sample SD visit_codes missing from CV:")
    for r in pg_missing_sample:
        print(f"    visit_code={r['visit_code']}, user={r['user_code']}, customer={r['customer_code']}")

pg_conn.close()

print("\n" + "=" * 70)
print("DONE")
