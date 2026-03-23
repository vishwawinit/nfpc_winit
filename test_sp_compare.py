"""
Run MSSQL SPs for Mar 1/2/3 and compare with local API.
READ-ONLY access to MSSQL source database.
"""
import pymssql
import urllib.request
import json

DB_SERVER   = "20.203.45.86"
DB_USER     = "nfpc"
DB_PASSWORD = "nfpc@!23"
DB_NAME     = "NFPCsfaV3_070326"
LOCAL_API   = "http://localhost:8000/api"

def ms_connect():
    return pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD,
                           database=DB_NAME, timeout=60)

def run_sp(conn, sp, **kwargs):
    """Execute a stored procedure with named params and return rows as list of dicts."""
    params = ", ".join(f"@{k}={repr(v) if isinstance(v,str) else v}" for k,v in kwargs.items())
    sql = f"EXEC {sp} {params}"
    cur = conn.cursor(as_dict=True)
    cur.execute(sql)
    rows = []
    try:
        rows = cur.fetchall()
        # Handle multiple result sets
        while cur.nextset():
            try:
                more = cur.fetchall()
                if more: rows.extend(more)
            except: break
    except Exception as e:
        print(f"  [fetch error: {e}]")
    cur.close()
    return rows

def local_api(path, **params):
    qs = "&".join(f"{k}={v}" for k,v in params.items())
    url = f"{LOCAL_API}{path}?{qs}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

DAYS = [
    (1, "Mar 1"),
    (2, "Mar 2"),
    (3, "Mar 3"),
]

EMPTY = "''"

print("\n" + "="*70)
print("CONNECTING TO MSSQL...")
conn = ms_connect()
print("Connected OK")

# ──────────────────────────────────────────────────────────────────────────────
# SP 1: sp_DashboardSales_SalesPercentage  →  return_on_sales in our API
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SP1: sp_DashboardSales_SalesPercentage  (Return on Sales / MTD Sales)")
print("="*70)
for day, label in DAYS:
    rows = run_sp(conn, "sp_DashboardSales_SalesPercentage",
        Year=2026, iMonth=3, Day=day,
        SalesOrg=EMPTY, HOS=EMPTY, ASM=EMPTY, Supervisor=EMPTY,
        SalesExecutive=EMPTY, Salesman=EMPTY, Route=EMPTY,
        Category=EMPTY, Brand=EMPTY, SubBrand=EMPTY,
        GrandChannel=EMPTY, SubChannel=EMPTY, ServerBy=EMPTY, SubSubChannel=EMPTY)
    print(f"\n  {label}: {len(rows)} rows from SP")
    for r in rows[:3]:
        print("    MSSQL:", dict(r))

    # Compare with local API
    local = local_api("/sales-performance", day=day, month=3, year=2026)
    ros = local.get("return_on_sales", {})
    print(f"    LOCAL:  total_sales={ros.get('total_sales',0):.0f}  "
          f"total_returns={ros.get('total_returns',0):.0f}  "
          f"net_sales={ros.get('net_sales',0):.0f}  ros%={ros.get('ros_pct',0)}")

# ──────────────────────────────────────────────────────────────────────────────
# SP 2: sp_GetSKUsSold_Formula  →  sku_counts in our API
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SP2: sp_GetSKUsSold_Formula  (SKU Counts: Today / MTD / YTD)")
print("="*70)
for day, label in DAYS:
    date_str = f"'20260{day if day>=10 else '0'+str(day)}'".strip("'")
    rows = run_sp(conn, "sp_GetSKUsSold_Formula",
        Date=f"2026-03-{day:02d}", Year=2026, Month=3,
        SalesOrg=EMPTY, RSM=EMPTY, SalesManager=EMPTY, Supervisor=EMPTY,
        SalesExecutive=EMPTY, Salesman=EMPTY, Route=EMPTY,
        Category=EMPTY, Brand=EMPTY, SubBrand=EMPTY,
        GrandChannel=EMPTY, SubChannel=EMPTY, ServerBy=EMPTY)
    print(f"\n  {label}: {len(rows)} rows from SP")
    for r in rows[:5]:
        print("    MSSQL:", dict(r))

    local = local_api("/sales-performance", day=day, month=3, year=2026)
    sku = local.get("sku_counts", {})
    print(f"    LOCAL:  today={sku.get('today')}  mtd={sku.get('mtd')}  ytd={sku.get('ytd')}")

# ──────────────────────────────────────────────────────────────────────────────
# SP 3: sp_SalesByItemOfClientDashboard  →  sku_table in our API
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SP3: sp_SalesByItemOfClientDashboard  (SKU Table)")
print("="*70)
for day, label in DAYS:
    rows = run_sp(conn, "sp_SalesByItemOfClientDashboard",
        Year=2026, Month=3, Day=day,
        SalesOrg=EMPTY, HOS=EMPTY, ASM=EMPTY, Supervisor=EMPTY,
        SalesExecutive=EMPTY, Salesman=EMPTY, Route=EMPTY,
        Category=EMPTY, Brand=EMPTY, SubBrand=EMPTY,
        GrandChannel=EMPTY, SubChannel=EMPTY, ServerBy=EMPTY, SubSubChannel=EMPTY)
    print(f"\n  {label}: {len(rows)} rows from SP")
    if rows:
        print("    Columns:", list(rows[0].keys()))
        for r in rows[:2]: print("    MSSQL:", dict(r))

    local = local_api("/sales-performance", day=day, month=3, year=2026)
    tbl = local.get("sku_table", [])
    print(f"    LOCAL:  {len(tbl)} sku_table rows")
    if tbl:
        print("    LOCAL sample:", {k: tbl[0][k] for k in ['item_code','item_name','current_month_sales','ly_current_month_sales'] if k in tbl[0]})

# ──────────────────────────────────────────────────────────────────────────────
# SP 4: sp_MarketSalesPerformance  (Market-level)
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SP4: sp_MarketSalesPerformance  (Market Sales)")
print("="*70)
rows = run_sp(conn, "sp_MarketSalesPerformance",
    Supervisor=EMPTY, CategoryCode=EMPTY, CountryCode=EMPTY, UnitorSAR="'Unit'")
print(f"  {len(rows)} rows from SP")
if rows:
    print("  Columns:", list(rows[0].keys()))
    for r in rows[:3]: print("  MSSQL:", dict(r))

conn.close()
print("\n" + "="*70)
print("DONE")
