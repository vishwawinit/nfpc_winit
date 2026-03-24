import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
try:
    import pymssql
except ImportError:
    os.system(f"{sys.executable} -m pip install pymssql -q")
    import pymssql

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2
    import psycopg2.extras

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
def get_mssql():
    return pymssql.connect(
        server='20.203.45.86',
        user='nfpc',
        password='nfpc@!23',
        database='NFPCsfaV3_070326',
        as_dict=True,
        timeout=60
    )

def get_pg():
    return psycopg2.connect(
        host='switchback.proxy.rlwy.net',
        port=31910,
        dbname='railway',
        user='postgres',
        password='glzENZuNPmfnAEYrprneXIfVczZAfExC',
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=30
    )

def run_mssql(sql, conn):
    cur = conn.cursor()
    cur.execute(sql)
    try:
        rows = cur.fetchall()
    except Exception:
        rows = []
    cur.close()
    return rows

def run_pg(sql, conn):
    cur = conn.cursor()
    cur.execute(sql)
    try:
        rows = cur.fetchall()
    except Exception:
        rows = []
    cur.close()
    return rows

def print_rows(rows, title=""):
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print('='*70)
    if not rows:
        print("  (no rows)")
        return
    keys = list(rows[0].keys())
    col_w = {}
    for k in keys:
        col_w[k] = max(len(str(k)), max(len(str(r.get(k, '') or '')) for r in rows))
        col_w[k] = min(col_w[k], 40)
    header = "  " + " | ".join(str(k).ljust(col_w[k]) for k in keys)
    sep    = "  " + "-+-".join("-" * col_w[k] for k in keys)
    print(header)
    print(sep)
    for r in rows:
        line = "  " + " | ".join(str(r.get(k, '') or '').ljust(col_w[k])[:col_w[k]] for k in keys)
        print(line)
    print(f"  ({len(rows)} rows)")

def print_text(text, title=""):
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print('='*70)
    print(text or "  (empty)")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
print("\n" + "#"*70)
print("  NFPC HIERARCHY COMPARISON  --  MSSQL vs PostgreSQL")
print("#"*70)

# ============================= MSSQL =====================================
print("\n\n" + "="*70)
print("  [MSSQL SECTION]")
print("="*70)

mss = get_mssql()

# 1. tblUser structure (column info)
rows = run_mssql("""
    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'tblUser'
      AND COLUMN_NAME IN ('Code','Description','RoleCode','SalesOrgCode','ReportsTo','IsActive','UserType','DepotCode','RouteCode')
    ORDER BY ORDINAL_POSITION
""", mss)
print_rows(rows, "MSSQL - tblUser column structure")

# 2. Vw_SalesUserHierarchy definition
rows = run_mssql("""
    SELECT definition
    FROM sys.sql_modules sm
    JOIN sys.objects o ON sm.object_id = o.object_id
    WHERE o.name = 'Vw_SalesUserHierarchy'
""", mss)
if rows:
    print_text(rows[0]['definition'], "MSSQL - Vw_SalesUserHierarchy VIEW definition")
else:
    print_text("(view not found)", "MSSQL - Vw_SalesUserHierarchy VIEW definition")

# 3. TOP 20 from Vw_SalesUserHierarchy
try:
    rows = run_mssql("SELECT TOP 20 * FROM Vw_SalesUserHierarchy", mss)
    print_rows(rows, "MSSQL - TOP 20 FROM Vw_SalesUserHierarchy")
except Exception as e:
    print(f"\n  [ERROR querying Vw_SalesUserHierarchy]: {e}")

# 4. Role codes from tblUser
rows = run_mssql("""
    SELECT RoleCode, COUNT(*) AS cnt
    FROM tblUser
    WHERE IsActive=1
    GROUP BY RoleCode
    ORDER BY 2 DESC
""", mss)
print_rows(rows, "MSSQL - Distinct RoleCode counts from tblUser (active users)")

# 4b. Role codes from tblUserRole (the real role table)
try:
    rows = run_mssql("""
        SELECT UR.RoleCode, COUNT(*) AS cnt
        FROM tblUserRole UR
        INNER JOIN tblUser U ON U.Code = UR.UserCode AND U.IsActive=1
        GROUP BY UR.RoleCode
        ORDER BY 2 DESC
    """, mss)
    print_rows(rows, "MSSQL - Distinct RoleCode counts from tblUserRole (active users)")
except Exception as e:
    print(f"\n  [ERROR querying tblUserRole]: {e}")

# 4c. tblUserRole structure
try:
    rows = run_mssql("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='tblUserRole' ORDER BY ORDINAL_POSITION
    """, mss)
    print_rows(rows, "MSSQL - tblUserRole columns")
except Exception as e:
    print(f"\n  [ERROR]: {e}")

# 4d. tblUserDetails structure
try:
    rows = run_mssql("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='tblUserDetails' ORDER BY ORDINAL_POSITION
    """, mss)
    print_rows(rows, "MSSQL - tblUserDetails columns")
