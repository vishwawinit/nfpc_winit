"""Shared filter parameter models and hierarchy resolution."""
from datetime import date
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

    Uses TWO sources merged via UNION to handle broken / missing chains:
      1. tbl_user_details.reportsto  — authoritative multi-org source
      2. dim_user.reports_to         — ETL-computed fallback (catches users whose
                                       tbl_user_details chain is broken, e.g. UARAMU02)

    Excludes self-referencing rows to prevent infinite loops.
    Case-insensitive matching (reportsto is lowercase, codes are uppercase).

    Returns list of user codes (all depths, active and intermediate).
    """
    from api.database import query
    codes = [c.strip() for c in manager_codes if c.strip()]
    if not codes:
        return []

    ph = ','.join(['%s'] * len(codes))
    upper_codes = [c.upper() for c in codes]

    # PostgreSQL RECURSIVE CTE must have exactly one non-recursive base and one recursive term.
    # We combine both sources (tbl_user_details + dim_user) in each half using subqueries.
    # JOIN tbl_user to filter isactive=true — inactive managers are excluded from traversal
    # so their subtrees don't bleed into unrelated orgs.
    rows = query(
        f"WITH RECURSIVE subs(code) AS ("
        # ── Non-recursive base: seed from both sources ──────────────────
        f"  SELECT DISTINCT code FROM ("
        f"    SELECT td.usercode AS code"
        f"    FROM tbl_user_details td"
        f"    JOIN tbl_user tu ON UPPER(tu.code) = UPPER(td.usercode)"
        f"    WHERE UPPER(td.reportsto) IN ({ph})"
        f"    AND UPPER(td.reportsto) != UPPER(td.usercode)"
        f"    AND (td.validto IS NULL OR td.validto >= CURRENT_DATE)"
        f"    AND tu.isactive = true"
        f"    UNION"
        f"    SELECT code"
        f"    FROM dim_user"
        f"    WHERE UPPER(reports_to) IN ({ph})"
        f"    AND is_active = true"
        f"  ) _seed"
        f"  UNION"
        # ── Recursive term: expand via both sources ──────────────────────
        f"  SELECT DISTINCT _nxt.code FROM subs"
        f"  JOIN LATERAL ("
        f"    SELECT td2.usercode AS code"
        f"    FROM tbl_user_details td2"
        f"    JOIN tbl_user tu2 ON UPPER(tu2.code) = UPPER(td2.usercode)"
        f"    WHERE UPPER(td2.reportsto) = UPPER(subs.code)"
        f"    AND UPPER(td2.reportsto) != UPPER(td2.usercode)"
        f"    AND (td2.validto IS NULL OR td2.validto >= CURRENT_DATE)"
        f"    AND tu2.isactive = true"
        f"    UNION"
        f"    SELECT code"
        f"    FROM dim_user"
        f"    WHERE UPPER(reports_to) = UPPER(subs.code)"
        f"    AND is_active = true"
        f"  ) _nxt ON true"
        f") SELECT DISTINCT code FROM subs",
        upper_codes + upper_codes  # used in seed base
    )
    return [r['code'] for r in rows]


def resolve_user_codes(filters: dict) -> Optional[str]:
    """Resolve hos/supervisor/depot/asm filters to a user_code list.

    Hierarchy: HOS → ASM → Supervisor → Salesman
    Uses tbl_user_details for hierarchy traversal (reportsto chain).
    Uses dim_user for depot_code filtering (salesmen have correct depot in dim_user).

    Returns comma-separated user codes, '__NO_MATCH__' if nothing matches,
    or None if no hierarchy filter is active.
    """
    from api.database import query

    if not any(filters.get(k) for k in ('hos', 'asm', 'supervisor', 'depot')):
        return None

    manager_codes = None

    # Build the starting manager set from deepest specified level
    if filters.get('hos'):
        hos_vals = [v.strip().upper() for v in filters['hos'].split(',') if v.strip()]
        if filters.get('asm'):
            # Both HOS and ASM specified — validate ASM is under HOS, use ASM as root
            asm_vals = [v.strip().upper() for v in filters['asm'].split(',') if v.strip()]
            all_under_hos = set(v.upper() for v in _get_all_subordinates(hos_vals))
            valid_asms = [a for a in asm_vals if a in all_under_hos]
            if not valid_asms:
                return "__NO_MATCH__"
            manager_codes = valid_asms
        else:
            manager_codes = hos_vals
    elif filters.get('asm'):
        manager_codes = [v.strip().upper() for v in filters['asm'].split(',') if v.strip()]

    if filters.get('supervisor'):
        sup_vals = [v.strip().upper() for v in filters['supervisor'].split(',') if v.strip()]
        if manager_codes:
            # Validate supervisors are under the current manager set
            all_under = set(v.upper() for v in _get_all_subordinates(manager_codes))
            valid_sups = [s for s in sup_vals if s in all_under]
            if not valid_sups:
                return "__NO_MATCH__"
            manager_codes = valid_sups
        else:
            manager_codes = sup_vals

    # Get all recursive subordinates under the resolved manager set
    if manager_codes:
        all_users = _get_all_subordinates(manager_codes)
        if not all_users:
            return "__NO_MATCH__"
    else:
        all_users = None

    # depot = NSM user code — get all subordinates of those NSM users
    if filters.get('depot'):
        nsm_codes = [v.strip().upper() for v in filters['depot'].split(',') if v.strip()]
        nsm_subs = _get_all_subordinates(nsm_codes)
        if all_users is not None:
            all_upper = {u.upper() for u in all_users}
            all_users = [u for u in nsm_subs if u.upper() in all_upper]
        else:
            all_users = nsm_subs
        if not all_users:
            return "__NO_MATCH__"

    if all_users is None:
        return None
    if not all_users:
        return "__NO_MATCH__"
    return ",".join(all_users)
