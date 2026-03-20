"""Filter dropdown data endpoints.

Hierarchy: HOS → ASM → Supervisor → Salesman → Route
All hierarchy filters use recursive subordinate resolution via _get_all_subordinates.
"""
from fastapi import APIRouter
from api.database import query
from api.models import _get_all_subordinates

router = APIRouter()

# Role-code constants for hierarchy identification
ROLE_CODES_HOS = ('HOS',)
ROLE_CODES_ASM = ('ASM',)
ROLE_CODES_SUPERVISOR = ('FreshSup', 'AMBIENTSUP', 'C_SALES_SUPERVISOR')
ROLE_CODES_SALESMAN = ('C_PRESALES_VANSALES', 'Vansales')


def _split(val, upper=False):
    """Split comma-separated string into list of stripped values."""
    if not val:
        return []
    parts = [v.strip() for v in val.split(',') if v.strip()]
    return [v.upper() for v in parts] if upper else parts


def _in_clause(col, vals, conditions, params):
    """Add an IN clause for a list of values."""
    if not vals:
        return
    ph = ','.join(['%s'] * len(vals))
    conditions.append(f"{col} IN ({ph})")
    params.extend(vals)


def _get_all_users_under(hos=None, asm=None, supervisor=None):
    """Get all recursive subordinate codes from the deepest hierarchy level specified.
    Returns set of user codes or None if no hierarchy filter."""
    manager_codes = None

    if hos:
        manager_codes = _split(hos, upper=True)
    if asm:
        asm_codes = _split(asm, upper=True)
        if manager_codes:
            # Intersect: only ASMs that are under the selected HOS
            all_under_hos = set(_get_all_subordinates(manager_codes))
            asm_codes = [a for a in asm_codes if a in all_under_hos]
            if not asm_codes:
                return set()
        manager_codes = asm_codes
    if supervisor:
        sup_codes = _split(supervisor, upper=True)
        if manager_codes:
            all_under = set(_get_all_subordinates(manager_codes))
            sup_codes = [s for s in sup_codes if s in all_under]
            if not sup_codes:
                return set()
        manager_codes = sup_codes

    if manager_codes:
        subs = _get_all_subordinates(manager_codes)
        return set(subs) if subs else set()
    return None


@router.get("/filters/sales-orgs")
def get_sales_orgs():
    return query("SELECT code, name FROM dim_sales_org WHERE is_active = true ORDER BY name")


@router.get("/filters/hos")
def get_hos(sales_org: str = None):
    """HOS users. When sales_org given, include HOS who manage users in that org
    (cross-org lookup since HOS can manage multiple orgs)."""
    hos_ph = ','.join(['%s'] * len(ROLE_CODES_HOS))
    base = f"role_code IN ({hos_ph}) AND is_active = true"
    params = list(ROLE_CODES_HOS)

    if sales_org:
        orgs = _split(sales_org)
        org_ph = ','.join(['%s'] * len(orgs))
        # Include HOS whose own sales_org matches OR who have ANY subordinate in that org
        return query(
            f"SELECT DISTINCT code, name FROM dim_user WHERE {base} AND ("
            f"  sales_org_code IN ({org_ph}) OR "
            f"  code IN ("
            f"    WITH RECURSIVE subs AS ("
            f"      SELECT code, reports_to FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})"
            f"      UNION"
            f"      SELECT u.code, u.reports_to FROM dim_user u JOIN subs s ON u.code = s.reports_to WHERE u.is_active = true"
            f"    ) SELECT DISTINCT code FROM subs"
            f"  )"
            f") ORDER BY name",
            params + orgs + orgs
        )

    return query(f"SELECT code, name FROM dim_user WHERE {base} ORDER BY name", params)


@router.get("/filters/asms")
def get_asms(sales_org: str = None, hos: str = None):
    """ASMs. When HOS given, use recursive lookup to find all ASMs under HOS (not just direct reports)."""
    asm_ph = ','.join(['%s'] * len(ROLE_CODES_ASM))
    conditions = [f"role_code IN ({asm_ph})", "is_active = true"]
    params = list(ROLE_CODES_ASM)

    if hos:
        # Recursively find all subordinates of HOS, then filter to ASM role
        hos_codes = _split(hos, upper=True)
        all_subs = _get_all_subordinates(hos_codes)
        if not all_subs:
            return []
        _in_clause("code", all_subs, conditions, params)

    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)


@router.get("/filters/depots")
def get_depots(sales_org: str = None, asm: str = None, hos: str = None):
    """Depots (regions). When hierarchy given, only show depots that have users under that hierarchy."""
    if not hos and not asm:
        # No hierarchy filter — return all depots
        return query("SELECT code, name FROM dim_region ORDER BY name")

    # Get all users under the hierarchy, then find their depot codes
    all_subs_set = _get_all_users_under(hos=hos, asm=asm)
    if all_subs_set is not None and not all_subs_set:
        return []

    conditions = ["is_active = true", "depot_code IS NOT NULL", "depot_code != ''"]
    params = []

    if all_subs_set:
        _in_clause("code", list(all_subs_set), conditions, params)
    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)

    where = " AND ".join(conditions)
    depot_codes = query(f"SELECT DISTINCT depot_code FROM dim_user WHERE {where}", params)
    if not depot_codes:
        return []

    codes = [r['depot_code'] for r in depot_codes]
    ph = ','.join(['%s'] * len(codes))
    return query(f"SELECT code, name FROM dim_region WHERE code IN ({ph}) ORDER BY name", codes)


