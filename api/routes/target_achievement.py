"""Target vs Achievement report endpoint.
Matches: SP_tblCommonTarget_SELECT_TARGET_FOR_DASHBOARD_ByItem

Sources:
  - rpt_route_sales_summary_by_item (has TotalSales + TargetAmount per route)
  - rpt_route_sales_by_item_customer (for actual sales when summary unavailable)
  - rpt_targets (fallback for targets)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSSI_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/target-vs-achievement")
def get_target_vs_achievement(
    year: Optional[int] = None,
    month: Optional[int] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            user_code = "__NO_MATCH__"
        elif resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month

    month_start = date(cur_year, cur_month, 1)
    month_end = date(cur_year, 12, 31) if cur_month == 12 else date(cur_year, cur_month + 1, 1) - timedelta(days=1)

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
    }.items() if v}

    # Resolve sales_org
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs)
        if not org_rows:
            return _empty()
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            intersected = set(base_filters['user_code'].split(',')) & org_users
            if not intersected:
                return _empty()
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

    # Item filter
    item_cond = ""
    item_params = []
    if brand or category:
        i_conds, i_params = [], []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            i_conds.append(f"TRIM(brand_code) IN ({','.join(['%s']*len(b_vals))})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            i_conds.append(f"category_code IN ({','.join(['%s']*len(c_vals))})")
            i_params.extend(c_vals)
        i_rows = query(f"SELECT DISTINCT code FROM dim_item WHERE {' AND '.join(i_conds)}", i_params)
        if not i_rows:
            return _empty()
        codes = [r['code'] for r in i_rows]
        item_cond = f" AND r.item_code IN ({','.join(['%s']*len(codes))})"
        item_params = codes

    filters = {**base_filters, 'date_from': month_start, 'date_to': month_end}

    # Route-level: Sales + Target from rpt_route_sales_by_item_customer
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    route_rows = query(
        f"SELECT r.route_code, COALESCE(dr.name, r.route_code) AS route_name, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS achieved "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_route dr ON r.route_code = dr.code "
        f"WHERE {rw}{item_cond} "
        f"GROUP BY r.route_code, COALESCE(dr.name, r.route_code) "
        f"ORDER BY achieved DESC",
        rp + item_params
    )

    # Targets from rpt_route_sales_summary_by_item (has TargetAmount per route)
    f_rssi = {k: v for k, v in filters.items() if k in RSSI_KEYS}
    tw, tp = build_where(f_rssi, date_col='date')
    target_rows = query(
        f"SELECT route_code, ROUND(COALESCE(SUM(target_amount), 0)::numeric, 2) AS target "
        f"FROM rpt_route_sales_summary_by_item WHERE {tw} "
        f"GROUP BY route_code",
        tp
    )
    target_map = {r["route_code"]: float(r["target"]) for r in target_rows}

    # Build route data
    total_target = 0
    total_achieved = 0
    route_data = []
    for row in route_rows:
        ach = float(row["achieved"])
        tgt = target_map.get(row["route_code"], 0)
        total_achieved += ach
        total_target += tgt
        route_data.append({
            "route_code": row["route_code"],
            "route_name": row["route_name"],
            "target": tgt,
            "achieved": ach,
            "achieved_pct": min(100.0, round(ach / tgt * 100, 2)) if tgt else 0,
        })

    # Add routes with target but no sales
    for rc, tgt in target_map.items():
        if not any(r["route_code"] == rc for r in route_data) and tgt > 0:
            total_target += tgt
            route_data.append({
                "route_code": rc,
                "route_name": rc,
                "target": tgt,
                "achieved": 0,
                "achieved_pct": 0,
            })

    route_data.sort(key=lambda r: r["achieved"], reverse=True)
    achieved_pct = min(100.0, round(total_achieved / total_target * 100, 2)) if total_target else 0

    return {
        "total_target": round(total_target, 2),
        "total_achieved": round(total_achieved, 2),
        "achieved_pct": achieved_pct,
        "route_data": route_data,
    }


def _empty():
    return {"total_target": 0, "total_achieved": 0, "achieved_pct": 0, "route_data": []}
