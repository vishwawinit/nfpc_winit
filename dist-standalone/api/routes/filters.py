"""Filter dropdown data endpoints.

Hierarchy: HOS → ASM → Supervisor → Salesman → Route

Sources:
  - tbl_user        : user master (code, username, isactive)
  - tbl_user_role   : role assignments (usercode, rolecode)
  - tbl_user_details: org membership + hierarchy (usercode, salesorgcode, reportsto, validto)
  - dim_user        : route_code, depot_code (correct for salesmen)
  - dim_route       : route master
"""
from fastapi import APIRouter
from api.database import query
from api.models import _get_all_subordinates

router = APIRouter()

ROLE_HOS        = ('HOS',)
ROLE_NSM        = ('NSM',)
ROLE_ASM        = ('ASM',)
# DP = District Point supervisor, BA = Brand Ambassador — both are senior supervisor level
ROLE_SUPERVISOR = ('C_SALES_SUPERVISOR', 'FreshSup', 'AMBIENTSUP', 'DP', 'BA')
ROLE_SALESMAN   = ('C_PRESALES_VANSALES', 'Vansales')

# Kept for backward-compat import
ROLE_CODES_SUPERVISOR = ROLE_SUPERVISOR


def _split(val, upper=False):
    if not val:
        return []
    parts = [v.strip() for v in val.split(',') if v.strip()]
    return [v.upper() for v in parts] if upper else parts


def _in_clause(col, vals, conditions, params):
    if not vals:
        return
    ph = ','.join(['%s'] * len(vals))
    conditions.append(f"{col} IN ({ph})")
    params.extend(vals)


def _role_ph(roles):
    return ','.join(['%s'] * len(roles))


def _active_detail_cond():
    return "(validto IS NULL OR validto >= CURRENT_DATE)"


def _users_by_roles_and_subs(roles, sub_codes=None, org_codes=None, extra_conditions=None, extra_params=None):
    """
    Core helper: fetch users who have one of the given roles,
    optionally filtered to sub_codes (subordinate list) and org_codes (via tbl_user_details).
    Returns list of {code, name} dicts.
    """
    role_ph = _role_ph(roles)
    conditions = [
        "u.isactive = true",
        f"r.rolecode IN ({role_ph})",
    ]
    params = list(roles)

    if sub_codes:
        if not sub_codes:
            return []
        u_ph = ','.join(['%s'] * len(sub_codes))
        conditions.append(f"UPPER(u.code) IN ({u_ph})")
        params.extend([c.upper() for c in sub_codes])

    if org_codes:
        # salesorgcode in tbl_user_details can be stored in any case — always compare UPPER
        org_ph = ','.join(['%s'] * len(org_codes))
        active = _active_detail_cond()
        conditions.append(
            f"UPPER(u.code) IN ("
            f"  SELECT UPPER(usercode) FROM tbl_user_details"
            f"  WHERE UPPER(salesorgcode) IN ({org_ph}) AND {active}"
            f")"
        )
        params.extend([o.upper() for o in org_codes])

    if extra_conditions:
        conditions.extend(extra_conditions)
        params.extend(extra_params or [])

    where = " AND ".join(conditions)
    return query(
        f"SELECT DISTINCT u.code, u.username AS name"
        f" FROM tbl_user u"
        f" JOIN tbl_user_role r ON UPPER(r.usercode) = UPPER(u.code)"
        f" WHERE {where}"
        f" ORDER BY u.username",
        params
    )


def _get_managers_of(user_codes, roles):
    """Reverse lookup: find direct managers at given roles for the given user codes.
    Walks up one level via tbl_user_details.reportsto — active users only."""
    if not user_codes:
        return []
    ph = ','.join(['%s'] * len(user_codes))
    role_ph = ','.join(['%s'] * len(roles))
    active = _active_detail_cond()
    return query(
        f"SELECT DISTINCT u.code, u.username AS name"
        f" FROM tbl_user_details d"
        f" JOIN tbl_user u ON UPPER(u.code) = UPPER(d.reportsto)"
        f" JOIN tbl_user_role r ON UPPER(r.usercode) = UPPER(u.code)"
        f" WHERE UPPER(d.usercode) IN ({ph})"
        f" AND r.rolecode IN ({role_ph})"
        f" AND u.isactive = true"
        f" AND {active}"
        f" ORDER BY u.username",
        [c.upper() for c in user_codes] + list(roles)
    )


