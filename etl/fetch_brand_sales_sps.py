#!/usr/bin/env python3
"""
Fetch full definitions and sample output for brand sales stored procedures.
READ-ONLY access to MSSQL source database.
"""

import pymssql
import sys
from datetime import datetime

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_brand_sales.txt"

# Connection details
MSSQL_CONFIG = {
    "server": "20.203.45.86",
    "user": "nfpc",
    "password": "nfpc@!23",
    "database": "NFPCsfaV3_070326",
}

SP_NAMES = [
    "sp_BrandsSale_Search_Report",
    "sp_GetBrandWiseTargetandSaleAmount",
    "sp_tblItemDateBasedOnBrand",
    "sp_tblBrand_SELALL",
    "usp_tblUser_SEL_ByUserTypeCodeWithUserCode",
    "sp_tblSalesTeam_SELAll",
    "sp_GetCurrenceCodeBytblSalesOrg",
    "sp_GetAllSalesOrgsByUserCode",
]

def separator(char="=", width=100):
    return char * width

def get_connection():
    return pymssql.connect(**MSSQL_CONFIG)

def fetch_sp_definition(conn, sp_name):
    """Fetch full SP definition using OBJECT_DEFINITION or sys.sql_modules."""
    cursor = conn.cursor(as_dict=True)

    # Try OBJECT_DEFINITION first
    cursor.execute(f"SELECT OBJECT_DEFINITION(OBJECT_ID('{sp_name}')) AS definition")
    row = cursor.fetchone()
    if row and row["definition"]:
        return row["definition"]

    # Fallback: sys.sql_modules
    cursor.execute(f"""
        SELECT sm.definition
        FROM sys.sql_modules sm
        JOIN sys.objects o ON sm.object_id = o.object_id
        WHERE o.name = '{sp_name}'
    """)
    row = cursor.fetchone()
    if row and row["definition"]:
        return row["definition"]

    return None

def fetch_sp_parameters(conn, sp_name):
    """Fetch parameter list for a stored procedure."""
    cursor = conn.cursor(as_dict=True)
    cursor.execute(f"""
        SELECT
            p.name AS param_name,
            t.name AS data_type,
            p.max_length,
            p.precision,
            p.scale,
            p.is_output,
            p.has_default_value,
            p.default_value,
            p.parameter_id
        FROM sys.parameters p
        JOIN sys.types t ON p.user_type_id = t.user_type_id
        JOIN sys.objects o ON p.object_id = o.object_id
        WHERE o.name = '{sp_name}'
        ORDER BY p.parameter_id
    """)
    return cursor.fetchall()

def fetch_tables_used(conn, sp_name):
    """Extract tables referenced in the SP via sys.sql_expression_dependencies."""
    cursor = conn.cursor(as_dict=True)
    cursor.execute(f"""
        SELECT DISTINCT
            COALESCE(sed.referenced_schema_name, 'dbo') AS schema_name,
            sed.referenced_entity_name AS table_name,
            o2.type_desc AS object_type
        FROM sys.sql_expression_dependencies sed
        JOIN sys.objects o ON sed.referencing_id = o.object_id
        LEFT JOIN sys.objects o2 ON sed.referenced_id = o2.object_id
        WHERE o.name = '{sp_name}'
          AND sed.referenced_entity_name NOT IN (SELECT name FROM sys.objects WHERE type = 'P')
        ORDER BY sed.referenced_entity_name
    """)
    return cursor.fetchall()

def run_sp_brand_selall(conn):
    """Run sp_tblBrand_SELALL to get brand list."""
    cursor = conn.cursor(as_dict=True)
    cursor.callproc("sp_tblBrand_SELALL")
    results = []
    while True:
        try:
            rows = cursor.fetchall()
            if rows:
                results.append(rows)
        except:
            pass
        if not cursor.nextset():
            break
    return results

