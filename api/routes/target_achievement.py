"""Target vs Achievement report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/target-vs-achievement")
def get_target_vs_achievement(
    year: Optional[int] = None,
    month: Optional[int] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
):
    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month

    # Date range for the selected month
    month_start = date(cur_year, cur_month, 1)
    if cur_month == 12:
        month_end = date(cur_year, 12, 31)
    else:
        month_end = date(cur_year, cur_month + 1, 1) - timedelta(days=1)

    base_filters = {k: v for k, v in {
        'sales_org': sales_org, 'route': route,
    }.items() if v}

    # --- Total target ---
    t_filters = {**base_filters, 'date_from': month_start, 'date_to': month_end}
    tw, tp = build_where(t_filters, date_col='start_date')
    total_target_row = query_one(
        f"SELECT COALESCE(SUM(amount),0) AS target "
        f"FROM rpt_targets WHERE is_active = true AND {tw}", tp
    )
    total_target = float(total_target_row["target"]) if total_target_row else 0

    # --- Total achieved (actual sales) ---
    a_filters = {**base_filters, 'date_from': month_start, 'date_to': month_end}
    aw, ap = build_where(a_filters, date_col='date')
    total_achieved_row = query_one(
        f"SELECT COALESCE(SUM(total_sales),0) AS achieved "
        f"FROM rpt_route_sales_collection WHERE {aw}", ap
    )
    total_achieved = float(total_achieved_row["achieved"]) if total_achieved_row else 0
    achieved_pct = round(total_achieved / total_target * 100, 2) if total_target else 0

    # --- Route-level breakdown ---
    # Targets per route
    rt_filters = {k: v for k, v in {'sales_org': sales_org}.items() if v}
    rt_f = {**rt_filters, 'date_from': month_start, 'date_to': month_end}
    rtw, rtp = build_where(rt_f, date_col='start_date')

    route_targets = query(
        f"SELECT route_code, route_name, COALESCE(SUM(amount),0) AS target "
        f"FROM rpt_targets WHERE is_active = true AND {rtw} "
        f"GROUP BY route_code, route_name", rtp
    )
    target_map = {r["route_code"]: r for r in route_targets}

    # Actual sales per route
    ra_f = {**rt_filters, 'date_from': month_start, 'date_to': month_end}
    raw, rap = build_where(ra_f, date_col='date')

    route_achieved = query(
        f"SELECT route_code, route_name, COALESCE(SUM(total_sales),0) AS achieved "
        f"FROM rpt_route_sales_collection WHERE {raw} "
        f"GROUP BY route_code, route_name", rap
    )
    achieved_map = {r["route_code"]: r for r in route_achieved}

    # Merge
    all_routes = set(list(target_map.keys()) + list(achieved_map.keys()))
    route_data = []
    for rc in sorted(all_routes):
        t_row = target_map.get(rc, {})
        a_row = achieved_map.get(rc, {})
        tgt = float(t_row.get("target", 0))
        ach = float(a_row.get("achieved", 0))
        rname = t_row.get("route_name") or a_row.get("route_name", rc)
        route_data.append({
            "route_code": rc,
            "route_name": rname,
            "target": tgt,
            "achieved": ach,
            "achieved_pct": round(ach / tgt * 100, 2) if tgt else 0,
        })

    # Apply route filter if specified
    if route:
        route_data = [r for r in route_data if r["route_code"] == route]

    # Sort by achieved descending
    route_data.sort(key=lambda r: r["achieved"], reverse=True)

    return {
        "total_target": total_target,
        "total_achieved": total_achieved,
        "achieved_pct": achieved_pct,
        "route_data": route_data,
    }
