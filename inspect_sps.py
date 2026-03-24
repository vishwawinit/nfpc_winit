# -*- coding: utf-8 -*-
"""Inspect and test MSSQL SPs vs PG implementation. ASCII-safe output."""
import sys, pymssql, psycopg2
sys.stdout.reconfigure(encoding='utf-8')

MSSQL = dict(server='20.203.45.86', user='nfpc', password='nfpc@!23', database='NFPCsfaV3_070326')
PG    = dict(host='switchback.proxy.rlwy.net', port=31910, dbname='railway',
             user='postgres', password='glzENZuNPmfnAEYrprneXIfVczZAfExC')

def sep(t): print(f"\n{'='*78}\n{t}\n{'='*78}")
def sub(t): print(f"\n  *** {t} ***")

ms = pymssql.connect(**MSSQL)
pg = psycopg2.connect(**PG)
mc = ms.cursor()
pc = pg.cursor()
print("Connected to MSSQL + PostgreSQL")

# ── PG test data ──────────────────────────────────────────────────────────────
pc.execute("SELECT DISTINCT user_code FROM rpt_route_sales_by_item_customer WHERE date BETWEEN '2026-03-01' AND '2026-03-24' LIMIT 5")
active_users = [r[0] for r in pc.fetchall()]
pc.execute("SELECT code, name, sales_org_code FROM dim_route WHERE is_active=true LIMIT 5")
routes = pc.fetchall()
pc.execute("SELECT code FROM dim_sales_org WHERE is_active=true AND code NOT IN ('NFPC','NFPC_OMAN','00999','00000') LIMIT 5")
orgs = [r[0] for r in pc.fetchall()]

TEST_USER  = active_users[0] if active_users else '102607'
TEST_ROUTE = routes[0][0] if routes else 'M01'
TEST_ORG   = routes[0][2] if routes else '00030'
D_FROM, D_TO = '2026-03-01', '2026-03-24'
print(f"Test: user={TEST_USER} route={TEST_ROUTE} org={TEST_ORG}")

# ── Find valid MSSQL salesman codes ───────────────────────────────────────────
sep("MSSQL USER/SALESMAN TABLES")
for tbl in ['SALESMANMASTER','ORGUSERS','tblUser']:
    try:
        mc.execute(f"SELECT TOP 3 * FROM {tbl}")
        cols = [d[0] for d in mc.description]
        rows = mc.fetchall()
        print(f"\n  Table: {tbl}  cols={cols}")
        for r in rows: print(f"    {dict(zip(cols,r))}")
    except Exception as e:
        print(f"  {tbl}: {e}")

# Try to get user codes using same IDs as PG
mc.execute("""SELECT TOP 5 Code, Description FROM tblUser WHERE IsActive=1""")
try:
    ms_users = [(r[0], r[1]) for r in mc.fetchall()]
    print(f"\n  tblUser (Code, Description): {ms_users}")
    MS_USER = ms_users[0][0] if ms_users else TEST_USER
except: MS_USER = TEST_USER

# Try SALESMANMASTER
try:
    mc.execute("SELECT TOP 1 * FROM SALESMANMASTER")
    cols = [d[0] for d in mc.description]
    print(f"\n  SALESMANMASTER cols: {cols}")
    mc.execute("SELECT TOP 3 * FROM SALESMANMASTER")
    for r in mc.fetchall():
        print(f"    {dict(zip(cols,r))}")
    # get code column
    code_col = [c for c in cols if 'code' in c.lower() or 'id' in c.lower()][0] if cols else cols[0]
    mc.execute(f"SELECT TOP 3 {code_col} FROM SALESMANMASTER")
    ms_codes = [r[0] for r in mc.fetchall()]
    print(f"  SALESMANMASTER codes: {ms_codes}")
    MS_USER = ms_codes[0] if ms_codes else MS_USER
except Exception as e:
    print(f"  SALESMANMASTER: {e}")