def run_sp_brands_sale_search_report(conn, params):
    """Run sp_BrandsSale_Search_Report with given params."""
    cursor = conn.cursor(as_dict=True)
    # Build EXEC statement
    param_str = ", ".join([f"@{k}='{v}'" if isinstance(v, str) else f"@{k}={v}" for k, v in params.items()])
    sql = f"EXEC sp_BrandsSale_Search_Report {param_str}"
    print(f"  Executing: {sql[:200]}")
    cursor.execute(sql)
    results = []
    while True:
        try:
            rows = cursor.fetchall()
            if rows:
                results.append(rows)
        except:
            pass
        if not cursor.nextset():
            break
    return results

def run_sp_brand_wise_target(conn, params):
    """Run sp_GetBrandWiseTargetandSaleAmount with given params."""
    cursor = conn.cursor(as_dict=True)
    param_str = ", ".join([f"@{k}='{v}'" if isinstance(v, str) else f"@{k}={v}" for k, v in params.items()])
    sql = f"EXEC sp_GetBrandWiseTargetandSaleAmount {param_str}"
    print(f"  Executing: {sql[:200]}")
    cursor.execute(sql)
    results = []
    while True:
        try:
            rows = cursor.fetchall()
            if rows:
                results.append(rows)
        except:
            pass
        if not cursor.nextset():
            break
    return results

def format_rows(rows, max_rows=20):
    """Format rows as a text table."""
    if not rows:
        return "  (no rows returned)"

    lines = []
    cols = list(rows[0].keys())

    # Calculate column widths
    col_widths = {c: len(str(c)) for c in cols}
    for row in rows[:max_rows]:
        for c in cols:
            val = str(row.get(c, ""))[:60]
            col_widths[c] = max(col_widths[c], len(val))

    # Header
    header = " | ".join(str(c).ljust(col_widths[c]) for c in cols)
    divider = "-+-".join("-" * col_widths[c] for c in cols)
    lines.append(header)
    lines.append(divider)

    # Rows
    for row in rows[:max_rows]:
        line = " | ".join(str(row.get(c, "")).ljust(col_widths[c])[:col_widths[c]] for c in cols)
        lines.append(line)

    if len(rows) > max_rows:
        lines.append(f"  ... ({len(rows) - max_rows} more rows not shown, total: {len(rows)})")
    else:
        lines.append(f"  Total rows: {len(rows)}")

    return "\n  ".join(lines)

