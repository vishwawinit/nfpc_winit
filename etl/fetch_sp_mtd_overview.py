#!/usr/bin/env python3
"""
Fetch full definitions of 5 stored procedures and run sample executions.
READ-ONLY access to MSSQL source database.
"""

import pymssql
import sys
import os
from datetime import datetime

# Connection settings
SERVER   = '20.203.45.86'
USER     = 'nfpc'
PASSWORD = 'nfpc@!23'
DATABASE = 'NFPCsfaV3_070326'

OUTPUT_FILE = '/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_mtd_overview.txt'

SP_NAMES = [
    'sp_GetMTDSalesOverviewReport_New',
    'sp_MTDSalesPerformanceReportLableDate',
    'USP_GetRoutesByUserCode_Filter_CreateOrder',
    'Usp_GetAllDataForDropDownListsBasedOnFilter',
    'sp_GetAllSalesOrgsByUserCode',
]

DIVIDER = '=' * 120


def connect():
    print(f"Connecting to {SERVER}/{DATABASE} as {USER} ...")
    conn = pymssql.connect(server=SERVER, user=USER, password=PASSWORD,
                           database=DATABASE, timeout=120, login_timeout=30)
    print("Connected.\n")
    return conn


def get_sp_definition(conn, sp_name):
    """Retrieve full SP definition via sys.sql_modules (SELECT only)."""
    sql = f"""
SELECT
    o.name          AS sp_name,
    o.type_desc     AS sp_type,
    o.create_date,
    o.modify_date,
    m.definition    AS sp_definition
FROM sys.objects o
JOIN sys.sql_modules m ON o.object_id = m.object_id
WHERE o.name = '{sp_name}'
  AND o.type IN ('P','PC','X','RF','TS')
"""
    cur = conn.cursor(as_dict=True)
    cur.execute(sql)
    rows = cur.fetchall()
    return rows


def exec_sp_with_results(conn, sql, label):
    """Execute a stored procedure and capture all result sets."""
    print(f"\n{'─'*80}")
    print(f"EXECUTING: {label}")
    print(f"{'─'*80}")

    results = []
    cur = conn.cursor()
    cur.execute(sql)

    set_index = 0
    while True:
        try:
            cols = [d[0] for d in (cur.description or [])]
            if not cols:
                # no result set here – try next
                if cur.nextset():
                    set_index += 1
                    continue
                else:
                    break

            rows = cur.fetchmany(3)          # first 3 rows only
            all_rows = cur.fetchall()        # drain the rest
            total_approx = len(rows) + len(all_rows)

            result = {
                'set_index': set_index,
                'columns': cols,
                'sample_rows': rows,
                'total_fetched': total_approx,
            }
            results.append(result)
            set_index += 1

            if not cur.nextset():
                break
        except Exception as e:
            print(f"  [nextset error: {e}]")
            break

    return results


def format_result_set(rs):
    """Pretty-print a result set."""
    lines = []
    cols = rs['columns']
    lines.append(f"\n  --- Result Set #{rs['set_index'] + 1} ---")
    lines.append(f"  Columns ({len(cols)}): {cols}")
    lines.append(f"  Total rows fetched (approx): {rs['total_fetched']}")
    lines.append(f"  First 3 rows:")
    for i, row in enumerate(rs['sample_rows'], 1):
        lines.append(f"    Row {i}: {list(row)}")
    if not rs['sample_rows']:
        lines.append("    (no rows returned)")
    return '\n'.join(lines)


