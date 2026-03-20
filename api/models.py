"""Shared filter parameter models."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel

class DateRangeFilter(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None

class StandardFilters(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    sales_org: Optional[str] = None
    route: Optional[str] = None
    user_code: Optional[str] = None
    channel: Optional[str] = None
    customer: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    item: Optional[str] = None


def _add_multi(conditions, params, col, value):
    """Handle single or comma-separated multi-value filter."""
    vals = [v.strip() for v in value.split(',') if v.strip()]
    if len(vals) == 1:
        conditions.append(f"{col} = %s")
        params.append(vals[0])
    elif vals:
        placeholders = ','.join(['%s'] * len(vals))
        conditions.append(f"{col} IN ({placeholders})")
        params.extend(vals)


def build_where(filters: dict, date_col: str = "date", prefix: str = "") -> tuple:
    """Build WHERE clause and params from filters dict.
    Supports comma-separated values for multi-select filters.
    Returns (where_clause, params_list).
    """
    conditions = []
    params = []
    p = f"{prefix}." if prefix else ""

    if filters.get('date_from'):
        conditions.append(f"{p}{date_col} >= %s")
        params.append(filters['date_from'])
    if filters.get('date_to'):
        conditions.append(f"{p}{date_col} <= %s")
        params.append(filters['date_to'])
    if filters.get('sales_org'):
        _add_multi(conditions, params, f"{p}sales_org_code", filters['sales_org'])
    if filters.get('route'):
        _add_multi(conditions, params, f"{p}route_code", filters['route'])
    if filters.get('user_code'):
        _add_multi(conditions, params, f"{p}user_code", filters['user_code'])
    if filters.get('channel'):
        _add_multi(conditions, params, f"{p}channel_code", filters['channel'])
    if filters.get('customer'):
        _add_multi(conditions, params, f"{p}customer_code", filters['customer'])
    if filters.get('brand'):
        _add_multi(conditions, params, f"TRIM({p}brand_code)", filters['brand'])
    if filters.get('category'):
        _add_multi(conditions, params, f"{p}category_code", filters['category'])
    if filters.get('item'):
        _add_multi(conditions, params, f"{p}item_code", filters['item'])

    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


def _get_all_subordinates(manager_codes: list) -> list:
    """Recursively get ALL subordinates under given manager codes (any depth).
    Returns list of user codes (includes direct and indirect reports)."""
    from api.database import query
    all_codes = set()
    current_level = set(c.strip().upper() for c in manager_codes if c.strip())

    # Walk down the hierarchy up to 5 levels deep (HOS->ASM->Sup->Salesman + safety)
    for _ in range(5):
        if not current_level:
            break
        ph = ','.join(['%s'] * len(current_level))
        rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND reports_to IN ({ph})",
            list(current_level)
        )
        next_level = set(r['code'] for r in rows) - all_codes
        all_codes |= next_level
        current_level = next_level

    return list(all_codes)


def resolve_user_codes(filters: dict) -> Optional[str]:
    """Resolve hos/supervisor/depot/asm filters to user_code list.
    Uses recursive subordinate resolution to get ALL users under a manager,
    regardless of role_code. This ensures salesmen reporting directly to ASMs
    (skipping supervisors) are included.
    Returns comma-separated user codes or None if no hierarchy filter is active.
    """
    from api.database import query
    from api.routes.filters import ROLE_CODES_SUPERVISOR

    if not any(filters.get(k) for k in ('hos', 'asm', 'supervisor', 'depot')):
        return None

    # Step 1: Determine the starting manager codes
    manager_codes = None

    if filters.get('hos'):
        hos_vals = [v.strip().upper() for v in filters['hos'].split(',') if v.strip()]
        if filters.get('asm'):
            manager_codes = [v.strip().upper() for v in filters['asm'].split(',') if v.strip()]
        else:
            manager_codes = hos_vals
    elif filters.get('asm'):
        manager_codes = [v.strip().upper() for v in filters['asm'].split(',') if v.strip()]

    if filters.get('supervisor'):
        sup_vals = [v.strip().upper() for v in filters['supervisor'].split(',') if v.strip()]
        if manager_codes:
            # ASM/HOS + Supervisor: get all subordinates under the ASM/HOS,
            # then intersect supervisors, then get subordinates of those supervisors
            all_under_manager = _get_all_subordinates(manager_codes)
            # Keep only the selected supervisors that are actually under the manager
            valid_sups = [s for s in sup_vals if s in all_under_manager]
            if not valid_sups:
                return "__NO_MATCH__"
            manager_codes = valid_sups
        else:
            # Supervisor only
            manager_codes = sup_vals

    # Step 2: Get all subordinates recursively
    if manager_codes:
        all_users = _get_all_subordinates(manager_codes)
        if not all_users:
            return "__NO_MATCH__"
    else:
        all_users = None

    # Step 3: Apply depot filter
    if filters.get('depot'):
        vals = [v.strip() for v in filters['depot'].split(',') if v.strip()]
        dep_ph = ','.join(['%s'] * len(vals))
        depot_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND depot_code IN ({dep_ph})",
            vals
        )
        depot_users = set(r['code'] for r in depot_rows)
        if all_users is not None:
            all_users = [u for u in all_users if u in depot_users]
        else:
            all_users = list(depot_users)
        if not all_users:
            return "__NO_MATCH__"

    if all_users is None:
        return None
    if not all_users:
        return "__NO_MATCH__"
    return ",".join(all_users)