def main():
    output_lines = []

    def log(text=""):
        print(text)
        output_lines.append(text)

    log(separator())
    log("NFPC BRAND SALES STORED PROCEDURES - FULL ANALYSIS")
    log(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Database: NFPCsfaV3_070326 @ 20.203.45.86 (READ-ONLY)")
    log(separator())
    log()

    print("Connecting to MSSQL...")
    conn = get_connection()
    print("Connected successfully.\n")

    # =========================================================================
    # PART 1: Full SP Definitions
    # =========================================================================
    log(separator())
    log("PART 1: FULL STORED PROCEDURE DEFINITIONS")
    log(separator())
    log()

    for i, sp_name in enumerate(SP_NAMES, 1):
        log(separator("-"))
        log(f"[{i}/{len(SP_NAMES)}] STORED PROCEDURE: {sp_name}")
        log(separator("-"))
        log()

        # Parameters
        params = fetch_sp_parameters(conn, sp_name)
        log("PARAMETERS:")
        if params:
            for p in params:
                direction = "OUTPUT" if p["is_output"] else "INPUT"
                dtype = p["data_type"]
                if dtype in ("varchar", "nvarchar", "char", "nchar"):
                    size = p["max_length"]
                    if size == -1:
                        dtype += "(MAX)"
                    else:
                        if dtype.startswith("n"):
                            dtype += f"({size // 2})"
                        else:
                            dtype += f"({size})"
                elif dtype in ("decimal", "numeric"):
                    dtype += f"({p['precision']},{p['scale']})"
                default = f" = {p['default_value']}" if p["has_default_value"] and p["default_value"] is not None else ""
                log(f"  {p['param_name']}  {dtype}  [{direction}]{default}")
        else:
            log("  (no parameters)")
        log()

        # Tables used
        tables = fetch_tables_used(conn, sp_name)
        log("TABLES / OBJECTS REFERENCED:")
        if tables:
            for t in tables:
                obj_type = t.get("object_type") or "UNKNOWN"
                log(f"  [{obj_type}]  {t['schema_name']}.{t['table_name']}")
        else:
            log("  (could not determine via sys.sql_expression_dependencies — check definition below)")
        log()

        # Full definition
        log("FULL DEFINITION:")
        definition = fetch_sp_definition(conn, sp_name)
        if definition:
            log(definition)
        else:
            log(f"  WARNING: Could not retrieve definition for {sp_name}")
            log("  (SP may not exist or insufficient permissions)")

        log()
        log()

    # =========================================================================
    # PART 2: Sample Execution
    # =========================================================================
    log(separator())
    log("PART 2: SAMPLE EXECUTION WITH MARCH 2026 PARAMETERS")
    log(separator())
    log()

    # --- sp_tblBrand_SELALL ---
    log(separator("-"))
    log("EXECUTING: sp_tblBrand_SELALL")
    log("PURPOSE: Retrieve full brand master list")
    log(separator("-"))
    log()
    try:
        results = run_sp_brand_selall(conn)
        if results:
            for rs_idx, rs in enumerate(results, 1):
                log(f"Result Set {rs_idx} ({len(rs)} rows):")
                log(format_rows(rs, max_rows=50))
                log()
        else:
            log("  (no result sets returned)")
    except Exception as e:
        log(f"  ERROR: {e}")
    log()

    # --- Check params for sp_BrandsSale_Search_Report first ---
    log(separator("-"))
    log("INSPECTING PARAMS: sp_BrandsSale_Search_Report")
    log(separator("-"))
    params_brand_sale = fetch_sp_parameters(conn, "sp_BrandsSale_Search_Report")
    log("Parameters found:")
    for p in params_brand_sale:
        log(f"  {p['param_name']}  {p['data_type']}  [{'OUTPUT' if p['is_output'] else 'INPUT'}]")
    log()

    # Build March 2026 params for sp_BrandsSale_Search_Report
    # Common params: FromDate, ToDate, SalesOrgCode, BrandCode, UserCode, etc.
    # We'll try to detect and use defaults
    brand_sale_params = {}
    for p in params_brand_sale:
        pname = p["param_name"].lstrip("@")
        pname_lower = pname.lower()
        if "fromdate" in pname_lower or "startdate" in pname_lower or "datefrom" in pname_lower:
            brand_sale_params[pname] = "2026-03-01"
        elif "todate" in pname_lower or "enddate" in pname_lower or "dateto" in pname_lower:
            brand_sale_params[pname] = "2026-03-18"
        elif "month" in pname_lower and "year" not in pname_lower:
            brand_sale_params[pname] = "3"
        elif "year" in pname_lower and "month" not in pname_lower:
            brand_sale_params[pname] = "2026"
        elif "monthyear" in pname_lower or ("month" in pname_lower and "year" in pname_lower):
            brand_sale_params[pname] = "032026"
        elif "salesorg" in pname_lower or "orgcode" in pname_lower:
            brand_sale_params[pname] = "0"  # 0 = all
        elif "brand" in pname_lower and "code" in pname_lower:
            brand_sale_params[pname] = "0"  # 0 = all
        elif "user" in pname_lower and "code" in pname_lower:
            brand_sale_params[pname] = "0"  # 0 = all
        elif "type" in pname_lower:
            brand_sale_params[pname] = "0"
        elif p["data_type"] in ("int", "bigint", "smallint"):
            brand_sale_params[pname] = 0
        elif p["data_type"] in ("bit"):
            brand_sale_params[pname] = 0
        else:
            brand_sale_params[pname] = "0"

    log(separator("-"))
    log("EXECUTING: sp_BrandsSale_Search_Report (March 2026)")
    log(f"Params used: {brand_sale_params}")
    log(separator("-"))
    log()
    try:
        results = run_sp_brands_sale_search_report(conn, brand_sale_params)
        if results:
            for rs_idx, rs in enumerate(results, 1):
                log(f"Result Set {rs_idx} ({len(rs)} rows):")
                if rs:
                    log(f"Columns: {list(rs[0].keys())}")
                    log(format_rows(rs, max_rows=20))
                log()
        else:
            log("  (no result sets returned)")
    except Exception as e:
        log(f"  ERROR running sp_BrandsSale_Search_Report: {e}")
        log("  Trying alternative param combinations...")
        # Try with date range only
        try:
            alt_params = {}
            for p in params_brand_sale:
                pname = p["param_name"].lstrip("@")
                pname_lower = pname.lower()
                if "fromdate" in pname_lower or "startdate" in pname_lower:
                    alt_params[pname] = "2026-03-01"
                elif "todate" in pname_lower or "enddate" in pname_lower:
                    alt_params[pname] = "2026-03-18"
                elif "month" in pname_lower:
                    alt_params[pname] = 3
                elif "year" in pname_lower:
                    alt_params[pname] = 2026
                elif p["data_type"] in ("int", "bigint", "smallint", "bit"):
                    alt_params[pname] = 0
                else:
                    alt_params[pname] = ""
            log(f"  Alt params: {alt_params}")
            param_str = ", ".join([f"@{k}='{v}'" if isinstance(v, str) else f"@{k}={v}" for k, v in alt_params.items()])
            cursor2 = conn.cursor(as_dict=True)
            cursor2.execute(f"EXEC sp_BrandsSale_Search_Report {param_str}")
            rows = cursor2.fetchall()
            log(f"  Result: {len(rows)} rows")
            log(format_rows(rows, max_rows=20))
        except Exception as e2:
            log(f"  Alt attempt also failed: {e2}")
    log()

    # --- sp_GetBrandWiseTargetandSaleAmount ---
    log(separator("-"))
    log("INSPECTING PARAMS: sp_GetBrandWiseTargetandSaleAmount")
    log(separator("-"))
    params_target = fetch_sp_parameters(conn, "sp_GetBrandWiseTargetandSaleAmount")
    log("Parameters found:")
    for p in params_target:
        log(f"  {p['param_name']}  {p['data_type']}  [{'OUTPUT' if p['is_output'] else 'INPUT'}]")
    log()

    target_params = {}
    for p in params_target:
        pname = p["param_name"].lstrip("@")
        pname_lower = pname.lower()
        if "fromdate" in pname_lower or "startdate" in pname_lower:
            target_params[pname] = "2026-03-01"
        elif "todate" in pname_lower or "enddate" in pname_lower:
            target_params[pname] = "2026-03-18"
        elif "month" in pname_lower and "year" not in pname_lower:
            target_params[pname] = "3"
        elif "year" in pname_lower and "month" not in pname_lower:
            target_params[pname] = "2026"
        elif "monthyear" in pname_lower or ("month" in pname_lower and "year" in pname_lower):
            target_params[pname] = "032026"
        elif "salesorg" in pname_lower or "orgcode" in pname_lower:
            target_params[pname] = "0"
        elif "brand" in pname_lower and "code" in pname_lower:
            target_params[pname] = "0"
        elif "user" in pname_lower and "code" in pname_lower:
            target_params[pname] = "0"
        elif p["data_type"] in ("int", "bigint", "smallint"):
            target_params[pname] = 0
        elif p["data_type"] == "bit":
            target_params[pname] = 0
        else:
            target_params[pname] = "0"

    log(separator("-"))
    log("EXECUTING: sp_GetBrandWiseTargetandSaleAmount (March 2026)")
    log(f"Params used: {target_params}")
    log(separator("-"))
    log()
    try:
        results = run_sp_brand_wise_target(conn, target_params)
        if results:
            for rs_idx, rs in enumerate(results, 1):
                log(f"Result Set {rs_idx} ({len(rs)} rows):")
                if rs:
                    log(f"Columns: {list(rs[0].keys())}")
                    log(format_rows(rs, max_rows=20))
                log()
        else:
            log("  (no result sets returned)")
    except Exception as e:
        log(f"  ERROR running sp_GetBrandWiseTargetandSaleAmount: {e}")
        # Try with just month/year
        try:
            alt2 = {}
            for p in params_target:
                pname = p["param_name"].lstrip("@")
                pname_lower = pname.lower()
                if "month" in pname_lower:
                    alt2[pname] = 3
                elif "year" in pname_lower:
                    alt2[pname] = 2026
                elif p["data_type"] in ("int", "bigint", "smallint", "bit"):
                    alt2[pname] = 0
                else:
                    alt2[pname] = ""
            log(f"  Alt params: {alt2}")
            param_str2 = ", ".join([f"@{k}='{v}'" if isinstance(v, str) else f"@{k}={v}" for k, v in alt2.items()])
            cursor3 = conn.cursor(as_dict=True)
            cursor3.execute(f"EXEC sp_GetBrandWiseTargetandSaleAmount {param_str2}")
            rows3 = cursor3.fetchall()
            log(f"  Result: {len(rows3)} rows")
            log(format_rows(rows3, max_rows=20))
        except Exception as e2:
            log(f"  Alt attempt also failed: {e2}")
    log()

    # =========================================================================
    # PART 3: Summary Table
    # =========================================================================
    log(separator())
    log("PART 3: SUMMARY - WHAT EACH SP RETURNS / PURPOSE")
    log(separator())
    log()

    summaries = {
        "sp_BrandsSale_Search_Report": {
            "purpose": "Main brand sales search report. Aggregates sales data by brand for a given date range, sales org, and user filters.",
            "returns": "Sales summary rows: brand, quantities, amounts, possibly grouped by salesperson or org.",
        },
        "sp_GetBrandWiseTargetandSaleAmount": {
            "purpose": "Compares brand-wise sales targets vs actual sale amounts for a given period.",
            "returns": "Brand name, target amount, actual sale amount, achievement % — one row per brand.",
        },
        "sp_tblItemDateBasedOnBrand": {
            "purpose": "Retrieves item/product data filtered by brand and date range.",
            "returns": "Item list with dates, likely for drilling into brand-level item detail.",
        },
        "sp_tblBrand_SELALL": {
            "purpose": "Simple master-data lookup: returns all brands defined in the system.",
            "returns": "Brand code, brand name (used to populate brand dropdowns in UI).",
        },
        "usp_tblUser_SEL_ByUserTypeCodeWithUserCode": {
            "purpose": "Retrieves users filtered by user type and user code — used to populate user dropdowns.",
            "returns": "User records (UserCode, UserName, UserTypeCode etc.).",
        },
        "sp_tblSalesTeam_SELAll": {
            "purpose": "Returns all sales team members/records — used for team-level filtering.",
            "returns": "Sales team list (TeamCode, TeamName, members).",
        },
        "sp_GetCurrenceCodeBytblSalesOrg": {
            "purpose": "Returns the currency code associated with a given sales organization.",
            "returns": "Currency code (e.g., AED, USD) for the specified sales org.",
        },
        "sp_GetAllSalesOrgsByUserCode": {
            "purpose": "Returns all sales organizations accessible by a specific user — drives org-level access control in UI.",
            "returns": "List of SalesOrg records (OrgCode, OrgName) the user has access to.",
        },
    }

    for sp_name, info in summaries.items():
        log(f"SP: {sp_name}")
        log(f"  Purpose : {info['purpose']}")
        log(f"  Returns : {info['returns']}")
        log()

    # Save to file
    output_text = "\n".join(output_lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(f"\n{'='*80}")
    print(f"OUTPUT SAVED TO: {OUTPUT_FILE}")
    print(f"{'='*80}")

    conn.close()

if __name__ == "__main__":
    main()
