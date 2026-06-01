#!/usr/bin/env python3
"""
Fetch full definitions of 4 stored procedures from MSSQL (READ-ONLY SELECT queries only).
"""

import pymssql

SERVER = "20.203.45.86"
USER = "nfpc"
PASSWORD = "nfpc@!23"
DATABASE = "NFPCsfaV3_070326"
OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_definitions_extra.txt"

SP_NAMES = [
    "sp_GetSKUsSold_Formula",
    "sp_SalesByItemOfClientDashboard",
    "sp_DashboardSales_SalesPercentage",
    "sp_MarketSalesPerformance",
]

def main():
    print(f"Connecting to {SERVER}/{DATABASE} ...")
    conn = pymssql.connect(server=SERVER, user=USER, password=PASSWORD, database=DATABASE, timeout=60)
    cursor = conn.cursor()

    results = []

    for sp_name in SP_NAMES:
        print(f"\n{'='*80}")
        print(f"STORED PROCEDURE: {sp_name}")
        print('='*80)

        query = f"SELECT OBJECT_DEFINITION(OBJECT_ID('{sp_name}'))"
        cursor.execute(query)
        row = cursor.fetchone()

        if row and row[0]:
            definition = row[0]
        else:
            definition = f"-- [NOT FOUND or no definition returned for {sp_name}]"

        print(definition)

        results.append({
            "name": sp_name,
            "definition": definition
        })

    cursor.close()
    conn.close()

    # Write to output file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("STORED PROCEDURE DEFINITIONS\n")
        f.write("="*80 + "\n")
        f.write(f"Database: {SERVER}/{DATABASE}\n")
        f.write("="*80 + "\n\n")

        for item in results:
            f.write(f"\n{'='*80}\n")
            f.write(f"STORED PROCEDURE: {item['name']}\n")
            f.write(f"{'='*80}\n\n")
            f.write(item["definition"])
            f.write("\n")

    print(f"\n\nAll definitions saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
