#!/usr/bin/env python3
"""
One-time fix: populate dim_route.has_active_assignment from tblUserLocations.
Routes in tblUserLocations = routes actively assigned to salesmen = what the
MSSQL dashboard SP filters coverage data to.
READ-ONLY on MSSQL. Writes only to local PostgreSQL.
"""
import os
import pymssql
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

print("Connecting to MSSQL (READ-ONLY)...")
ms_conn = pymssql.connect(
    server=os.environ['DB_SERVER'], user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME'], timeout=60
)
ms_cur = ms_conn.cursor()

print("Fetching active routes from tblUserLocations...")
ms_cur.execute("""
    SELECT DISTINCT RouteCode
    FROM tblUserLocations
    WHERE IsActive = 1 AND RouteCode IS NOT NULL AND RouteCode != ''
""")
active_routes = [r[0] for r in ms_cur.fetchall()]
ms_conn.close()
print(f"  Found {len(active_routes)} active routes in tblUserLocations")

print("Connecting to PostgreSQL...")
pg_conn = psycopg2.connect(
    host=os.environ['PG_HOST'], port=int(os.environ.get('PG_PORT', 5432)),
    dbname=os.environ['PG_DATABASE'], user=os.environ['PG_USER'],
    password=os.environ['PG_PASSWORD']
)
pg_cur = pg_conn.cursor()

print("Updating dim_route.has_active_assignment...")
pg_cur.execute("UPDATE dim_route SET has_active_assignment = false")
n_reset = pg_cur.rowcount
print(f"  Reset {n_reset} routes to has_active_assignment=false")

if active_routes:
    ph = ','.join(['%s'] * len(active_routes))
    pg_cur.execute(f"UPDATE dim_route SET has_active_assignment = true WHERE code IN ({ph})", active_routes)
    n_set = pg_cur.rowcount
    print(f"  Set {n_set} routes to has_active_assignment=true")
else:
    print("  No active routes found — skipping UPDATE")

pg_conn.commit()
pg_conn.close()

# Verify
print("\nVerifying coverage for 2026-03-01 with active routes filter...")
pg_conn2 = psycopg2.connect(
    host=os.environ['PG_HOST'], port=int(os.environ.get('PG_PORT', 5432)),
    dbname=os.environ['PG_DATABASE'], user=os.environ['PG_USER'],
    password=os.environ['PG_PASSWORD']
)
cur2 = pg_conn2.cursor()
cur2.execute("""
    SELECT SUM(c.scheduled_calls) AS scheduled, SUM(c.total_actual_calls) AS total_actual,
           SUM(c.planned_calls) AS actual, SUM(c.selling_calls) AS selling
    FROM rpt_coverage_summary c
    JOIN dim_route r ON c.route_code = r.code AND r.has_active_assignment = true
    WHERE c.visit_date = '2026-03-01'
""")
r = cur2.fetchone()
print(f"  Scheduled={r[0]}, Total Actual={r[1]}, Planned={r[2]}, Selling={r[3]}")
if r[0]:
    print(f"  Strike Rate={round(r[3]/r[1]*100,2)}%, Coverage={round(r[2]/r[0]*100,2)}%")
pg_conn2.close()

print("\nDone.")
