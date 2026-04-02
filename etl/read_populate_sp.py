import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=20.203.45.86;DATABASE=NFPCsfaV3_070326;UID=nfpc;PWD=nfpc@!23',
    timeout=15
)
cur = conn.cursor()
cur.execute("SELECT definition FROM sys.sql_modules WHERE object_id = OBJECT_ID('usp_Populate_tblRouteSalesSummary_DataByItem')")
row = cur.fetchone()
print(row[0])
conn.close()
