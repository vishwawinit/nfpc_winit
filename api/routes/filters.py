"""Filter dropdown data endpoints."""
from fastapi import APIRouter
from api.database import query

router = APIRouter()

# Role-code constants for hierarchy identification
ROLE_CODES_HOS = ('HOS',)
ROLE_CODES_ASM = ('ASM',)
ROLE_CODES_SUPERVISOR = ('FreshSup', 'AMBIENTSUP', 'C_SALES_SUPERVISOR')
ROLE_CODES_SALESMAN = ('C_PRESALES_VANSALES', 'Vansales')

@router.get("/filters/sales-orgs")
def get_sales_orgs():
    return query("SELECT code, name FROM dim_sales_org WHERE is_active = true ORDER BY name")

@router.get("/filters/routes")
def get_routes(sales_org: str = None, depot: str = None, supervisor: str = None, asm: str = None, hos: str = None):
    """Routes, optionally filtered by sales_org, depot, supervisor, asm, or hos.
    When hierarchy filters are given, only return routes assigned to matching users."""
    # If hierarchy filters given, resolve to user codes first, then get their routes
    user_codes = _resolve_hierarchy_to_users(depot=depot, supervisor=supervisor, asm=asm, hos=hos, sales_org=sales_org)
    if user_codes is not None:
        if not user_codes:
            return []
        placeholders = ','.join(['%s'] * len(user_codes))
        base = f"SELECT DISTINCT r.code, r.name FROM dim_route r JOIN dim_user u ON u.route_code = r.code WHERE r.is_active = true AND u.code IN ({placeholders})"
        params = list(user_codes)
        if sales_org:
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            base += f" AND r.sales_org_code IN ({org_ph})"
            params.extend(orgs)
        return query(f"{base} ORDER BY r.name", params)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        if len(orgs) == 1:
            return query("SELECT code, name FROM dim_route WHERE is_active = true AND sales_org_code = %s ORDER BY name", [orgs[0]])
        placeholders = ','.join(['%s'] * len(orgs))
        return query(f"SELECT code, name FROM dim_route WHERE is_active = true AND sales_org_code IN ({placeholders}) ORDER BY name", orgs)
    return query("SELECT code, name FROM dim_route WHERE is_active = true ORDER BY name")

@router.get("/filters/users")
def get_users(sales_org: str = None, supervisor: str = None, depot: str = None, asm: str = None, hos: str = None):
    """All active users, optionally filtered by hierarchy (recursive subordinates).
    Cascading: hos -> asm -> supervisor -> all subordinates at any depth."""
    from api.models import _get_all_subordinates

    # Determine manager codes for recursive resolution
    manager_codes = None
    if hos and not asm:
        hos_codes = [v.strip() for v in hos.split(',') if v.strip()]
        manager_codes = hos_codes
    if asm:
        manager_codes = [v.strip() for v in asm.split(',') if v.strip()]
    if supervisor:
        sup_codes = [v.strip() for v in supervisor.split(',') if v.strip()]
        if manager_codes:
            # Intersect: only supervisors that are under the selected ASM/HOS
            all_under = _get_all_subordinates(manager_codes)
            sup_codes = [s for s in sup_codes if s in all_under]
            if not sup_codes:
                return []
        manager_codes = sup_codes

    conditions = ["is_active = true"]
    params = []

    if manager_codes:
        all_subs = _get_all_subordinates(manager_codes)
        if not all_subs:
            return []
        ph = ','.join(['%s'] * len(all_subs))
        conditions.append(f"code IN ({ph})")
        params.extend(all_subs)

    if depot:
        depots = [v.strip() for v in depot.split(',') if v.strip()]
        dep_ph = ','.join(['%s'] * len(depots))
        conditions.append(f"depot_code IN ({dep_ph})")
        params.extend(depots)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)

@router.get("/filters/customers")
def get_customers(sales_org: str = None):
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        if len(orgs) == 1:
            return query("SELECT code, name FROM dim_customer WHERE is_active = true AND sales_org_code = %s ORDER BY name", [orgs[0]])
        placeholders = ','.join(['%s'] * len(orgs))
        return query(f"SELECT code, name FROM dim_customer WHERE is_active = true AND sales_org_code IN ({placeholders}) ORDER BY name", orgs)
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
    """Route categories (Van Sales, Pre-Sales, etc.)."""
    return query("SELECT DISTINCT route_type AS code, route_type AS name FROM dim_route WHERE route_type IS NOT NULL AND TRIM(route_type) != '' ORDER BY route_type")

