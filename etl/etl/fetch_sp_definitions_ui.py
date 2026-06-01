#!/usr/bin/env python3
"""
Fetch full definitions of 13 stored procedures from MSSQL (READ-ONLY).
Only SELECT queries are used.
"""

import pymssql
import sys

# Connection settings
SERVER = "20.203.45.86"
USER = "nfpc"
PASSWORD = "nfpc@!23"
DATABASE = "NFPCsfaV3_070326"

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_definitions_ui.txt"

SP_NAMES = [
    "Usp_GetAllDataForDropDownListsBasedOnFilter",
    "sp_tblUser_GetAllSupervisor",
    "SP_SalesOverVieweReport_V1",
    "SP_SalesOverVieweReport_Part2",
    "usp_GetMTDSalesByRouteAndSupervisiorsV2",
    "usp_tblCity_SELALL",
    "USP_GetAllUserNames_ForUser",
    "sp_GetAllSalesOrgsByUserCode",
    "usp_tblRegion",
    "sp_tblRouteCategory_SELALL",
    "sp_tblRoute_SELALL_ByRouteCat",
    "sp_tblCustomerGroup_DELWithArray",
    "sp_GetItemSold_Common",
]

def fetch_sp_definition(cursor, sp_name):
    """Fetch full definition using OBJECT_DEFINITION."""
    cursor.execute(f"SELECT OBJECT_DEFINITION(OBJECT_ID('{sp_name}'))")
    row = cursor.fetchone()
    if row and row[0]:
        return row[0]
    return None

def fetch_sp_params(cursor, sp_name):
    """Fetch parameters for a stored procedure."""
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
        WHERE OBJECT_NAME(p.object_id) = %s
        ORDER BY p.parameter_id
    """, (sp_name,))
    return cursor.fetchall()

def main():
    print(f"Connecting to MSSQL {SERVER}/{DATABASE}...")
    try:
        conn = pymssql.connect(
            server=SERVER,
            user=USER,
            password=PASSWORD,
            database=DATABASE,
            timeout=60
        )
    except Exception as e:
        print(f"ERROR connecting: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    print("Connected successfully.\n")

    results = {}

    for sp_name in SP_NAMES:
        print(f"Fetching: {sp_name} ...")
        definition = fetch_sp_definition(cursor, sp_name)
        params = fetch_sp_params(cursor, sp_name)
        results[sp_name] = {
            "definition": definition,
            "params": params
        }
        if definition:
            print(f"  -> Got definition ({len(definition)} chars), {len(params)} params")
        else:
            print(f"  -> NOT FOUND or no definition")

    conn.close()

    # Write output file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write("STORED PROCEDURE DEFINITIONS - NFPC Reports UI SPs\n")
        f.write(f"Database: {SERVER}/{DATABASE}\n")
        f.write("=" * 100 + "\n\n")

        for sp_name in SP_NAMES:
            data = results[sp_name]
            f.write("\n" + "=" * 100 + "\n")
            f.write(f"STORED PROCEDURE: {sp_name}\n")
            f.write("=" * 100 + "\n\n")

            # Parameters section
            f.write("--- PARAMETERS ---\n")
            if data["params"]:
                for p in data["params"]:
                    param_name, data_type, max_len, precision, scale, is_output, has_default, default_val = p
                    direction = "OUTPUT" if is_output else "INPUT"
                    type_info = data_type
                    if data_type in ("varchar", "nvarchar", "char", "nchar"):
                        type_info += f"({max_len if max_len != -1 else 'MAX'})"
                    elif data_type in ("decimal", "numeric"):
                        type_info += f"({precision},{scale})"
                    default_str = f" = {default_val}" if has_default and default_val is not None else ""
                    f.write(f"  {param_name}  {type_info}  [{direction}]{default_str}\n")
            else:
                f.write("  (no parameters)\n")

            # Full definition
            f.write("\n--- FULL DEFINITION ---\n")
            if data["definition"]:
                f.write(data["definition"])
            else:
                f.write("  *** DEFINITION NOT FOUND - SP may not exist or may be encrypted ***\n")
            f.write("\n")

    print(f"\nOutput written to: {OUTPUT_FILE}")

    # Print everything to stdout as well
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    print(content)

if __name__ == "__main__":
    main()
