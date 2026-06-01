#!/usr/bin/env python3
"""
Fetch full definitions of 3 stored procedures and run them with sample params.
READ-ONLY operations against the MSSQL source database.
"""

import pymssql
import sys
from datetime import datetime

# Connection config
MSSQL_CONFIG = {
    "server": "20.203.45.86",
    "user": "nfpc",
    "password": "nfpc@!23",
    "database": "NFPCsfaV3_070326",
    "timeout": 60,
    "login_timeout": 30,
}

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_weekly_sales.txt"

SP_NAMES = [
    "sp_tblTrxHeader_SELALL_Search_New",
    "SP_GetCustomerWeeklyOrderHistoryGraph_Modified",
    "SP_GetCustomerWeeklyOrderHistoryGraph_Modified_Amount",
]

SAMPLE_EXECS = {
    # This SP does NOT have @StartDate/@EndDate params.
    # It uses @searchString (a WHERE clause snippet) and @UserCode, @maximumRows, @startRowIndex.
    # Correct call: pass a date filter via @searchString.
    "sp_tblTrxHeader_SELALL_Search_New": {
        "primary": (
            "EXEC sp_tblTrxHeader_SELALL_Search_New "
            "@sortExpression='TrxDate ASC', "
            "@maximumRows=5, "
            "@startRowIndex=1, "
            "@searchString='DATEDIFF(dd,TH.TrxDate,''2026/03/01'') <= 0 AND DATEDIFF(dd,TH.TrxDate,''2026/03/03'') >= 0', "
            "@UserCode='admin'"
        ),
    },
    "SP_GetCustomerWeeklyOrderHistoryGraph_Modified": {
        "primary": "EXEC SP_GetCustomerWeeklyOrderHistoryGraph_Modified @StartDate='2026-03-01', @EndDate='2026-03-07'",
    },
    # This SP derives @SalesOrg from tblUserDetails for the given @UserCode.
    # Using 'admin' which should exist; fallback to CEO as per SP default.
    "SP_GetCustomerWeeklyOrderHistoryGraph_Modified_Amount": {
        "primary": (
            "EXEC SP_GetCustomerWeeklyOrderHistoryGraph_Modified_Amount "
            "@StartDate='2026-03-01', @EndDate='2026-03-07', "
            "@SearchString='1=1', @UserCode='admin'"
        ),
    },
}

def separator(char="=", width=80):
    return char * width

def print_and_write(text, f):
    print(text)
    f.write(text + "\n")

def get_sp_definition(cursor, sp_name):
    """Fetch full SP definition using sys.sql_modules + sys.objects (READ ONLY)."""
    query = """
        SELECT
            o.name AS sp_name,
            o.type_desc,
            o.create_date,
            o.modify_date,
            m.definition
        FROM sys.sql_modules m
        JOIN sys.objects o ON m.object_id = o.object_id
        WHERE o.name = %s
          AND o.type IN ('P', 'PC')
    """
    cursor.execute(query, (sp_name,))
    rows = cursor.fetchall()
    return rows

def get_sp_parameters(cursor, sp_name):
    """Fetch parameter definitions for a stored procedure (READ ONLY)."""
    query = """
        SELECT
            p.name AS param_name,
            t.name AS data_type,
            p.max_length,
            p.precision,
            p.scale,
            p.is_output,
            p.has_default_value,
            p.default_value
        FROM sys.parameters p
        JOIN sys.objects o ON p.object_id = o.object_id
        JOIN sys.types t ON p.user_type_id = t.user_type_id
        WHERE o.name = %s
        ORDER BY p.parameter_id
    """
    cursor.execute(query, (sp_name,))
    rows = cursor.fetchall()
    return rows

def execute_sp_and_capture(conn, exec_sql, sp_name, f):
    """Execute the SP and capture all result sets."""
    print_and_write(f"\n--- Executing: {exec_sql} ---", f)
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(exec_sql)

        result_set_num = 0
        while True:
            try:
                rows = cursor.fetchmany(5)
                if cursor.description:
                    result_set_num += 1
                    col_names = [desc[0] for desc in cursor.description]
                    print_and_write(f"\nResult Set #{result_set_num}", f)
                    print_and_write(f"Columns ({len(col_names)}): {col_names}", f)
                    print_and_write(f"First up to 5 rows:", f)
                    if rows:
                        for i, row in enumerate(rows, 1):
                            print_and_write(f"  Row {i}: {dict(row)}", f)
                    else:
                        print_and_write("  (no rows returned)", f)
                else:
                    # No description means non-SELECT result or done
                    pass

                if not cursor.nextset():
                    break
            except Exception as inner_e:
                print_and_write(f"  [nextset error: {inner_e}]", f)
                break

        if result_set_num == 0:
            print_and_write("  (no result sets returned)", f)

        cursor.close()
    except Exception as e:
        print_and_write(f"  [ERROR executing SP: {e}]", f)
        # Try to get correct param names from definition
        print_and_write(f"  >> Check SP definition above for correct parameter names.", f)

