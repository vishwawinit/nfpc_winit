import pyodbc

def get_conn():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=20.203.45.86;DATABASE=NFPCsfaV3_070326;UID=nfpc;PWD=nfpc@!23',
        timeout=20
    )

# 1. What data type is Attribute17?
conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='tblTrxDetail' AND COLUMN_NAME='Attribute17'")
row = cur.fetchone()
print(f"Attribute17 column type: {row[1]}({row[2]})")
conn.close()

# 2. Sample values
conn = get_conn()
cur = conn.cursor()
cur.execute("""
SELECT TOP 10 TD.Attribute17, TD.ItemCode, TH.TrxType
FROM tblTrxDetail TD JOIN tblTrxHeader TH ON TH.TrxCode=TD.TrxCode
WHERE TH.TRXStatus=200 AND YEAR(TH.TrxDate)=2026 AND MONTH(TH.TrxDate)=3
  AND TD.Attribute17 IS NOT NULL AND TD.Attribute17 <> '' AND TD.Attribute17 <> '0'
""")
rows = cur.fetchall()
print("\nSample Attribute17 values:")
for r in rows:
    print(f"  Attr17='{r[0]}' Item={r[1]} TrxType={r[2]}")
conn.close()

# 3. Total impact
conn = get_conn()
cur = conn.cursor()
cur.execute("""
SELECT
    COUNT(*) AS rows_nonzero,
    SUM(TRY_CAST(TD.Attribute17 AS FLOAT)) AS total_amount
FROM tblTrxDetail TD JOIN tblTrxHeader TH ON TH.TrxCode=TD.TrxCode
WHERE TH.TRXStatus=200 AND YEAR(TH.TrxDate)=2026 AND MONTH(TH.TrxDate)=3
  AND TRY_CAST(TD.Attribute17 AS FLOAT) IS NOT NULL
  AND TRY_CAST(TD.Attribute17 AS FLOAT) <> 0
""")
r = cur.fetchone()
print(f"\nRows with non-zero Attribute17: {r[0]}, Total amount: {round(r[1],2) if r[1] else 0}")
conn.close()
