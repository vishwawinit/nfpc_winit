import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=20.203.45.86;DATABASE=NFPCsfaV3_070326;UID=nfpc;PWD=nfpc@!23',
    timeout=30
)
cur = conn.cursor()

# New formula total (with Attribute17)
cur.execute("""
SELECT
    COUNT(*) AS rows,
    SUM(
        CASE WHEN TH.TrxType=4 THEN -1 ELSE 1 END * ABS(
            (TD.QuantityLevel1 * TD.PriceUsedLevel1)
            - ISNULL(TD.TotalDiscountAmount, 0)
            + ISNULL(TD.ExciseDutyTaxAmount, 0)
            + ISNULL(TRY_CAST(TD.Attribute17 AS FLOAT), 0)
        )
    ) AS total_with_attr17,
    SUM(
        CASE WHEN TH.TrxType=4 THEN -1 ELSE 1 END * ABS(
            (TD.QuantityLevel1 * TD.PriceUsedLevel1)
            - ISNULL(TD.TotalDiscountAmount, 0)
            + ISNULL(TD.ExciseDutyTaxAmount, 0)
        )
    ) AS total_without_attr17
FROM tblTrxHeader TH WITH(NOLOCK)
INNER JOIN tblTrxDetail TD WITH(NOLOCK) ON TD.TrxCode = TH.TrxCode
WHERE TH.TRXStatus = 200
  AND TH.TrxDate >= '2026-03-07' AND TH.TrxDate < '2026-03-08'
""")
r = cur.fetchone()
print(f"=== March 7 2026 ===")
print(f"Rows: {r[0]}")
print(f"Total WITH Attribute17:    {round(r[1], 2)}")
print(f"Total WITHOUT Attribute17: {round(r[2], 2)}")
print(f"Attribute17 contribution:  {round(r[1]-r[2], 2)}")

# Old formula (tblRouteSalesSummaryByItemCustomer)
cur.execute("""
SELECT SUM(TotalSales) AS total_old
FROM tblRouteSalesSummaryByItemCustomer WITH(NOLOCK)
WHERE CAST(Date AS DATE) = '2026-03-07'
""")
r2 = cur.fetchone()
print(f"Old table total:           {round(r2[0], 2) if r2[0] else 0}")

conn.close()
print("\nDashboard API shows: 2858597.53 for March 7")
print("Journey (RSIC old) shows:  2883020.41 for March 7")