def _resolve_manager_subs(hos=None, asm=None, supervisor=None):
    """
    Resolve hierarchy filters to a list of subordinate user codes.
    Returns None if no hierarchy filter given, [] if nothing matches.
    """
    manager_codes = None

    if supervisor:
        manager_codes = _split(supervisor, upper=True)
    elif asm:
        manager_codes = _split(asm, upper=True)
        if hos:
            hos_codes = _split(hos, upper=True)
            all_under_hos = set(v.upper() for v in _get_all_subordinates(hos_codes))
            manager_codes = [a for a in manager_codes if a in all_under_hos]
    elif hos:
        manager_codes = _split(hos, upper=True)

    if manager_codes is None:
        return None

    if not manager_codes:
        return []

    return _get_all_subordinates(manager_codes)


# ── Sales Orgs ────────────────────────────────────────────────────────────────

@router.get("/filters/sales-orgs")
def get_sales_orgs(
    hos: str = None, asm: str = None,
    depot: str = None, supervisor: str = None, user_code: str = None, gcd: str = None,
):
    """Return sales orgs filtered to what the logged-in user actually manages.
    Uses tbl_user_details.salesorgcode as the authoritative org membership source.
    Interceptor automatically passes the locked filter (hos/asm/supervisor/user_code)
    so each role sees only their own orgs.
    """
    active = _active_detail_cond()

    user_codes = None

    # Most-specific filter wins — bottom-up: user_code > supervisor > depot > asm > hos
    # This ensures that selecting a lower-level filter narrows the org options correctly
    # even when a higher-level filter is locked (e.g. HOS locked but supervisor selected)
    if user_code:
        # Use dim_user.sales_org_code — salesman's primary working org
        # tbl_user_details may register them in multiple orgs; dim_user has the correct single org
        codes = _split(user_code, upper=True)
        ph = ','.join(['%s'] * len(codes))
        return query(
            f"SELECT DISTINCT du.sales_org_code AS code, COALESCE(so.name, du.sales_org_code) AS name"
            f" FROM dim_user du"
            f" LEFT JOIN dim_sales_org so ON so.code = du.sales_org_code"
            f" WHERE UPPER(du.code) IN ({ph})"
            f" AND du.is_active = true AND du.sales_org_code IS NOT NULL"
            f" ORDER BY name",
            codes
        )
    elif supervisor:
        user_codes = _split(supervisor, upper=True)
    elif depot:
        user_codes = _split(depot, upper=True)
    elif asm:
        # ASM may span multiple orgs — use subordinates' orgs for accuracy
        asm_codes = _split(asm, upper=True)
        sub_codes = _get_all_subordinates(asm_codes)
        user_codes = sub_codes if sub_codes else asm_codes
    elif hos:
        # HOS is registered in ALL orgs — use subordinates' orgs instead
        hos_codes = _split(hos, upper=True)
        sub_codes = _get_all_subordinates(hos_codes)
        user_codes = sub_codes if sub_codes else hos_codes
    elif gcd:
        # GCD/above-HOS — use subordinates' orgs (same logic as HOS)
        gcd_codes = _split(gcd, upper=True)
        sub_codes = _get_all_subordinates(gcd_codes)
        user_codes = sub_codes if sub_codes else gcd_codes

    if user_codes:
        ph = ','.join(['%s'] * len(user_codes))
        return query(
            f"SELECT DISTINCT UPPER(d.salesorgcode) AS code, COALESCE(so.name, d.salesorgcode) AS name"
            f" FROM tbl_user_details d"
            f" LEFT JOIN dim_sales_org so ON UPPER(so.code) = UPPER(d.salesorgcode)"
            f" WHERE UPPER(d.usercode) IN ({ph}) AND {active}"
            f" ORDER BY name",
            user_codes
        )

    return query("SELECT code, name FROM dim_sales_org WHERE is_active = true ORDER BY name")


# ── HOS ──────────────────────────────────────────────────────────────────────

