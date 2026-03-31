"""Run MSSQL stored procedures to populate February 2026 summary data, then trigger ETL."""
import os
import sys
import pymssql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DATE_FROM = '20260201'
DATE_TO = '20260228'

SPS = [
    ("usp_Populate_RouteCoverageReportSummary_Data", DATE_FROM, DATE_TO),
    ("usp_Populate_tblRouteSalesSummary_DataByItem", DATE_FROM, DATE_TO),
    ("usp_insert_RouteSalesSummaryByItemCustomer", DATE_FROM, DATE_TO),
]

def run():
    print(f"Connecting to MSSQL {os.environ['DB_SERVER']} / {os.environ['DB_NAME']}...")
    conn = pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
        login_timeout=30,
        timeout=3600,
    )
    cur = conn.cursor()
    for sp, d1, d2 in SPS:
        print(f"\n  EXEC {sp} '{d1}', '{d2}'  ...", flush=True)
        cur.execute(f"EXEC {sp} '{d1}', '{d2}'")
        conn.commit()
        print(f"  Done", flush=True)
    cur.close()
    conn.close()
    print("\nAll SPs completed successfully.")

if __name__ == '__main__':
    run()