def main():
    output_lines = []

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        header = f"""
{separator()}
NFPC REPORTS - Stored Procedure Definitions & Sample Execution
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Database: NFPCsfaV3_070326 @ 20.203.45.86
{separator()}
"""
        print_and_write(header, f)

        print_and_write("Connecting to MSSQL...", f)
        try:
            conn = pymssql.connect(**MSSQL_CONFIG)
            print_and_write("Connected successfully.\n", f)
        except Exception as e:
            print_and_write(f"FATAL: Could not connect: {e}", f)
            sys.exit(1)

        # ----------------------------------------------------------------
        # PART 1: Fetch Full Definitions
        # ----------------------------------------------------------------
        print_and_write(separator(), f)
        print_and_write("PART 1: FULL STORED PROCEDURE DEFINITIONS", f)
        print_and_write(separator(), f)

        for sp_name in SP_NAMES:
            print_and_write(f"\n{separator('-')}", f)
            print_and_write(f"SP NAME: {sp_name}", f)
            print_and_write(separator("-"), f)

            cursor = conn.cursor()

            # Get metadata + definition
            rows = get_sp_definition(cursor, sp_name)
            if not rows:
                print_and_write(f"  [WARNING] No definition found for '{sp_name}'. Checking alternate lookup...", f)
                # Try case-insensitive
                cursor.execute(
                    "SELECT o.name, m.definition FROM sys.sql_modules m JOIN sys.objects o ON m.object_id = o.object_id WHERE LOWER(o.name) = LOWER(%s)",
                    (sp_name,)
                )
                rows = cursor.fetchall()
                if not rows:
                    print_and_write(f"  [ERROR] SP '{sp_name}' not found in database.", f)
                    cursor.close()
                    continue

            row = rows[0]
            if len(row) >= 5:
                print_and_write(f"Type:        {row[1]}", f)
                print_and_write(f"Created:     {row[2]}", f)
                print_and_write(f"Modified:    {row[3]}", f)
                definition = row[4]
            else:
                # alternate lookup returned only name + definition
                definition = row[1]

            # Get parameters
            params = get_sp_parameters(cursor, sp_name)
            if params:
                print_and_write(f"\nParameters ({len(params)}):", f)
                for p in params:
                    default_info = f", default={p[7]}" if p[6] else ""
                    output_flag = " [OUTPUT]" if p[5] else ""
                    print_and_write(f"  {p[0]}  {p[1]}(len={p[2]}, prec={p[3]}, scale={p[4]}){output_flag}{default_info}", f)
            else:
                print_and_write("  (no parameters found)", f)

            print_and_write(f"\nFULL DEFINITION:", f)
            print_and_write(separator("-"), f)
            if definition:
                print_and_write(definition, f)
            else:
                print_and_write("  [definition is NULL or empty]", f)
            print_and_write(separator("-"), f)

            cursor.close()

        # ----------------------------------------------------------------
        # PART 2: Execute SPs and Capture Output
        # ----------------------------------------------------------------
        print_and_write(f"\n{separator()}", f)
        print_and_write("PART 2: SAMPLE EXECUTION & OUTPUT STRUCTURE", f)
        print_and_write(separator(), f)

        for sp_name in SP_NAMES:
            print_and_write(f"\n{separator('-')}", f)
            print_and_write(f"EXECUTING: {sp_name}", f)
            print_and_write(separator("-"), f)

            exec_info = SAMPLE_EXECS.get(sp_name, {})
            primary_sql = exec_info.get("primary", "")

            if primary_sql:
                execute_sp_and_capture(conn, primary_sql, sp_name, f)

        # ----------------------------------------------------------------
        # Done
        # ----------------------------------------------------------------
        print_and_write(f"\n{separator()}", f)
        print_and_write(f"DONE. Output saved to: {OUTPUT_FILE}", f)
        print_and_write(separator(), f)

        conn.close()

if __name__ == "__main__":
    main()