@router.get("/filters/hos")
def get_hos(sales_org: str = None, asm: str = None, depot: str = None, supervisor: str = None, user_code: str = None, gcd: str = None):
    """HOS users. Supports both directions:
    - Top-down: sales_org filters HOS by org membership
    - Bottom-up: asm/depot/supervisor/user_code narrows HOS to who manages them"""
    if asm or depot or supervisor or user_code:
        # Reverse lookup — walk up to HOS level
        if asm or depot:
            codes = _split(asm or depot, upper=True)
        elif supervisor:
            # supervisor is 2 levels below HOS: supervisor → ASM → HOS
            sup_codes = _split(supervisor, upper=True)
            mid = [r['code'] for r in _get_managers_of(sup_codes, ROLE_ASM + ROLE_NSM)]
            codes = mid if mid else sup_codes
        else:
            # user_code is 3 levels below HOS: user → supervisor → ASM → HOS
            lower = _split(user_code, upper=True)
            sup = [r['code'] for r in _get_managers_of(lower, ROLE_SUPERVISOR)]
            if sup:
                mid = [r['code'] for r in _get_managers_of(sup, ROLE_ASM + ROLE_NSM)]
                codes = mid if mid else sup
            else:
                # user may report directly to ASM (no supervisor)
                mid = [r['code'] for r in _get_managers_of(lower, ROLE_ASM + ROLE_NSM)]
                codes = mid if mid else lower
        return _get_managers_of(codes, ROLE_HOS)

    sub_codes = None
    if gcd:
        sub_codes = _get_all_subordinates(_split(gcd, upper=True))
        if not sub_codes:
            return []

    return _users_by_roles_and_subs(
        roles=ROLE_HOS,
        sub_codes=sub_codes,
        org_codes=_split(sales_org) if sales_org else None,
    )


# ── ASM ──────────────────────────────────────────────────────────────────────

@router.get("/filters/asms")
def get_asms(sales_org: str = None, hos: str = None, supervisor: str = None, user_code: str = None, gcd: str = None):
    """ASM users. Supports both directions:
    - Top-down: hos filters ASMs under that HOS
    - Bottom-up: supervisor/user_code narrows ASMs to who manages them"""
    if supervisor or user_code:
        # Reverse lookup — bottom-up wins regardless of locked hos context
        lower = _split(supervisor or user_code, upper=True)
        if user_code and not supervisor:
            # user is 2 levels below ASM — find supervisor first
            sup = [r['code'] for r in _get_managers_of(lower, ROLE_SUPERVISOR)]
            lower = sup if sup else lower
        return _get_managers_of(lower, ROLE_ASM)

    sub_codes = None
    if hos:
        sub_codes = _get_all_subordinates(_split(hos, upper=True))
    elif gcd:
        sub_codes = _get_all_subordinates(_split(gcd, upper=True))

    if sub_codes is not None and not sub_codes:
        return []

    return _users_by_roles_and_subs(
        roles=ROLE_ASM,
        sub_codes=sub_codes,
        org_codes=_split(sales_org) if sales_org else None,
    )


# ── Depots ────────────────────────────────────────────────────────────────────

@router.get("/filters/depots")
def get_depots(sales_org: str = None, asm: str = None, hos: str = None, supervisor: str = None, user_code: str = None, gcd: str = None):
    """Return NSM users (real users with NSM role). Supports both directions:
    - Top-down: hos/asm filters NSMs under that hierarchy
    - Bottom-up: supervisor/user_code narrows NSMs to who manages them"""
    if (supervisor or user_code) and not (hos or asm):
        # Reverse lookup — bottom-up wins regardless of locked context
        lower = _split(supervisor or user_code, upper=True)
        if user_code and not supervisor:
            sup = [r['code'] for r in _get_managers_of(lower, ROLE_SUPERVISOR)]
            lower = sup if sup else lower
        return _get_managers_of(lower, ROLE_NSM)

    sub_codes = None
    if hos or asm:
        sub_codes = _resolve_manager_subs(hos=hos, asm=asm)
    elif gcd:
        sub_codes = _get_all_subordinates(_split(gcd, upper=True))

    if sub_codes is not None and not sub_codes:
        return []

    return _users_by_roles_and_subs(
        roles=ROLE_NSM,
        sub_codes=sub_codes,
        org_codes=_split(sales_org) if sales_org else None,
    )


# ── Supervisors ───────────────────────────────────────────────────────────────

