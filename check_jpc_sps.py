#!/usr/bin/env python3
"""Fetch definitions of JPC and related SPs. READ-ONLY on MSSQL."""
import pymssql

MSSQL = dict(server='20.203.45.86', user='nfpc', password='nfpc@!23',
             database='NFPCsfaV3_070326', timeout=60)

SPS = [
    'sp_GetJourneyPlanComplianceReportNew',
    'sp_GetJourneyPlanComplianceReportNew_Count',
    'sp_GetJourneyPlanComplianceReportNew_Mapping',
    'Usp_GetAllDataForDropDownListsBasedOnFilter',
    'USP_GetAllUserCodes',
    'sp_GetAllSalesOrgsByUserCode',
    'sp_tblChannel_SELALL',
]

conn = pymssql.connect(**MSSQL)
cur = conn.cursor(as_dict=True)
print("Connected.\n")

for sp in SPS:
    print("=" * 80)
    print(f"SP: {sp}")
    print("=" * 80)
    cur.execute(
        "SELECT m.definition FROM sys.objects o "
        "JOIN sys.sql_modules m ON o.object_id = m.object_id "
        "WHERE o.type = 'P' AND o.name = %s",
        (sp,)
    )
    row = cur.fetchone()
    if row and row['definition']:
        print(row['definition'])
    else:
        print("[NOT FOUND]")
    print()

conn.close()
print("Done.")
