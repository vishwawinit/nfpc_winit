import pymssql

# Connection details from .env
DB_SERVER = "20.203.45.86"
DB_USER = "nfpc"
DB_PASSWORD = "nfpc@!23"
DB_NAME = "NFPCsfaV3_070326"

OUTPUT_FILE = "/Users/mac/Downloads/nfpc-reports-main/etl/logs/sp_definitions.txt"

SP_NAMES = [
    "sp_tblOrder_Total_SalesAndCollection_Dashboard_Reports_ByItem",
    "sp_tblOrder_Total_SalesAndCollection_Dashboard_Reports",
    "SP_StrikeRate_ForDashboard_Reports",
    "SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS",
    "sp_DashboardDetails_Reports_V2",
    "sp_DashboardDetails_Reports_ByItem",
    "sp_tblOrder_Weekly_Dashboard_Reports_V1_NEw_OPTS_ByItem_V1",
    "sp_tblPaymentHeader_Weekly_Dashboard_Reports_V1_New_OPTS",
    "sp_GetSalesmanWiseSales_Dashboard_Reports_V1",
    "sp_GetSalesmanWiseCollection_Dashboard_Reports_By_Item",
    "SP_GetDashboardRouteDetails_Dashboard_Reports_V1_New_OPTS",
    "SP_tblCommonTarget_SELECT_TARGET_FOR_DASHBOARD_ByItem",
    "sp_GetSKUsSold_Formula_Dashboard",
    "Sp_GetAllSuperVisors",
    "Sp_GetallASMCodes",
    "sp_GetAllSalesOrgsByUserCode",
]

def fetch_sp_definitions():
    conn = pymssql.connect(
        server=DB_SERVER,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        timeout=30
    )
    cursor = conn.cursor()

    results = []

    for sp_name in SP_NAMES:
        print(f"Fetching: {sp_name}")
        query = f"SELECT OBJECT_DEFINITION(OBJECT_ID('{sp_name}'))"
        cursor.execute(query)
        row = cursor.fetchone()
        definition = row[0] if row and row[0] else "-- NOT FOUND / NULL --"
        results.append((sp_name, definition))
        print(f"  -> {'Found' if row and row[0] else 'NOT FOUND'}")

    cursor.close()
    conn.close()
    return results

def main():
    print("Connecting to MSSQL (READ-ONLY)...")
    results = fetch_sp_definitions()

    separator = "=" * 100

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("STORED PROCEDURE DEFINITIONS\n")
        f.write(f"Database: {DB_NAME} @ {DB_SERVER}\n")
        f.write(f"Total SPs: {len(SP_NAMES)}\n")
        f.write(separator + "\n\n")

        for sp_name, definition in results:
            f.write(f"SP NAME: {sp_name}\n")
            f.write(separator + "\n")
            f.write(definition)
            f.write("\n\n")
            f.write(separator + "\n\n")

    print(f"\nDone! Output saved to: {OUTPUT_FILE}")
    return results

if __name__ == "__main__":
    results = main()
    # Also print to stdout
    sep = "=" * 100
    for sp_name, definition in results:
        print(f"\n{sep}")
        print(f"SP: {sp_name}")
        print(sep)
        print(definition)