print(f"\n  Using MS_USER={MS_USER} for SP tests")

# ── SP DEFINITIONS ────────────────────────────────────────────────────────────
sep("SP DEFINITIONS")
SPS = [
    'Usp_GetAllDataForDropDownListsBasedOnFilter',
    'sp_GetMTDSalesOverviewReport_New',
    'sp_MTDSalesPerformanceReportLableDate',
    'sp_GetAllSalesOrgsByUserCode',
    'USP_GetRoutesByUserCode_Filter_CreateOrder',
]
for sp in SPS:
    print(f"\n--- {sp} ---")
    mc.execute("SELECT m.definition FROM sys.objects o JOIN sys.sql_modules m ON o.object_id=m.object_id WHERE o.type='P' AND o.name=%s", (sp,))
    row = mc.fetchone()
    if row:
        txt = row[0].encode('ascii','replace').decode('ascii')
        print(txt[:5000])
        if len(row[0]) > 5000: print(f"[...{len(row[0])-5000} more chars total={len(row[0])}]")
    else:
        print("[not found]")

# ── SP TEST RUNS ──────────────────────────────────────────────────────────────
sep("SP TEST RUNS")

def exec_sp(name, params_str):
    sql = f"EXEC {name} {params_str}"
    short = sql[:180]
    print(f"\n  >> {short}")
    try:
        c = ms.cursor()
        c.execute(sql)
        if c.description:
            cols = [d[0] for d in c.description]
            rows = []
            while True:
                batch = c.fetchmany(20)
                if not batch: break
                rows.extend(batch)
            print(f"     Cols ({len(cols)}): {cols}")
            print(f"     Total rows: {len(rows)}")
            for i,r in enumerate(rows[:4]):
                row_d = {k: str(v)[:80] for k,v in zip(cols,r)}
                print(f"     Row{i+1}: {row_d}")
        else:
            print("     [no result set]")
        c.close()
    except Exception as e:
        print(f"     ERROR: {e}")

# 1. Usp_GetAllDataForDropDownListsBasedOnFilter
sub("1. Usp_GetAllDataForDropDownListsBasedOnFilter")
for filter_name in ['', 'SalesOrg', 'Route', 'Channel', 'Brand', 'Category', 'Salesman']:
    fn_str = f", @FilterName='{filter_name}'" if filter_name else ""
    exec_sp('Usp_GetAllDataForDropDownListsBasedOnFilter', f"@UserCode='{MS_USER}'{fn_str}")

# 2. sp_GetMTDSalesOverviewReport_New
sub("2. sp_GetMTDSalesOverviewReport_New")
exec_sp('sp_GetMTDSalesOverviewReport_New',
    f"@SortExpression='', @StartRowIndex=0, @MaximumRows=50, "
    f"@SalesOrgCodes='', @RSMs='', @SalesManager='', @Supervisor='', "
    f"@SalesExecutive='', @SalesMan='{MS_USER}', @Route='', "
    f"@Category='', @Brand='', @SubBrand='', @Channel='', @SubChannel='', "
    f"@StartDate='{D_FROM}', @EndDate='{D_TO}', @ServerBy=''"
)
exec_sp('sp_GetMTDSalesOverviewReport_New',
    f"@SortExpression='', @StartRowIndex=0, @MaximumRows=50, "
    f"@SalesOrgCodes='{TEST_ORG}', @RSMs='', @SalesManager='', @Supervisor='', "
    f"@SalesExecutive='', @SalesMan='', @Route='{TEST_ROUTE}', "
    f"@Category='', @Brand='', @SubBrand='', @Channel='', @SubChannel='', "
    f"@StartDate='{D_FROM}', @EndDate='{D_TO}', @ServerBy=''"
)

