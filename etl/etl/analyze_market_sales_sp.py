#!/usr/bin/env python3
"""
Analyze MSSQL Stored Procedures:
 - Usp_GetMarketSalesPerformanceData
 - usp_tblCountry_SELALL
 - SP_tblTrxHeader_ReportCountryView
READ-ONLY access only.
"""

import pymssql
import sys
from datetime import datetime

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_market_sales.txt"

DB_CONFIG = {
    "server": "20.203.45.86",
    "user": "nfpc",
    "password": "nfpc@!23",
    "database": "NFPCsfaV3_070326",
    "timeout": 60,
    "login_timeout": 15,
}

SP_NAMES = [
    "Usp_GetMarketSalesPerformanceData",
    "usp_tblCountry_SELALL",
    "SP_tblTrxHeader_ReportCountryView",
]

lines = []

def log(msg=""):
    print(msg)
    lines.append(msg)

def separator(char="=", width=100):
    log(char * width)

def header(title):
    separator()
    log(f"  {title}")
    separator()

def subheader(title):
    separator("-", 80)
    log(f"  {title}")
    separator("-", 80)


def get_sp_definition(cursor, sp_name):
    """Fetch full stored procedure definition using sys.sql_modules."""
    log(f"\n>>> Fetching definition for: {sp_name}")
    try:
        cursor.execute("""
            SELECT
                o.name AS sp_name,
                o.type_desc,
                o.create_date,
                o.modify_date,
                sm.definition
            FROM sys.objects o
            JOIN sys.sql_modules sm ON o.object_id = sm.object_id
            WHERE o.type IN ('P', 'PC')
              AND LOWER(o.name) = LOWER(%s)
        """, (sp_name,))
        rows = cursor.fetchall()
        if not rows:
            log(f"  [WARNING] No definition found for '{sp_name}' via sys.sql_modules.")
            return None
        row = rows[0]
        log(f"  Name        : {row[0]}")
        log(f"  Type        : {row[1]}")
        log(f"  Created     : {row[2]}")
        log(f"  Modified    : {row[3]}")
        return row[4]  # definition text
    except Exception as e:
        log(f"  [ERROR] Definition fetch failed: {e}")
        return None


def get_sp_parameters(cursor, sp_name):
    """Fetch parameters of a stored procedure."""
    try:
        cursor.execute("""
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
            JOIN sys.types t ON p.user_type_id = t.user_type_id
            JOIN sys.objects o ON p.object_id = o.object_id
            WHERE LOWER(o.name) = LOWER(%s)
            ORDER BY p.parameter_id
        """, (sp_name,))
        return cursor.fetchall()
    except Exception as e:
        log(f"  [ERROR] Parameter fetch failed: {e}")
        return []


def get_tables_referenced(cursor, sp_name):
    """Find tables/views referenced in the SP body."""
    try:
        cursor.execute("""
            SELECT DISTINCT
                OBJECT_NAME(d.referenced_id) AS referenced_object,
                o2.type_desc AS object_type
            FROM sys.sql_expression_dependencies d
            JOIN sys.objects o ON d.referencing_id = o.object_id
            LEFT JOIN sys.objects o2 ON d.referenced_id = o2.object_id
            WHERE LOWER(o.name) = LOWER(%s)
              AND d.referenced_id IS NOT NULL
            ORDER BY referenced_object
        """, (sp_name,))
        return cursor.fetchall()
    except Exception as e:
        log(f"  [ERROR] Table reference fetch failed: {e}")
        return []


def print_result_sets(cursor, sp_name, label=""):
    """Print all result sets returned by the cursor after executing an SP."""
    result_num = 1
    found_any = False
    while True:
        try:
            cols = [desc[0] for desc in cursor.description] if cursor.description else []
            if not cols:
                # Try to move to next result set
                if not cursor.nextset():
                    break
                continue

            found_any = True
            rows = cursor.fetchall()
            subheader(f"Result Set #{result_num} {label} — {len(rows)} row(s), {len(cols)} column(s)")
            log(f"  Columns: {cols}")
            log("")

            # Print header row
            col_widths = [max(len(str(c)), 12) for c in cols]
            for i, r in enumerate(rows[:5]):
                for j, val in enumerate(r):
                    col_widths[j] = max(col_widths[j], len(str(val)[:50]))

            header_line = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(cols))
            log("  " + header_line)
            log("  " + "-" * len(header_line))

            for row in rows[:5]:
                row_line = " | ".join(str(v)[:50].ljust(col_widths[i]) for i, v in enumerate(row))
                log("  " + row_line)

            if len(rows) > 5:
                log(f"  ... ({len(rows) - 5} more rows not shown)")

            log("")
            result_num += 1

            if not cursor.nextset():
                break

        except StopIteration:
            break
        except Exception as e:
            log(f"  [INFO] No more result sets or error: {e}")
            break

    if not found_any:
        log("  (No result sets returned)")


