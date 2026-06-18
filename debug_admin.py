from api.database import query
from api.models import _get_all_subordinates

# All subordinates under admin
subs = _get_all_subordinates(['admin'])
print(f'Admin subordinates count: {len(subs)}')
print(f'Subs list: {subs}')

# Direct reports to admin
rows = query(
    "SELECT usercode, reportsto FROM tbl_user_details "
    "WHERE UPPER(reportsto)=UPPER(%s) AND (validto IS NULL OR validto >= CURRENT_DATE)",
    ['admin']
)
print(f'\nDirect reports to admin ({len(rows)}):')
for r in rows:
    print(' ', r)

# UAFASA01 and UAVITO01 details
rows2 = query(
    "SELECT td.usercode, tu.role_code, td.reportsto FROM tbl_user_details td "
    "JOIN tbl_user tu ON UPPER(tu.code)=UPPER(td.usercode) "
    "WHERE UPPER(td.usercode) IN ('UAFASA01','UAVITO01') AND (td.validto IS NULL OR td.validto >= CURRENT_DATE)",
    []
)
print(f'\nUAFASA01/UAVITO01 details:')
for r in rows2:
    print(' ', r)

# Who reports to UAFASA01
rows3 = query(
    "SELECT td.usercode, tu.role_code FROM tbl_user_details td "
    "JOIN tbl_user tu ON UPPER(tu.code)=UPPER(td.usercode) "
    "WHERE UPPER(td.reportsto)='UAFASA01' AND (td.validto IS NULL OR td.validto >= CURRENT_DATE) LIMIT 10",
    []
)
print(f'\nUsers reporting to UAFASA01 ({len(rows3)}):')
for r in rows3:
    print(' ', r)

# dim_user for admin
rows4 = query("SELECT code, role_code, reports_to FROM dim_user WHERE UPPER(code)='ADMIN'", [])
print(f'\ndim_user admin: {rows4}')

# Check roles of admin's subs
rows5 = query(
    "SELECT tu.code, tu.role_code FROM tbl_user tu "
    "WHERE UPPER(tu.code) IN ('UAFASA01','UAVITO01','UASAHU01','UABIAD01','UABIBH01','UAMOMA01','UASHBA02','UAAHJA02','UAMOAM01','UAEMAH01')",
    []
)
print(f'\nRoles of admin subs (supervisor-level):')
for r in rows5:
    print(' ', r)
