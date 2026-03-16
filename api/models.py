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
        _add_multi(conditions, params, f"TRIM({p}category_code)", filters['brand'])
    if filters.get('category'):
        _add_multi(conditions, params, f"{p}category_code", filters['category'])
    if filters.get('item'):
        _add_multi(conditions, params, f"{p}item_code", filters['item'])

    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


def resolve_user_codes(filters: dict) -> Optional[str]:
    """Resolve supervisor/depot/asm filters to user_code list.
    Hierarchy: ASM -> Supervisor -> Salesman.
    Returns comma-separated user codes or None if no hierarchy filter is active.
    """
    from api.database import query
    sub_filters = []
    sub_params = []

    # ASM filter: first resolve ASM -> supervisors, then supervisors -> salesmen
    if filters.get('asm'):
        asm_vals = [v.strip() for v in filters['asm'].split(',') if v.strip()]
        asm_ph = ','.join(['%s'] * len(asm_vals))
        # Get supervisors under these ASMs
        sup_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND reports_to IN ({asm_ph})",
            asm_vals
        )
        sup_codes = [r['code'] for r in sup_rows]

        # If supervisor filter also given, intersect
        if filters.get('supervisor'):
            sel_sups = set(v.strip() for v in filters['supervisor'].split(',') if v.strip())
            sup_codes = [c for c in sup_codes if c in sel_sups]

        if not sup_codes:
            return "__NO_MATCH__"

        sup_ph = ','.join(['%s'] * len(sup_codes))
        sub_filters.append(f"reports_to IN ({sup_ph})")
        sub_params.extend(sup_codes)

    elif filters.get('supervisor'):
        vals = [v.strip() for v in filters['supervisor'].split(',') if v.strip()]
        if len(vals) == 1:
            sub_filters.append("reports_to = %s")
            sub_params.append(vals[0])
        else:
            placeholders = ','.join(['%s'] * len(vals))
            sub_filters.append(f"reports_to IN ({placeholders})")
            sub_params.extend(vals)

    if filters.get('depot'):
        vals = [v.strip() for v in filters['depot'].split(',') if v.strip()]
        if len(vals) == 1:
            sub_filters.append("depot_code = %s")
            sub_params.append(vals[0])
        else:
            placeholders = ','.join(['%s'] * len(vals))
            sub_filters.append(f"depot_code IN ({placeholders})")
            sub_params.extend(vals)

    if not sub_filters:
        return None

    where = " AND ".join(sub_filters)
    rows = query(
        f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND {where}",
        sub_params
    )
    if not rows:
        return "__NO_MATCH__"
    return ",".join(r["code"] for r in rows)