def analyze_sp(conn, sp_name):
    header(f"STORED PROCEDURE: {sp_name}")

    # --- 1. Full Definition ---
    subheader("1. FULL DEFINITION")
    cursor = conn.cursor()
    definition = get_sp_definition(cursor, sp_name)
    if definition:
        log("\n--- BEGIN SP DEFINITION ---")
        log(definition)
        log("--- END SP DEFINITION ---\n")
    else:
        log("  Definition not available.\n")

    # --- 2. Parameters ---
    subheader("2. PARAMETERS")
    cursor = conn.cursor()
    params = get_sp_parameters(cursor, sp_name)
    if params:
        log(f"  {'Param':<30} {'Type':<20} {'MaxLen':>8} {'Prec':>6} {'Scale':>6} {'Output':>8} {'HasDefault':>12} {'Default'}")
        log("  " + "-" * 110)
        for p in params:
            log(f"  {str(p[0]):<30} {str(p[1]):<20} {str(p[2]):>8} {str(p[3]):>6} {str(p[4]):>6} {str(p[5]):>8} {str(p[6]):>12}   {str(p[7]) if p[7] is not None else ''}")
    else:
        log("  (No parameters — or SP takes no arguments)")

    # --- 3. Tables / Views Referenced ---
    subheader("3. TABLES / VIEWS REFERENCED")
    cursor = conn.cursor()
    refs = get_tables_referenced(cursor, sp_name)
    if refs:
        for ref in refs:
            log(f"  {str(ref[1]):<30} {ref[0]}")
    else:
        log("  (Could not determine references — may use dynamic SQL)")

    return params, definition


def run_sp_and_capture(conn, sp_name, params_list, params_label, exec_sql_template):
    """Execute an SP with given params and capture results."""
    subheader(f"EXECUTION: {sp_name} | Params: {params_label}")
    log(f"  SQL: {exec_sql_template}")
    log("")
    cursor = conn.cursor()
    try:
        cursor.execute(exec_sql_template, params_list)
        print_result_sets(cursor, sp_name, f"[{params_label}]")
    except Exception as e:
        log(f"  [ERROR during execution]: {e}")
        log("")