# 3. sp_MTDSalesPerformanceReportLableDate
sub("3. sp_MTDSalesPerformanceReportLableDate")
exec_sp('sp_MTDSalesPerformanceReportLableDate',
    f"@SortExpression='', @StartRowIndex=0, @MaximumRows=50, "
    f"@SalesOrgCodes='', @RSMs='', @SalesManager='', @Supervisor='', "
    f"@SalesExecutive='', @SalesMan='{MS_USER}', @Route='', "
    f"@Category='', @Brand='', @SubBrand='', @Channel='', @SubChannel='', "
    f"@StartDate='{D_FROM}', @EndDate='{D_TO}', @Depot=''"
)
exec_sp('sp_MTDSalesPerformanceReportLableDate',
    f"@SortExpression='', @StartRowIndex=0, @MaximumRows=50, "
    f"@SalesOrgCodes='{TEST_ORG}', @RSMs='', @SalesManager='', @Supervisor='', "
    f"@SalesExecutive='', @SalesMan='', @Route='{TEST_ROUTE}', "
    f"@Category='', @Brand='', @SubBrand='', @Channel='', @SubChannel='', "
    f"@StartDate='{D_FROM}', @EndDate='{D_TO}', @Depot=''"
)

# 4. sp_GetAllSalesOrgsByUserCode
sub("4. sp_GetAllSalesOrgsByUserCode")
for u in [MS_USER] + list(active_users[:3]):
    exec_sp('sp_GetAllSalesOrgsByUserCode', f"@UserCode='{u}'")

# 5. USP_GetRoutesByUserCode_Filter_CreateOrder  (@LoginUserCode, @SalesOrgCode)
sub("5. USP_GetRoutesByUserCode_Filter_CreateOrder")
for u in [MS_USER] + list(active_users[:2]):
    exec_sp('USP_GetRoutesByUserCode_Filter_CreateOrder', f"@LoginUserCode='{u}', @SalesOrgCode=''")
    exec_sp('USP_GetRoutesByUserCode_Filter_CreateOrder', f"@LoginUserCode='{u}', @SalesOrgCode='{TEST_ORG}'")

# ── PG COMPARISON ─────────────────────────────────────────────────────────────
sep("PG COMPARISON")

sub("MTD daily sales per user (PG)")
pc.execute("""
    SELECT r.date,
        ROUND(SUM(r.total_sales)::numeric,2) AS total_sales,
        ROUND(SUM(CASE WHEN dc.customer_type='Cash' THEN r.total_sales ELSE 0 END)::numeric,2) AS cash,
        ROUND(SUM(CASE WHEN dc.customer_type='Credit' THEN r.total_sales ELSE 0 END)::numeric,2) AS credit
    FROM rpt_route_sales_by_item_customer r
    JOIN dim_route dr ON r.route_code=dr.code
    JOIN dim_customer dc ON r.customer_code=dc.code AND dc.sales_org_code=dr.sales_org_code
    WHERE r.user_code=%s AND r.date BETWEEN %s AND %s
    GROUP BY r.date ORDER BY r.date
""", (TEST_USER, D_FROM, D_TO))
rows = pc.fetchall()
print(f"  user={TEST_USER} -> {len(rows)} days")
for r in rows: print(f"  {r}")

sub("Sales orgs for user (PG dim_user_details)")
pc.execute("""
    SELECT DISTINCT dso.code, dso.name
    FROM dim_user_details dud
    JOIN dim_sales_org dso ON dud.sales_org_code=dso.code
    WHERE dud.user_code=%s
""", (TEST_USER,))
for r in pc.fetchall(): print(f"  {r}")

sub("Routes for user (PG)")
pc.execute("""
    SELECT dr.code, dr.name, dr.sales_org_code
    FROM dim_user du
    JOIN dim_route dr ON du.route_code=dr.code
    WHERE du.code=%s
""", (TEST_USER,))
for r in pc.fetchall(): print(f"  {r}")

mc.close(); ms.close()
pc.close(); pg.close()
print("\nDone.")