def main():
    output_lines = []

    def out(msg=''):
        print(msg)
        output_lines.append(str(msg))

    out(DIVIDER)
    out(f"NFPC MTD Overview SP Inspection — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out(DIVIDER)

    conn = connect()

    # ─────────────────────────────────────────────────────────
    # 1. Fetch full definitions of all 5 SPs
    # ─────────────────────────────────────────────────────────
    out()
    out(DIVIDER)
    out("SECTION 1: STORED PROCEDURE FULL DEFINITIONS")
    out(DIVIDER)

    for sp_name in SP_NAMES:
        out()
        out(f"{'─'*80}")
        out(f"SP: {sp_name}")
        out(f"{'─'*80}")
        rows = get_sp_definition(conn, sp_name)
        if not rows:
            out(f"  *** NOT FOUND in sys.sql_modules ***")
        else:
            for row in rows:
                out(f"  Type      : {row['sp_type']}")
                out(f"  Created   : {row['create_date']}")
                out(f"  Modified  : {row['modify_date']}")
                out()
                out("  DEFINITION:")
                out("  " + "-"*76)
                defn = row['sp_definition'] or '(empty)'
                for line in defn.splitlines():
                    out(f"  {line}")
                out("  " + "-"*76)

    # ─────────────────────────────────────────────────────────
    # 2. Run sp_GetMTDSalesOverviewReport_New with sample params
    # ─────────────────────────────────────────────────────────
    out()
    out(DIVIDER)
    out("SECTION 2: EXEC sp_GetMTDSalesOverviewReport_New (sample params)")
    out(DIVIDER)

    # Actual params (from SP definition): @SalesOrgCodes, @RSMs, @SalesManager, @Supervisor,
    # @SalesExecutive, @SalesMan, @Route, @Category, @Brand, @SubBrand,
    # @Channel, @SubChannel, @StartDate, @EndDate, @ServerBy
    # (No @GrandChannel/@SubSubChannel/@Year/@Month in the current SP version)
    sql_mtd_overview = """
EXEC sp_GetMTDSalesOverviewReport_New
    @SalesOrgCodes='', @RSMs='', @SalesManager='', @Supervisor='',
    @SalesExecutive='', @SalesMan='', @Route='',
    @Category='', @Brand='', @SubBrand='', @Channel='', @SubChannel='',
    @StartDate='2026-03-01', @EndDate='2026-03-03', @ServerBy=''
"""

    try:
        results = exec_sp_with_results(conn, sql_mtd_overview, 'sp_GetMTDSalesOverviewReport_New')
        out(f"\n  Total result sets returned: {len(results)}")
        for rs in results:
            block = format_result_set(rs)
            for line in block.splitlines():
                out(line)
    except Exception as e:
        out(f"  ERROR executing sp_GetMTDSalesOverviewReport_New: {e}")

    # ─────────────────────────────────────────────────────────
    # 3. Run sp_MTDSalesPerformanceReportLableDate
    # ─────────────────────────────────────────────────────────
    out()
    out(DIVIDER)
    out("SECTION 3: EXEC sp_MTDSalesPerformanceReportLableDate (date=2026-03-03)")
    out(DIVIDER)

    # Try to discover parameters first via sys.parameters
    sql_params = """
SELECT
    p.name          AS param_name,
    t.name          AS param_type,
    p.max_length,
    p.is_output,
    p.has_default_value,
    p.default_value
FROM sys.objects o
JOIN sys.parameters p ON o.object_id = p.object_id
JOIN sys.types t ON p.user_type_id = t.user_type_id
WHERE o.name = 'sp_MTDSalesPerformanceReportLableDate'
ORDER BY p.parameter_id
"""
    cur2 = conn.cursor(as_dict=True)
    cur2.execute(sql_params)
    params = cur2.fetchall()

    out("\n  Parameters for sp_MTDSalesPerformanceReportLableDate:")
    if params:
        for p in params:
            out(f"    {p['param_name']}  {p['param_type']}({p['max_length']})  "
                f"output={p['is_output']}  has_default={p['has_default_value']}")
    else:
        out("    (no parameters found — SP may take none, or was not found)")

    # Actual params: @StartDate, @EndDate (plus filters - all have defaults)
    # Use @EndDate='2026-03-03' (StartDate will be auto-computed to month start)
    sql_label_date = """
EXEC sp_MTDSalesPerformanceReportLableDate
    @StartDate='2026-03-01', @EndDate='2026-03-03'
"""
    try:
        results2 = exec_sp_with_results(conn, sql_label_date,
                                        'sp_MTDSalesPerformanceReportLableDate')
        out(f"\n  Total result sets returned: {len(results2)}")
        for rs in results2:
            block = format_result_set(rs)
            for line in block.splitlines():
                out(line)
    except Exception as e:
        out(f"  ERROR: {e}")
        # Try with no params
        out("\n  Retrying with no parameters...")
        try:
            results2b = exec_sp_with_results(conn, 'EXEC sp_MTDSalesPerformanceReportLableDate',
                                             'sp_MTDSalesPerformanceReportLableDate (no params)')
            out(f"\n  Total result sets returned: {len(results2b)}")
            for rs in results2b:
                block = format_result_set(rs)
                for line in block.splitlines():
                    out(line)
        except Exception as e2:
            out(f"  ERROR (no params): {e2}")

    # ─────────────────────────────────────────────────────────
    # Save to file
    # ─────────────────────────────────────────────────────────
    out()
    out(DIVIDER)
    out(f"Saving output to: {OUTPUT_FILE}")
    out(DIVIDER)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"\nDone. Output saved to {OUTPUT_FILE}")
    conn.close()


if __name__ == '__main__':
    main()