except Exception as e:
    print(f"\n  [ERROR]: {e}")

# 5. tblUserDetails sample
try:
    rows = run_mssql("SELECT TOP 5 * FROM tblUserDetails", mss)
    print_rows(rows, "MSSQL - tblUserDetails TOP 5")
except Exception as e:
    print(f"\n  [ERROR querying tblUserDetails]: {e}")

# 6. udf_GetAllChildUsers definition
rows = run_mssql("""
    SELECT definition
    FROM sys.sql_modules sm
    JOIN sys.objects o ON sm.object_id = o.object_id
    WHERE o.name = 'udf_GetAllChildUsers'
""", mss)
if rows:
    print_text(rows[0]['definition'], "MSSQL - udf_GetAllChildUsers definition")
else:
    print_text("(function not found)", "MSSQL - udf_GetAllChildUsers definition")

# 7. udf_GetAllSalesOrgOfUser definition
rows = run_mssql("""
    SELECT definition
    FROM sys.sql_modules sm
    JOIN sys.objects o ON sm.object_id = o.object_id
    WHERE o.name = 'udf_GetAllSalesOrgOfUser'
""", mss)
if rows:
    print_text(rows[0]['definition'], "MSSQL - udf_GetAllSalesOrgOfUser definition")
else:
    print_text("(function not found)", "MSSQL - udf_GetAllSalesOrgOfUser definition")

# 8. Sample users with hierarchy (via tblUserRole)
try:
    rows = run_mssql("""
        SELECT TOP 10 U.Code, U.Description, UR.RoleCode, UD.ReportsTo, UD.SalesOrgCode, U.DepotCode, U.RouteCode
        FROM tblUser U
        INNER JOIN tblUserRole UR ON UR.UserCode = U.Code
        INNER JOIN tblUserDetails UD ON UD.UserCode = U.Code
        WHERE U.IsActive=1
          AND UR.RoleCode IN ('HOS','ASM','C_SALES_SUPERVISOR','FreshSup','AMBIENTSUP','C_PRESALES_VANSALES','Vansales')
        ORDER BY UR.RoleCode, U.Code
    """, mss)
    print_rows(rows, "MSSQL - Sample active users by role via tblUserRole (top 10)")
except Exception as e:
    print(f"\n  [ERROR]: {e}")

# 9. Specific users (from tblUser)
rows = run_mssql("""
    SELECT Code, Description, RoleCode, ReportsTo, SalesOrgCode, DepotCode, RouteCode
    FROM tblUser
    WHERE Code IN ('102607','102609','106073')
""", mss)
print_rows(rows, "MSSQL - Users 102607, 102609, 106073 (from tblUser)")
mssql_users_base = {str(r['Code']): dict(r) for r in rows}

# 9b. Specific users via tblUserDetails (ReportsTo / SalesOrgCode)
try:
    rows = run_mssql("""
        SELECT U.Code, U.Description,
               UR.RoleCode,
               UD.ReportsTo, UD.SalesOrgCode,
               U.DepotCode, U.RouteCode
        FROM tblUser U
        LEFT JOIN tblUserRole UR ON UR.UserCode = U.Code
        LEFT JOIN tblUserDetails UD ON UD.UserCode = U.Code
        WHERE U.Code IN ('102607','102609','106073')
    """, mss)
    print_rows(rows, "MSSQL - Users 102607, 102609, 106073 (with tblUserRole + tblUserDetails)")
    mssql_users = {}
    for r in rows:
        code = str(r['Code'])
        if code not in mssql_users:
            mssql_users[code] = dict(r)
except Exception as e:
    print(f"\n  [ERROR]: {e}")
    mssql_users = mssql_users_base

# Brand
rows = run_mssql("""
    SELECT DISTINCT TOP 30 GroupLevel2,
        (SELECT TOP 1 Description FROM tblItemGroup WHERE Code=I.GroupLevel2) BrandName
    FROM tblItem I
    WHERE GroupLevel2 IS NOT NULL
    ORDER BY GroupLevel2
""", mss)
print_rows(rows, "MSSQL - Brand (GroupLevel2) top 30")

# Category
rows = run_mssql("""
    SELECT DISTINCT TOP 30 GroupLevel4,
        (SELECT TOP 1 Description FROM tblItemGroup WHERE Code=I.GroupLevel4) CatName
    FROM tblItem I
    WHERE GroupLevel4 IS NOT NULL
    ORDER BY GroupLevel4
""", mss)
print_rows(rows, "MSSQL - Category (GroupLevel4) top 30")

# Channel
rows = run_mssql("SELECT TOP 20 Code, Description FROM tblChannel ORDER BY Code", mss)
print_rows(rows, "MSSQL - tblChannel TOP 20")

