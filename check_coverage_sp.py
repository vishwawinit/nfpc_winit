#!/usr/bin/env python3
"""
Check SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS definition
and tblRoute HasActiveAssignment column.
READ-ONLY on MSSQL.
"""
import pymssql

MSSQL = dict(server='20.203.45.86', user='nfpc', password='nfpc@!23',
             database='NFPCsfaV3_070326', timeout=60)

conn = pymssql.connect(**MSSQL)
cur = conn.cursor(as_dict=True)
print("Connected to MSSQL.\n")

# 1. Get SP definition
print("=" * 80)
print("SP: SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS")
print("=" * 80)
cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS')) AS def")
row = cur.fetchone()
if row and row['def']:
    print(row['def'])
else:
    print("[NOT FOUND]")

# 2. Check tblRoute columns
print("\n" + "=" * 80)
print("tblRoute columns")
print("=" * 80)
cur.execute("""
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'tblRoute'
    ORDER BY ORDINAL_POSITION
""")
for r in cur.fetchall():
    print(f"  {r['COLUMN_NAME']:<40} {r['DATA_TYPE']}")

# 3. Count routes with HasActiveAssignment = 1 (if column exists)
print("\n" + "=" * 80)
print("Routes with HasActiveAssignment = 1")
print("=" * 80)
try:
    cur.execute("SELECT COUNT(*) AS cnt FROM tblRoute WHERE HasActiveAssignment = 1")
    r = cur.fetchone()
    print(f"  Routes with HasActiveAssignment=1: {r['cnt']}")
    cur.execute("SELECT COUNT(*) AS cnt FROM tblRoute")
    r2 = cur.fetchone()
    print(f"  Total routes: {r2['cnt']}")
except Exception as e:
    print(f"  Error (column may not exist): {e}")

# 4. Coverage summary for Mar 1 with and without has_active_assignment filter
print("\n" + "=" * 80)
print("Coverage summary Mar 1 — with/without HasActiveAssignment filter")
print("=" * 80)
cur.execute("""
    SELECT SUM(cs.ScheduledCalls) AS scheduled, SUM(cs.TotalActualCalls) AS total_actual,
           SUM(cs.ActualCalls) AS actual, SUM(cs.SellingCalls) AS selling
    FROM tblRouteCoverageSummary cs
    WHERE CAST(cs.VisitDate AS DATE) = '2026-03-01'
""")
r = cur.fetchone()
print(f"  Without filter: scheduled={r['scheduled']}, total_actual={r['total_actual']}, "
      f"actual={r['actual']}, selling={r['selling']}")

try:
    cur.execute("""
        SELECT SUM(cs.ScheduledCalls) AS scheduled, SUM(cs.TotalActualCalls) AS total_actual,
               SUM(cs.ActualCalls) AS actual, SUM(cs.SellingCalls) AS selling
        FROM tblRouteCoverageSummary cs
        JOIN tblRoute r ON cs.RouteCode = r.Code AND r.HasActiveAssignment = 1
        WHERE CAST(cs.VisitDate AS DATE) = '2026-03-01'
    """)
    r2 = cur.fetchone()
    print(f"  With HasActiveAssignment=1: scheduled={r2['scheduled']}, total_actual={r2['total_actual']}, "
          f"actual={r2['actual']}, selling={r2['selling']}")
except Exception as e:
    print(f"  HasActiveAssignment filter error: {e}")

# 5. Check SP_GetDashboardRouteDetails definition
print("\n" + "=" * 80)
print("SP: SP_GetDashboardRouteDetails_Dashboard_Reports_V1_New_OPTS")
print("=" * 80)
cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('SP_GetDashboardRouteDetails_Dashboard_Reports_V1_New_OPTS')) AS def")
row2 = cur.fetchone()
if row2 and row2['def']:
    print(row2['def'][:3000])
    if len(row2['def']) > 3000:
        print(f"[... {len(row2['def'])-3000} more chars ...]")
else:
    print("[NOT FOUND]")

conn.close()
print("\nDone.")