@router.get("/filters/supervisors")
def get_supervisors(sales_org: str = None, asm: str = None, hos: str = None, depot: str = None, user_code: str = None, gcd: str = None):
    """Supervisor users. Supports both directions:
    - Top-down: hos/asm/depot filters supervisors under that hierarchy
    - Bottom-up: user_code narrows supervisors to who directly manages that user"""
    if user_code:
        # Reverse lookup — bottom-up wins regardless of locked hos/asm/depot context
        return _get_managers_of(_split(user_code, upper=True), ROLE_SUPERVISOR)

    sub_codes = None

    if depot:
        # NSM selected — get all subs of that NSM, then optionally intersect with HOS/ASM subs
        nsm_subs = set(_get_all_subordinates(_split(depot, upper=True)))
        if hos or asm:
            hier_subs = set(_resolve_manager_subs(hos=hos, asm=asm) or [])
            sub_codes = list(nsm_subs & hier_subs)
        else:
            sub_codes = list(nsm_subs)
        if not sub_codes:
            return []
    elif hos or asm:
        sub_codes = _resolve_manager_subs(hos=hos, asm=asm)
    elif gcd:
        sub_codes = _get_all_subordinates(_split(gcd, upper=True))

    if sub_codes is not None and not sub_codes:
        return []

    return _users_by_roles_and_subs(
        roles=ROLE_SUPERVISOR,
        sub_codes=sub_codes,
        org_codes=_split(sales_org) if sales_org else None,
    )


# ── Salesmen ─────────────────────────────────────────────────────────────────