def main():
    log("=" * 100)
    log(f"  NFPC MSSQL Stored Procedure Analysis")
    log(f"  Database : NFPCsfaV3_070326  |  Server: 20.203.45.86")
    log(f"  Run at   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 100)

    log("\nConnecting to MSSQL...")
    try:
        conn = pymssql.connect(**DB_CONFIG)
        log("Connected successfully.\n")
    except Exception as e:
        log(f"[FATAL] Connection failed: {e}")
        sys.exit(1)

    # =========================================================================
    # SP 1: Usp_GetMarketSalesPerformanceData
    # =========================================================================
    params_1, def_1 = analyze_sp(conn, "Usp_GetMarketSalesPerformanceData")

    # Determine parameter count to build exec call
    # Will try common patterns for March 2026
    subheader("4. SAMPLE EXECUTION — Usp_GetMarketSalesPerformanceData (March 2026)")

    # First, let's see the parameter names so we can pass them correctly
    # Try: @FromDate, @ToDate style first
    param_names_1 = [p[0] for p in params_1] if params_1 else []
    log(f"  Parameter names: {param_names_1}")

    cursor_test = conn.cursor()
    executed_1 = False

    # Try various common param patterns
    exec_attempts = []

    if len(params_1) == 0:
        exec_attempts.append(("No params", "EXEC Usp_GetMarketSalesPerformanceData", [], "EXEC Usp_GetMarketSalesPerformanceData"))
    else:
        # Try with date range
        exec_attempts.append((
            "Month=3, Year=2026",
            "EXEC Usp_GetMarketSalesPerformanceData %s, %s",
            [3, 2026],
            "EXEC Usp_GetMarketSalesPerformanceData 3, 2026"
        ))
        exec_attempts.append((
            "FromDate/ToDate March 2026",
            "EXEC Usp_GetMarketSalesPerformanceData %s, %s",
            ['2026-03-01', '2026-03-31'],
            "EXEC Usp_GetMarketSalesPerformanceData '2026-03-01', '2026-03-31'"
        ))
        exec_attempts.append((
            "Year=2026, Month=3",
            "EXEC Usp_GetMarketSalesPerformanceData %s, %s",
            [2026, 3],
            "EXEC Usp_GetMarketSalesPerformanceData 2026, 3"
        ))

    for attempt_label, sql_tmpl, params_vals, display_sql in exec_attempts:
        log(f"\n  Trying: {attempt_label}")
        log(f"  SQL: {display_sql}")
        cursor_exec = conn.cursor()
        try:
            if params_vals:
                cursor_exec.execute(sql_tmpl, params_vals)
            else:
                cursor_exec.execute(sql_tmpl)
            print_result_sets(cursor_exec, "Usp_GetMarketSalesPerformanceData", f"[{attempt_label}]")
            executed_1 = True
            break
        except Exception as e:
            log(f"  [Failed]: {e}")

    if not executed_1:
        log("  [WARNING] All execution attempts failed. Check parameter names above.")

    # =========================================================================
    # SP 2: usp_tblCountry_SELALL
    # =========================================================================
    params_2, def_2 = analyze_sp(conn, "usp_tblCountry_SELALL")

    subheader("4. SAMPLE EXECUTION — usp_tblCountry_SELALL")
    log("  Executing: EXEC usp_tblCountry_SELALL")
    cursor_c = conn.cursor()
    try:
        cursor_c.execute("EXEC usp_tblCountry_SELALL")
        print_result_sets(cursor_c, "usp_tblCountry_SELALL", "[Country List]")
    except Exception as e:
        log(f"  [ERROR]: {e}")

    # =========================================================================
    # SP 3: SP_tblTrxHeader_ReportCountryView
    # =========================================================================
    params_3, def_3 = analyze_sp(conn, "SP_tblTrxHeader_ReportCountryView")

    subheader("4. SAMPLE EXECUTION — SP_tblTrxHeader_ReportCountryView (March 2026)")
    param_names_3 = [p[0] for p in params_3] if params_3 else []
    log(f"  Parameter names: {param_names_3}")

    exec_attempts_3 = []

    if len(params_3) == 0:
        exec_attempts_3.append(("No params", "EXEC SP_tblTrxHeader_ReportCountryView", [], "EXEC SP_tblTrxHeader_ReportCountryView"))
    else:
        exec_attempts_3.append((
            "FromDate/ToDate March 2026",
            "EXEC SP_tblTrxHeader_ReportCountryView %s, %s",
            ['2026-03-01', '2026-03-31'],
            "EXEC SP_tblTrxHeader_ReportCountryView '2026-03-01', '2026-03-31'"
        ))
        exec_attempts_3.append((
            "Month=3, Year=2026",
            "EXEC SP_tblTrxHeader_ReportCountryView %s, %s",
            [3, 2026],
            "EXEC SP_tblTrxHeader_ReportCountryView 3, 2026"
        ))
        exec_attempts_3.append((
            "Year=2026, Month=3",
            "EXEC SP_tblTrxHeader_ReportCountryView %s, %s",
            [2026, 3],
            "EXEC SP_tblTrxHeader_ReportCountryView 2026, 3"
        ))

    executed_3 = False
    for attempt_label, sql_tmpl, params_vals, display_sql in exec_attempts_3:
        log(f"\n  Trying: {attempt_label}")
        log(f"  SQL: {display_sql}")
        cursor_exec3 = conn.cursor()
        try:
            if params_vals:
                cursor_exec3.execute(sql_tmpl, params_vals)
            else:
                cursor_exec3.execute(sql_tmpl)
            print_result_sets(cursor_exec3, "SP_tblTrxHeader_ReportCountryView", f"[{attempt_label}]")
            executed_3 = True
            break
        except Exception as e:
            log(f"  [Failed]: {e}")

    if not executed_3:
        log("  [WARNING] All execution attempts failed for SP_tblTrxHeader_ReportCountryView.")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    header("SUMMARY ANALYSIS")

    summaries = [
        ("Usp_GetMarketSalesPerformanceData", params_1, def_1),
        ("usp_tblCountry_SELALL", params_2, def_2),
        ("SP_tblTrxHeader_ReportCountryView", params_3, def_3),
    ]

    for sp_name, params, defn in summaries:
        subheader(f"SP: {sp_name}")
        log(f"  Parameters ({len(params)}):")
        for p in params:
            direction = "OUTPUT" if p[5] else "INPUT"
            log(f"    {p[0]} ({p[1]}) [{direction}]")
        if not params:
            log("    (none)")

        log("")
        log("  Tables / Objects Referenced:")
        cursor_s = conn.cursor()
        refs = get_tables_referenced(cursor_s, sp_name)
        for ref in refs:
            log(f"    [{ref[1]}] {ref[0]}")
        if not refs:
            log("    (dynamic SQL or could not determine)")

        log("")
        # Quick purpose guess from definition keywords
        if defn:
            defn_upper = defn.upper()
            purpose_hints = []
            if "SALES" in defn_upper:
                purpose_hints.append("sales data")
            if "COUNTRY" in defn_upper:
                purpose_hints.append("country filtering/grouping")
            if "MARKET" in defn_upper:
                purpose_hints.append("market analysis")
            if "GROUP BY" in defn_upper:
                purpose_hints.append("aggregation")
            if "JOIN" in defn_upper:
                purpose_hints.append("multi-table joins")
            if "PIVOT" in defn_upper:
                purpose_hints.append("pivot/cross-tab")
            if "CURSOR" in defn_upper:
                purpose_hints.append("cursor iteration")
            if "TEMP" in defn_upper or "#" in defn:
                purpose_hints.append("temp tables")
            if "PERFORMANCE" in defn_upper:
                purpose_hints.append("performance KPIs")
            if "TARGET" in defn_upper or "QUOTA" in defn_upper:
                purpose_hints.append("target/quota comparison")
            log(f"  Inferred Purpose Hints: {', '.join(purpose_hints) if purpose_hints else 'N/A'}")
        log("")

    conn.close()
    log("\n[Done] Analysis complete.")

    # Save to file
    output = "\n".join(lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\n[Saved] Full output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
