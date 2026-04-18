"""Authentication endpoint — login by user_code."""
from fastapi import APIRouter, HTTPException
from api.database import query_one

router = APIRouter()

SALESMAN_ROLES  = {'C_PRESALES_VANSALES', 'Vansales', 'Storekeeper'}
SUPERVISOR_ROLES = {'C_SALES_SUPERVISOR', 'FreshSup', 'AMBIENTSUP'}

# Pages salesmen are allowed to see
SALESMAN_PAGES = [
    '/', '/salesman-journey', '/eot-status', '/customer-attendance',
    '/log-report', '/time-management', '/productivity',
]

def _locked_filters(user: dict) -> dict:
    role  = user.get('role_code', '')
    code  = user.get('code', '')
    depot = user.get('depot_code') or ''

    if role == 'HOS':
        return {'hos': code}
    if role == 'NSM':
        return {'depot': depot} if depot else {}
    if role == 'ASM':
        return {'asm': code}
    if role in SUPERVISOR_ROLES:
        return {'supervisor': code}
    if role in SALESMAN_ROLES:
        return {'user_code': code}
    # GCD and all other management roles — no filter lock
    return {}

def _allowed_pages(role: str):
    if role in SALESMAN_ROLES:
        return SALESMAN_PAGES
    return None  # None = all pages


@router.get("/auth/login")
def login(userCode: str):
    user = query_one(
        """SELECT code, name, role_code, role_name,
                  sales_org_code, depot_code, depot_name,
                  reports_to, reports_to_name, is_active
           FROM dim_user
           WHERE UPPER(code) = UPPER(%s)""",
        [userCode.strip()]
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.get('is_active'):
        raise HTTPException(status_code=403, detail="User account is inactive")

    role = user.get('role_code') or ''
    return {
        "user_code":        user['code'],
        "user_name":        (user['name'] or '').strip(),
        "role_code":        role,
        "role_name":        (user['role_name'] or '').strip(),
        "sales_org_code":   user['sales_org_code'],
        "depot_code":       user['depot_code'],
        "depot_name":       (user['depot_name'] or '').strip(),
        "reports_to":       user['reports_to'],
        "reports_to_name":  (user['reports_to_name'] or '').strip(),
        "locked_filters":   _locked_filters(user),
        "allowed_pages":    _allowed_pages(role),
    }