@router.get("/filters/users")
def get_users(
    sales_org: str = None,
    supervisor: str = None,
    depot: str = None,
    asm: str = None,
    hos: str = None,
    user_code: str = None,
    gcd: str = None,
):
    """Salesman users, optionally filtered by hierarchy (HOS/ASM/NSM/Supervisor) and/or sales org.
    depot = NSM user code — only salesmen under that NSM.
    user_code = locked filter for salesman/standalone DP — returns just that user."""
    # Salesman or standalone DP locked to their own code — return just themselves
    if user_code and not (supervisor or depot or asm or hos):
        codes = _split(user_code, upper=True)
        ph = ','.join(['%s'] * len(codes))
        return query(
            f"SELECT DISTINCT u.code, u.username AS name"
            f" FROM tbl_user u"
            f" WHERE UPPER(u.code) IN ({ph}) AND u.isactive = true"
            f" ORDER BY u.username",
            codes
        )

    sub_codes = None

    if depot:
        # NSM selected — resolve NSM subordinates, then intersect with other hierarchy filters
        nsm_subs = set(_get_all_subordinates(_split(depot, upper=True)))
        if supervisor or asm or hos:
            hier_subs = set(_resolve_manager_subs(hos=hos, asm=asm, supervisor=supervisor) or [])
            sub_codes = list(nsm_subs & hier_subs)
        else:
            sub_codes = list(nsm_subs)
        if not sub_codes:
            return []
    elif supervisor or asm or hos:
        sub_codes = _resolve_manager_subs(hos=hos, asm=asm, supervisor=supervisor)
    elif gcd:
        sub_codes = _get_all_subordinates(_split(gcd, upper=True))

    if sub_codes is not None and not sub_codes:
        return []

    return _users_by_roles_and_subs(
        roles=ROLE_SALESMAN,
        sub_codes=sub_codes,
        org_codes=_split(sales_org) if sales_org else None,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/filters/routes")
def get_routes(
    sales_org: str = None,
    depot: str = None,
    supervisor: str = None,
    asm: str = None,
    hos: str = None,
    user_code: str = None,
):
    """Routes for the given hierarchy. Uses dim_user.route_code (correct for salesmen)."""

    # Specific user(s) — most precise
    if user_code:
        user_codes = _split(user_code, upper=True)
        u_ph = ','.join(['%s'] * len(user_codes))
        route_codes = set()
        rows = query(
            f"SELECT DISTINCT route_code FROM dim_user"
            f" WHERE UPPER(code) IN ({u_ph}) AND route_code IS NOT NULL",
            user_codes
        )
        route_codes |= {r['route_code'] for r in rows}
        txn = query(
            f"SELECT DISTINCT route_code FROM rpt_customer_visits"
            f" WHERE UPPER(user_code) IN ({u_ph})",
            user_codes
        )
        route_codes |= {r['route_code'] for r in txn if r['route_code']}
        return _fetch_routes(list(route_codes)) if route_codes else []

    # Hierarchy filter — depot = NSM user code, resolve its subordinates
    hier_subs = _resolve_manager_subs(hos=hos, asm=asm, supervisor=supervisor)

    all_subs = hier_subs
    if depot:
        nsm_subs = set(_get_all_subordinates(_split(depot, upper=True)))
        if hier_subs is not None:
            all_subs = list(nsm_subs & set(hier_subs))
        else:
            all_subs = list(nsm_subs)

    if all_subs is not None or sales_org:
        user_conditions = ["is_active = true"]
        user_params = []

        if all_subs is not None:
            if not all_subs:
                return []
            u_ph = ','.join(['%s'] * len(all_subs))
            user_conditions.append(f"UPPER(code) IN ({u_ph})")
            user_params.extend([c.upper() for c in all_subs])

        if sales_org:
            _in_clause("sales_org_code", _split(sales_org), user_conditions, user_params)

        user_where = " AND ".join(user_conditions)
        user_rows = query(
            f"SELECT DISTINCT route_code FROM dim_user"
            f" WHERE {user_where} AND route_code IS NOT NULL",
            user_params
        )
        route_codes = {r['route_code'] for r in user_rows}

        if all_subs:
            u_ph2 = ','.join(['%s'] * len(all_subs))
            txn_rows = query(
                f"SELECT DISTINCT route_code FROM rpt_customer_visits"
                f" WHERE UPPER(user_code) IN ({u_ph2})",
                [c.upper() for c in all_subs]
            )
            route_codes |= {r['route_code'] for r in txn_rows if r['route_code']}

        return _fetch_routes(list(route_codes)) if route_codes else []

    if sales_org:
        orgs = _split(sales_org)
        org_ph = ','.join(['%s'] * len(orgs))
        return query(
            f"SELECT code, name FROM dim_route"
            f" WHERE is_active = true AND sales_org_code IN ({org_ph}) ORDER BY name",
            orgs
        )

    return query("SELECT code, name FROM dim_route WHERE is_active = true ORDER BY name")


def _fetch_routes(route_codes):
    ph = ','.join(['%s'] * len(route_codes))
    result = query(
        f"SELECT code, name FROM dim_route WHERE is_active = true AND code IN ({ph}) ORDER BY name",
        route_codes
    )
    found = {r['code'] for r in result}
    for rc in route_codes:
        if rc not in found:
            result.append({'code': rc, 'name': rc})
    result.sort(key=lambda x: x['name'] or x['code'])
    return result


# ── Other lookups ─────────────────────────────────────────────────────────────

@router.get("/filters/customers")
def get_customers(sales_org: str = None):
    if sales_org:
        orgs = _split(sales_org)
        org_ph = ','.join(['%s'] * len(orgs))
        return query(
            f"SELECT code, name FROM dim_customer"
            f" WHERE is_active = true AND sales_org_code IN ({org_ph}) ORDER BY name",
            orgs
        )
    return query("SELECT DISTINCT code, name FROM dim_customer WHERE is_active = true ORDER BY name")


@router.get("/filters/order-customers")
def get_order_customers():
    return query(
        "SELECT DISTINCT ON (code) code, TRIM(name) AS name, sales_org_code AS sales_org"
        " FROM dim_customer WHERE is_active = true AND name IS NOT NULL ORDER BY code"
    )


@router.get("/filters/items")
def get_items(brand: str = None, category: str = None, sales_org: str = None):
    conditions = ["is_active = true"]
    params = []
    if brand:
        _in_clause("TRIM(brand_code)", _split(brand), conditions, params)
    if category:
        _in_clause("category_code", _split(category), conditions, params)
    if sales_org:
        _in_clause("sales_org_code", _split(sales_org), conditions, params)
    where = " AND ".join(conditions)
    return query(f"SELECT code, name FROM dim_item WHERE {where} ORDER BY name", params)


@router.get("/filters/brands")
def get_brands():
    return query(
        "SELECT DISTINCT TRIM(brand_code) as code, brand_name as name"
        " FROM dim_item WHERE brand_code IS NOT NULL AND TRIM(brand_code) != '' ORDER BY brand_name"
    )


@router.get("/filters/channels")
def get_channels():
    return query("SELECT code, name FROM dim_channel ORDER BY name")


@router.get("/filters/categories")
def get_categories():
    return query(
        "SELECT DISTINCT category_code as code, category_name as name"
        " FROM dim_item WHERE category_code IS NOT NULL ORDER BY category_name"
    )


@router.get("/filters/route-categories")
def get_route_categories():
    return query(
        "SELECT DISTINCT route_type AS code, route_type AS name"
        " FROM dim_route WHERE route_type IS NOT NULL AND TRIM(route_type) != '' ORDER BY route_type"
    )


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
    return query(
        f"SELECT code, name, route_type, sales_org_code FROM dim_route WHERE {where} ORDER BY name",
        params
    )


@router.get("/filters/cities")
def get_cities():
    return query("SELECT code, name, region_code FROM dim_city ORDER BY name")


@router.get("/filters/regions")
def get_regions():
    return query("SELECT code, name FROM dim_region ORDER BY name")
