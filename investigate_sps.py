#!/usr/bin/env python3
"""
Investigate stored procedures that write to tblRouteSalesSummaryByItem
and tblRouteSalesCollectionSummary.
READ-ONLY queries only.
"""

import pymssql
import sys

SERVER = "20.203.45.86"
USER = "nfpc"
PASSWORD = "nfpc@!23"
DATABASE = "NFPCsfaV3_070326"

def run_query(conn, sql, desc=""):
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        print(f"  ERROR running [{desc}]: {e}")
        return []

def main():
    print("=" * 80)
    print("NFPC - Stored Procedure Investigation (READ-ONLY)")
    print("Tables: tblRouteSalesSummaryByItem | tblRouteSalesCollectionSummary")
    print("=" * 80)

    print("\nConnecting to MSSQL...")
    conn = pymssql.connect(server=SERVER, user=USER, password=PASSWORD,
                           database=DATABASE, timeout=60)
    print("Connected.\n")

    # -----------------------------------------------------------------------
    # 1. Find all SPs / functions referencing either table
    # -----------------------------------------------------------------------
    print("=" * 80)
    print("STEP 1: SPs / Functions that reference the tables")
    print("=" * 80)

    sql_find_sps = """
SELECT OBJECT_NAME(sm.object_id) AS sp_name, o.type_desc
FROM sys.sql_modules sm
JOIN sys.objects o ON sm.object_id = o.object_id
WHERE (sm.definition LIKE '%tblRouteSalesSummaryByItem%'
   OR  sm.definition LIKE '%tblRouteSalesCollectionSummary%')
AND o.type IN ('P', 'FN', 'TF', 'IF')
ORDER BY sp_name
"""
    sps = run_query(conn, sql_find_sps, "find SPs")

    if not sps:
        print("  No stored procedures or functions found referencing those tables.")
    else:
        print(f"  Found {len(sps)} object(s):\n")
        for row in sps:
            print(f"  - {row['sp_name']}  ({row['type_desc']})")

    # -----------------------------------------------------------------------
    # 2. SQL Agent jobs referencing either table
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 2: SQL Agent Jobs referencing the tables")
    print("=" * 80)

    sql_jobs = """
SELECT j.name AS job_name, js.step_name, js.command
FROM msdb.dbo.sysjobs j
JOIN msdb.dbo.sysjobsteps js ON j.job_id = js.job_id
WHERE js.command LIKE '%tblRouteSalesSummaryByItem%'
   OR js.command LIKE '%tblRouteSalesCollectionSummary%'
"""
    jobs = run_query(conn, sql_jobs, "find jobs")

    if not jobs:
        print("  No SQL Agent jobs found referencing those tables.")
    else:
        print(f"  Found {len(jobs)} job step(s):\n")
        for row in jobs:
            print(f"  Job : {row['job_name']}")
            print(f"  Step: {row['step_name']}")
            print(f"  Cmd : {row['command'][:500]}")
            print()

    # -----------------------------------------------------------------------
    # 3. Full definition of each SP – and flag INSERT/UPDATE/DELETE lines
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 3: Full definitions with write-operation analysis")
    print("=" * 80)

    TARGET_TABLES = [
        "tblRouteSalesSummaryByItem",
        "tblRouteSalesCollectionSummary",
    ]
    WRITE_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE"]

    for sp_row in sps:
        sp_name = sp_row['sp_name']
        print(f"\n{'─' * 70}")
        print(f"SP: {sp_name}")
        print(f"{'─' * 70}")

        rows = run_query(conn,
                         f"SELECT OBJECT_DEFINITION(OBJECT_ID('{sp_name}')) AS def",
                         f"definition of {sp_name}")

        if not rows or rows[0]['def'] is None:
            print("  (definition not available)")
            continue

        definition = rows[0]['def']

        # Print full definition
        print("\n--- FULL DEFINITION ---\n")
        print(definition)

        # Summarise write operations against our two tables
        print("\n--- WRITE OPERATION SUMMARY ---\n")
        found_writes = False
        for i, line in enumerate(definition.splitlines(), 1):
            upper = line.upper()
            for tbl in TARGET_TABLES:
                if tbl.upper() in upper:
                    for kw in WRITE_KEYWORDS:
                        if kw in upper:
                            print(f"  Line {i:4d} [{kw}] -> {line.strip()}")
                            found_writes = True
                            break

        if not found_writes:
            print("  No direct write operations found against the target tables in line-by-line scan.")
            print("  (The SP may reference the tables for SELECT only, or the write may be indirect.)")

    # -----------------------------------------------------------------------
    # 4. Max dates and row counts in both tables
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 4: Max date and row counts")
    print("=" * 80)

    sql_dates = """
SELECT 'tblRouteSalesSummaryByItem'        AS tbl, MAX(Date) AS max_date, COUNT(*) AS cnt
FROM tblRouteSalesSummaryByItem
UNION ALL
SELECT 'tblRouteSalesCollectionSummary',         MAX(Date), COUNT(*)
FROM tblRouteSalesCollectionSummary
"""
    date_rows = run_query(conn, sql_dates, "max dates")

    if not date_rows:
        print("  Could not retrieve date/count info.")
    else:
        print(f"\n  {'Table':<40} {'Max Date':<20} {'Row Count':>10}")
        print(f"  {'-'*40} {'-'*20} {'-'*10}")
        for row in date_rows:
            print(f"  {row['tbl']:<40} {str(row['max_date']):<20} {row['cnt']:>10,}")

    conn.close()
    print("\n\nDone.")

if __name__ == "__main__":
    main()
