"""Filter dropdown data endpoints."""
from fastapi import APIRouter
from api.database import query

router = APIRouter()

@router.get("/filters/sales-orgs")
def get_sales_orgs():
    return query("SELECT code, name FROM dim_sales_org WHERE is_active = true ORDER BY name")

@router.get("/filters/routes")
def get_routes(sales_org: str = None, depot: str = None, supervisor: str = None, asm: str = None):
    """Routes, optionally filtered by sales_org, depot, supervisor, or asm.
    When hierarchy filters are given, only return routes assigned to matching users."""
    # If hierarchy filters given, resolve to user codes first, then get their routes
    user_codes = _resolve_hierarchy_to_users(depot=depot, supervisor=supervisor, asm=asm, sales_org=sales_org)
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
def get_users(sales_org: str = None, supervisor: str = None, depot: str = None, asm: str = None):
    """Salesmen, optionally filtered by sales_org, supervisor, depot, or asm.
    Cascading: asm -> supervisors under asm -> users under those supervisors."""
    conditions = ["is_active = true"]
    params = []

    if asm:
        # ASM selected: get supervisors under this ASM, then salesmen under those supervisors
        asm_codes = [v.strip() for v in asm.split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_codes))
        # Supervisors who report to ASM
        sup_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND reports_to IN ({asm_ph})",
            asm_codes
        )
        sup_codes = [r['code'] for r in sup_rows]
        if supervisor:
            # Intersect with selected supervisors
            sel_sups = set(v.strip() for v in supervisor.split(',') if v.strip())
            sup_codes = [c for c in sup_codes if c in sel_sups]
        if not sup_codes:
            return []
        sup_ph = ','.join(['%s'] * len(sup_codes))
        conditions.append(f"reports_to IN ({sup_ph})")
        params.extend(sup_codes)
    elif supervisor:
        sups = [v.strip() for v in supervisor.split(',') if v.strip()]
        sup_ph = ','.join(['%s'] * len(sups))
        conditions.append(f"reports_to IN ({sup_ph})")
        params.extend(sups)

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
    return query("SELECT DISTINCT TRIM(category_code) as code, category_name as name FROM dim_item WHERE TRIM(category_code) != '' ORDER BY category_name")

@router.get("/filters/channels")
def get_channels():
    return query("SELECT code, name FROM dim_channel ORDER BY name")

@router.get("/filters/categories")
def get_categories():
    return query("SELECT DISTINCT category_code as code, category_name as name FROM dim_item WHERE category_code IS NOT NULL ORDER BY category_name")

@router.get("/filters/depots")
def get_depots(sales_org: str = None, asm: str = None):
    conditions = ["is_active = true", "depot_code IS NOT NULL", "depot_code != ''"]
    params = []

    if asm:
        asm_codes = [v.strip() for v in asm.split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_codes))
        # Get supervisors under ASM, then users under those supervisors
        sup_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND reports_to IN ({asm_ph})",
            asm_codes
        )
        sup_codes = [r['code'] for r in sup_rows]
        if sup_codes:
            sup_ph = ','.join(['%s'] * len(sup_codes))
            conditions.append(f"reports_to IN ({sup_ph})")
            params.extend(sup_codes)
        else:
            return []

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(
        f"SELECT DISTINCT depot_code as code, depot_code as name FROM dim_user WHERE {where} ORDER BY depot_code",
        params
    )

@router.get("/filters/supervisors")
def get_supervisors(sales_org: str = None, asm: str = None):
    """Supervisors. When asm is given, only show supervisors under that ASM."""
    conditions = ["u.is_active = true", "u.reports_to IS NOT NULL", "u.reports_to != ''"]
    params = []

    if asm:
        asm_codes = [v.strip() for v in asm.split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_codes))
        conditions.append(f"u.reports_to IN ({asm_ph})")
        params.extend(asm_codes)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"u.sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = " AND ".join(conditions)
    return query(
        f"SELECT DISTINCT u2.code, u2.name "
        f"FROM dim_user u JOIN dim_user u2 ON u.reports_to = u2.code "
        f"WHERE {where} ORDER BY u2.name",
        params
    )

@router.get("/filters/asms")
def get_asms(sales_org: str = None):
    """ASMs = users who manage supervisors (2 levels up from salesmen).
    i.e., users whose code appears as reports_to of other users who themselves have subordinates."""
    conditions = []
    params = []

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"u_salesman.sales_org_code IN ({org_ph})")
        params.extend(orgs)

    where = f"AND {' AND '.join(conditions)}" if conditions else ""

    return query(
        f"SELECT DISTINCT u_asm.code, u_asm.name "
        f"FROM dim_user u_salesman "
        f"JOIN dim_user u_sup ON u_salesman.reports_to = u_sup.code "
        f"JOIN dim_user u_asm ON u_sup.reports_to = u_asm.code "
        f"WHERE u_salesman.is_active = true "
        f"AND u_sup.is_active = true "
        f"AND u_asm.is_active = true "
        f"{where} "
        f"ORDER BY u_asm.name",
        params
    )


def _resolve_hierarchy_to_users(depot=None, supervisor=None, asm=None, sales_org=None):
    """Helper: resolve hierarchy filters to a list of user codes. Returns None if no hierarchy filters."""
    if not depot and not supervisor and not asm:
        return None

    conditions = ["is_active = true"]
    params = []

    if asm:
        asm_codes = [v.strip() for v in asm.split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_codes))
        sup_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND reports_to IN ({asm_ph})",
            asm_codes
        )
        sup_codes = [r['code'] for r in sup_rows]
        if supervisor:
            sel_sups = set(v.strip() for v in supervisor.split(',') if v.strip())
            sup_codes = [c for c in sup_codes if c in sel_sups]
        if not sup_codes:
            return []
        sup_ph = ','.join(['%s'] * len(sup_codes))
        conditions.append(f"reports_to IN ({sup_ph})")
        params.extend(sup_codes)
    elif supervisor:
        sups = [v.strip() for v in supervisor.split(',') if v.strip()]
        sup_ph = ','.join(['%s'] * len(sups))
        conditions.append(f"reports_to IN ({sup_ph})")
        params.extend(sups)

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
    rows = query(f"SELECT DISTINCT code FROM dim_user WHERE {where}", params)
    return [r['code'] for r in rows]