mss.close()

# ============================= POSTGRESQL =====================================
print("\n\n" + "="*70)
print("  [POSTGRESQL SECTION]")
print("="*70)

pg = get_pg()

# 1. dim_user active, top 30
rows = run_pg("""
    SELECT code, name, role_code, reports_to, sales_org_code, depot_code, route_code
    FROM dim_user
    WHERE is_active=true
    ORDER BY role_code, code
    LIMIT 30
""", pg)
print_rows(rows, "PG - dim_user (active, LIMIT 30)")

# 2. Role codes
rows = run_pg("""
    SELECT role_code, COUNT(*) AS cnt
    FROM dim_user
    WHERE is_active=true
    GROUP BY role_code
    ORDER BY 2 DESC
""", pg)
print_rows(rows, "PG - Distinct role_code counts (active users)")

# 3. dim_user_details for specific users
try:
    rows = run_pg("""
        SELECT * FROM dim_user_details
        WHERE user_code IN ('102607','102609','106073')
    """, pg)
    print_rows(rows, "PG - dim_user_details for 102607, 102609, 106073")
except Exception as e:
    print(f"\n  [ERROR querying dim_user_details]: {e}")

# 4. Specific users
rows = run_pg("""
    SELECT code, name, role_code, reports_to, sales_org_code, depot_code, route_code
    FROM dim_user
    WHERE code IN ('102607','102609','106073')
""", pg)
print_rows(rows, "PG - Users 102607, 102609, 106073")
pg_users = {str(r['code']): dict(r) for r in rows}

# 5. Hierarchy chain for 102607
print("\n" + "="*70)
print("  PG - Hierarchy chain walk for user 102607")
print("="*70)
visited = set()
current = '102607'
chain = []
for _ in range(20):
    if current is None or current in visited:
        break
    visited.add(current)
    r = run_pg(f"""
        SELECT code, name, role_code, reports_to, sales_org_code
        FROM dim_user WHERE code = '{current}'
    """, pg)
    if not r:
        print(f"  User {current} not found in PG dim_user")
        break
    row = dict(r[0])
    chain.append(row)
    current = row.get('reports_to')

for i, node in enumerate(chain):
    indent = "  " + ("  " * i)
    print(f"{indent}[{i}] code={node['code']} | name={node['name']} | role={node['role_code']} | reports_to={node['reports_to']} | sales_org={node['sales_org_code']}")

# Brand
try:
    rows = run_pg("""
        SELECT DISTINCT brand_code, brand_name
        FROM dim_item
        WHERE brand_code IS NOT NULL
        ORDER BY brand_code
        LIMIT 30
    """, pg)
    print_rows(rows, "PG - dim_item brand_code / brand_name (LIMIT 30)")
except Exception as e:
    print(f"\n  [ERROR querying dim_item brands]: {e}")

# Category
try:
    rows = run_pg("""
        SELECT DISTINCT category_code, category_name
        FROM dim_item
        WHERE category_code IS NOT NULL
        ORDER BY category_code
        LIMIT 30
    """, pg)
    print_rows(rows, "PG - dim_item category_code / category_name (LIMIT 30)")
except Exception as e:
    print(f"\n  [ERROR querying dim_item categories]: {e}")

# Channel
try:
    rows = run_pg("SELECT code, name FROM dim_channel ORDER BY code", pg)
    print_rows(rows, "PG - dim_channel")
except Exception as e:
    print(f"\n  [ERROR querying dim_channel]: {e}")

pg.close()

# ============================= COMPARISON =====================================
print("\n\n" + "#"*70)
print("  COMPARISON: MSSQL vs PG  (users 102607, 102609, 106073)")
print("#"*70)

fields_mss = ['RoleCode', 'ReportsTo', 'SalesOrgCode', 'DepotCode', 'RouteCode']
fields_pg  = ['role_code', 'reports_to', 'sales_org_code', 'depot_code', 'route_code']

for code in ['102607', '102609', '106073']:
    print(f"\n  --- User {code} ---")
    m = mssql_users.get(code, {})
    p = pg_users.get(code, {})
    if not m:
        print("    MSSQL: NOT FOUND")
    if not p:
        print("    PG   : NOT FOUND")
    if m and p:
        print(f"  {'Field':<22} {'MSSQL':^30} {'PG':^30} {'Match?':^8}")
        print(f"  {'-'*22} {'-'*30} {'-'*30} {'-'*8}")
        for fm, fp in zip(fields_mss, fields_pg):
            mv = str(m.get(fm, '') or '')
            pv = str(p.get(fp, '') or '')
            match = "OK" if mv.strip().lower() == pv.strip().lower() else "DIFF"
            print(f"  {fm:<22} {mv:<30} {pv:<30} {match:^8}")

print("\n\n" + "#"*70)
print("  DONE")
print("#"*70)