@router.get("/filters/routes-by-category")
def get_routes_by_category(route_type: str = None, sales_org: str = None):
    """Routes filtered by route category."""
    conditions = ["is_active = true"]
    params = []
    if route_type and route_type != '0':
        conditions.append("route_type = %s")
        params.append(route_type)
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)
    where = " AND ".join(conditions)
    return query(f"SELECT code, name, route_type, sales_org_code FROM dim_route WHERE {where} ORDER BY name", params)

@router.get("/filters/cities")
def get_cities():
    """All cities."""
    return query("SELECT code, name, region_code FROM dim_city ORDER BY name")

@router.get("/filters/regions")
def get_regions():
    """All regions."""
    return query("SELECT code, name FROM dim_region ORDER BY name")

@router.get("/filters/depots")
def get_depots(sales_org: str = None, asm: str = None):
    """Depots sourced from dim_region. All 3 regions always available."""
    return query("SELECT code, name FROM dim_region ORDER BY name")

@router.get("/filters/supervisors")
def get_supervisors(sales_org: str = None, asm: str = None, hos: str = None):
    """Supervisors identified by role_code. Optionally filtered by sales_org, asm, and hos."""
    sup_ph = ','.join(['%s'] * len(ROLE_CODES_SUPERVISOR))
    conditions = [f"role_code IN ({sup_ph})", "is_active = true"]
    params = list(ROLE_CODES_SUPERVISOR)

    # HOS selected but no ASM: resolve HOS -> ASMs first
    if hos and not asm:
        hos_codes = [v.strip() for v in hos.split(',') if v.strip()]
        h_ph = ','.join(['%s'] * len(hos_codes))
        asm_role_ph = ','.join(['%s'] * len(ROLE_CODES_ASM))
        asm_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND role_code IN ({asm_role_ph}) AND reports_to IN ({h_ph})",
            list(ROLE_CODES_ASM) + hos_codes
        )
        asm = ','.join(r['code'] for r in asm_rows) if asm_rows else None
        if not asm:
            return []

    if asm:
        asm_codes = [v.strip() for v in asm.split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_codes))
        conditions.append(f"reports_to IN ({asm_ph})")
        params.extend(asm_codes)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)

@router.get("/filters/hos")
def get_hos(sales_org: str = None):
    """Head of Sales identified by role_code."""
    hos_ph = ','.join(['%s'] * len(ROLE_CODES_HOS))
    conditions = [f"role_code IN ({hos_ph})", "is_active = true"]
    params = list(ROLE_CODES_HOS)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)

@router.get("/filters/asms")
def get_asms(sales_org: str = None, hos: str = None):
    """ASMs identified by role_code. Optionally filtered by sales_org and hos."""
    asm_ph = ','.join(['%s'] * len(ROLE_CODES_ASM))
    conditions = [f"role_code IN ({asm_ph})", "is_active = true"]
    params = list(ROLE_CODES_ASM)

    if hos:
        hos_codes = [v.strip() for v in hos.split(',') if v.strip()]
        h_ph = ','.join(['%s'] * len(hos_codes))
        conditions.append(f"reports_to IN ({h_ph})")
        params.extend(hos_codes)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_user WHERE {where} ORDER BY name", params)


def _resolve_hierarchy_to_users(depot=None, supervisor=None, asm=None, hos=None, sales_org=None):
    """Helper: resolve hierarchy filters to a list of user codes using recursive subordinate lookup.
    Returns None if no hierarchy filters, [] if no match, or list of user codes."""
    from api.models import _get_all_subordinates

    if not depot and not supervisor and not asm and not hos:
        return None

    # Determine manager codes
    manager_codes = None
    if hos and not asm:
        manager_codes = [v.strip() for v in hos.split(',') if v.strip()]
    if asm:
        manager_codes = [v.strip() for v in asm.split(',') if v.strip()]
    if supervisor:
        sup_codes = [v.strip() for v in supervisor.split(',') if v.strip()]
        if manager_codes:
            all_under = _get_all_subordinates(manager_codes)
            sup_codes = [s for s in sup_codes if s in all_under]
            if not sup_codes:
                return []
        manager_codes = sup_codes

    all_users = None
    if manager_codes:
        all_users = _get_all_subordinates(manager_codes)
        if not all_users:
            return []

    # Apply depot filter
    if depot:
        depots = [v.strip() for v in depot.split(',') if v.strip()]
        dep_ph = ','.join(['%s'] * len(depots))
        depot_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND depot_code IN ({dep_ph})",
            depots
        )
        depot_users = set(r['code'] for r in depot_rows)
        if all_users is not None:
            all_users = [u for u in all_users if u in depot_users]
        else:
            all_users = list(depot_users)

    # Apply sales_org filter
    if sales_org and all_users is not None:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})",
            orgs
        )
        org_users = set(r['code'] for r in org_rows)
        all_users = [u for u in all_users if u in org_users]

    if all_users is None:
        return None
    return all_users if all_users else []
