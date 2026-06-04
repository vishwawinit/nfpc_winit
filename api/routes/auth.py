"""Authentication endpoint — login by user_code."""
from fastapi import APIRouter, HTTPException
from api.database import query_one, query

router = APIRouter()

# Role priority — highest index wins when a user has multiple roles
ROLE_PRIORITY = [
    'Storekeeper', 'Vansales', 'C_PRESALES_VANSALES',  # salesman level
    'AMBIENTSUP', 'FreshSup', 'C_SALES_SUPERVISOR',     # supervisor level
    'DP', 'BA',                                          # senior supervisor level
    'NSM',                                               # NSM level
    'ASM',                                               # ASM level
    'HOS',                                               # HOS level
    'GCD',                                               # full access
]

SALESMAN_ROLES   = {'C_PRESALES_VANSALES', 'Vansales', 'Storekeeper'}
SUPERVISOR_ROLES = {'C_SALES_SUPERVISOR', 'FreshSup', 'AMBIENTSUP', 'DP', 'BA'}


def _pick_role(roles: list) -> str:
    """Pick the highest-priority role from a list of role codes."""
    best = ''
    best_idx = -1
    for r in roles:
        idx = ROLE_PRIORITY.index(r) if r in ROLE_PRIORITY else -1
        if idx > best_idx:
            best_idx = idx
            best = r
    return best


def _has_subordinates(code: str) -> bool:
    """Check if a user has anyone reporting to them in tbl_user_details."""
    rows = query(
        "SELECT 1 FROM tbl_user_details"
        " WHERE UPPER(reportsto) = UPPER(%s)"
        " AND UPPER(reportsto) != UPPER(usercode)"
        " AND (validto IS NULL OR validto >= CURRENT_DATE)"
        " LIMIT 1",
        [code]
    )
    return len(rows) > 0


def _locked_filters(role: str, code: str) -> dict:
    if role == 'HOS':
        return {'hos': code}
    if role == 'NSM':
        return {'depot': code}
    if role == 'ASM':
        return {'asm': code}
    if role in SUPERVISOR_ROLES:
        # If no one reports to this supervisor, lock to their own data
        # (standalone DP/BA with no team — should still see their own visits)
        if _has_subordinates(code):
            return {'supervisor': code}
        return {'user_code': code}
    if role in SALESMAN_ROLES:
        return {'user_code': code}
    # GCD and above — restrict to their subordinate tree if they manage people
    if _has_subordinates(code):
        return {'gcd': code}
    return {}


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

    # Get all roles from tbl_user_role — more reliable than dim_user.role_code
    role_rows = query(
        "SELECT rolecode FROM tbl_user_role WHERE UPPER(usercode) = UPPER(%s)",
        [userCode.strip()]
    )
    all_roles = [r['rolecode'] for r in role_rows if r['rolecode']]
    # Fall back to dim_user.role_code if tbl_user_role has no entry
    if not all_roles and user.get('role_code'):
        all_roles = [user['role_code']]

    effective_role = _pick_role(all_roles) or (user.get('role_code') or '')

    return {
        "user_code":        user['code'],
        "user_name":        (user['name'] or '').strip(),
        "role_code":        effective_role,
        "role_name":        (user['role_name'] or '').strip(),
        "all_roles":        all_roles,
        "sales_org_code":   user['sales_org_code'],
        "depot_code":       user['depot_code'],
        "depot_name":       (user['depot_name'] or '').strip(),
        "reports_to":       user['reports_to'],
        "reports_to_name":  (user['reports_to_name'] or '').strip(),
        "locked_filters":   _locked_filters(effective_role, user['code']),
        "allowed_pages":    None,
    }
