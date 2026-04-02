import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=20.203.45.86;DATABASE=NFPCsfaV3_070326;UID=nfpc;PWD=nfpc@!23',
    timeout=15
)
cur = conn.cursor()

# Find SPs referencing either sales summary table
cur.execute("""
SELECT DISTINCT o.name AS sp_name
FROM sys.sql_modules m
JOIN sys.objects o ON m.object_id = o.object_id
WHERE o.type = 'P'
  AND (
    m.definition LIKE '%tblRouteSalesSummaryByItem%'
    OR m.definition LIKE '%tblRouteSalesSummaryByItemCustomer%'
  )
ORDER BY o.name
""")
rows = cur.fetchall()
print("=== SPs referencing tblRouteSalesSummaryByItem / tblRouteSalesSummaryByItemCustomer ===")
for r in rows:
    print(" -", r[0])

# Also check which SPs populate (INSERT/UPDATE/MERGE) these tables
print("\n=== SPs that WRITE to these tables ===")
cur.execute("""
SELECT DISTINCT o.name AS sp_name
FROM sys.sql_modules m
JOIN sys.objects o ON m.object_id = o.object_id
WHERE o.type = 'P'
  AND (
    (m.definition LIKE '%INSERT%tblRouteSalesSummaryByItem%' OR m.definition LIKE '%MERGE%tblRouteSalesSummaryByItem%' OR m.definition LIKE '%UPDATE%tblRouteSalesSummaryByItem%')
    OR (m.definition LIKE '%INSERT%tblRouteSalesSummaryByItemCustomer%' OR m.definition LIKE '%MERGE%tblRouteSalesSummaryByItemCustomer%')
  )
ORDER BY o.name
""")
rows2 = cur.fetchall()
for r in rows2:
    print(" -", r[0])

conn.close()