@router.get("/filters/supervisors")
def get_supervisors(sales_org: str = None, asm: str = None, hos: str = None):
    """Supervisors. Uses recursive subordinate lookup under HOS/ASM."""
    sup_ph = ','.join(['%s'] * len(ROLE_CODES_SUPERVISOR))
    conditions = [f"role_code IN ({sup_ph})", "is_active = true"]
    params = list(ROLE_CODES_SUPERVISOR)

    if hos or asm:
        all_subs_set = _get_all_users_under(hos=hos, asm=asm)
        if all_subs_set is not None:
            if not all_subs_set:
                return []
            _in_clause("code", list(all_subs_set), conditions, params)

    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)


@router.get("/filters/users")
def get_users(sales_org: str = None, supervisor: str = None, depot: str = None, asm: str = None, hos: str = None):
    """Salesmen only. Uses recursive subordinate lookup for hierarchy filters."""
    salesman_ph = ','.join(['%s'] * len(ROLE_CODES_SALESMAN))
    conditions = ["is_active = true", f"role_code IN ({salesman_ph})"]
    params = list(ROLE_CODES_SALESMAN)

    # Resolve hierarchy
    all_subs_set = _get_all_users_under(hos=hos, asm=asm, supervisor=supervisor)
    if all_subs_set is not None:
        if not all_subs_set:
            return []
        _in_clause("code", list(all_subs_set), conditions, params)

    if depot:
        _in_clause("depot_code", _split(depot), conditions, params)

    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)


@router.get("/filters/routes")
def get_routes(sales_org: str = None, depot: str = None, supervisor: str = None, asm: str = None, hos: str = None):
    """Routes. When hierarchy filters given, only return routes assigned to matching users."""
    all_subs_set = _get_all_users_under(hos=hos, asm=asm, supervisor=supervisor)

    if all_subs_set is not None or depot:
        # Build user code list from hierarchy + depot
        user_conditions = ["is_active = true"]
        user_params = []

        if all_subs_set is not None:
            if not all_subs_set:
                return []
            _in_clause("code", list(all_subs_set), user_conditions, user_params)

        if depot:
            _in_clause("depot_code", _split(depot), user_conditions, user_params)

        if sales_org:
            _in_clause("sales_org_code", _split(sales_org), user_conditions, user_params)

        user_where = " AND ".join(user_conditions)
        # Get route_codes from dim_user (assigned routes)
        user_rows = query(f"SELECT DISTINCT route_code FROM dim_user WHERE {user_where} AND route_code IS NOT NULL", user_params)
        route_codes = set(r['route_code'] for r in user_rows)

        # Also get routes from transaction data (some users have NULL route_code in dim_user)
        if all_subs_set:
            user_list = list(all_subs_set)
            u_ph = ','.join(['%s'] * len(user_list))
            txn_routes = query(f"SELECT DISTINCT route_code FROM rpt_customer_visits WHERE user_code IN ({u_ph})", user_list)
            route_codes |= set(r['route_code'] for r in txn_routes if r['route_code'])

        if not route_codes:
            return []

        rc_list = list(route_codes)
        ph = ','.join(['%s'] * len(rc_list))
        result = query(f"SELECT code, name FROM dim_route WHERE is_active = true AND code IN ({ph}) ORDER BY name", rc_list)
        # If dim_route doesn't have all codes, include them anyway
        if len(result) < len(rc_list):
            found = set(r['code'] for r in result)
            for rc in rc_list:
                if rc not in found:
                    result.append({'code': rc, 'name': rc})
            result.sort(key=lambda x: x['name'] or x['code'])
        return result

    if sales_org:
        orgs = _split(sales_org)
        org_ph = ','.join(['%s'] * len(orgs))
        return query(f"SELECT code, name FROM dim_route WHERE is_active = true AND sales_org_code IN ({org_ph}) ORDER BY name", orgs)

    return query("SELECT code, name FROM dim_route WHERE is_active = true ORDER BY name")


@router.get("/filters/customers")
def get_customers(sales_org: str = None):
    if sales_org:
        orgs = _split(sales_org)
        org_ph = ','.join(['%s'] * len(orgs))
        return query(f"SELECT code, name FROM dim_customer WHERE is_active = true AND sales_org_code IN ({org_ph}) ORDER BY name", orgs)
    return query("SELECT DISTINCT code, name FROM dim_customer WHERE is_active = true ORDER BY name")


@router.get("/filters/items")
def get_items():
    return query("SELECT code, name FROM dim_item WHERE is_active = true ORDER BY name")


@router.get("/filters/brands")
def get_brands():
    return query("SELECT DISTINCT TRIM(brand_code) as code, brand_name as name FROM dim_item WHERE brand_code IS NOT NULL AND TRIM(brand_code) != '' ORDER BY brand_name")


@router.get("/filters/channels")
def get_channels():
    return query("SELECT code, name FROM dim_channel ORDER BY name")


@router.get("/filters/categories")
def get_categories():
    return query("SELECT DISTINCT category_code as code, category_name as name FROM dim_item WHERE category_code IS NOT NULL ORDER BY category_name")


@router.get("/filters/route-categories")
def get_route_categories():
    return query("SELECT DISTINCT route_type AS code, route_type AS name FROM dim_route WHERE route_type IS NOT NULL AND TRIM(route_type) != '' ORDER BY route_type")


@router.get("/filters/routes-by-category")
def get_routes_by_category(route_type: str = None, sales_org: str = None):
    conditions = ["is_active = true"]
    params = []
    if route_type and route_type != '0':
        conditions.append("route_type = %s")
        params.append(route_type)
    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)
    where = " AND ".join(conditions)
    return query(f"SELECT code, name, route_type, sales_org_code FROM dim_route WHERE {where} ORDER BY name", params)


@router.get("/filters/cities")
def get_cities():
    return query("SELECT code, name, region_code FROM dim_city ORDER BY name")


@router.get("/filters/regions")
def get_regions():
    return query("SELECT code, name FROM dim_region ORDER BY name")
