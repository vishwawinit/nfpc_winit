import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=20.203.45.86;DATABASE=NFPCsfaV3_070326;UID=nfpc;PWD=nfpc@!23',
    timeout=15
)
cur = conn.cursor()

SPS = [
    'RouteSalesSummaryByIC_Insert',
    'sp_DashboardSales_New',
]

for sp in SPS:
    cur.execute("SELECT definition FROM sys.sql_modules WHERE object_id = OBJECT_ID(?)", sp)
    row = cur.fetchone()
    print(f"\n{'='*80}")
    print(f"SP: {sp}")
    print('='*80)
    if row:
        # Print full definition
        print(row[0])
    else:
        print("  (not found)")

conn.close()
