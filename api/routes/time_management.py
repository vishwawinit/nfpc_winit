"""Time Management report endpoint.
Matches: sp_TimeManagementReport_Search

Sources:
  - Journey times: rpt_journeys (start_time, end_time)
  - Visit times: rpt_customer_visits (first checkin, last checkout, productive time)
  - Sales: rpt_route_sales_by_item_customer (for productive detection)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()


@router.get("/time-management")
def get_time_management(
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return []
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'user_code': user_code, 'route': route,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    jw, jp = build_where(filters, date_col='date', prefix='j')

    rows = query(
        f"SELECT j.date, j.user_code, j.user_name, "
        f"  j.route_code, j.route_name, j.sales_org_code, "
        f"  j.start_time, j.end_time, j.vehicle_code, "
        f"  cv.first_checkin, cv.last_checkout, "
        f"  cv.total_visits, cv.productive_time_mins, "
        f"  CASE WHEN j.start_time IS NOT NULL AND j.end_time IS NOT NULL "
        f"    THEN ROUND(EXTRACT(EPOCH FROM (j.end_time::timestamp - j.start_time::timestamp)) / 3600.0, 2) "
        f"    ELSE 0 END AS total_working_hours "
        f"FROM rpt_journeys j "
        f"LEFT JOIN ( "
        f"  SELECT user_code, date, "
        f"    MIN(arrival_time) AS first_checkin, "
        f"    MAX(out_time) AS last_checkout, "
        f"    COUNT(*) AS total_visits, "
        f"    COALESCE(SUM(total_time_mins), 0) AS productive_time_mins "
        f"  FROM rpt_customer_visits GROUP BY user_code, date "
        f") cv ON j.user_code = cv.user_code AND j.date = cv.date "
        f"WHERE {jw} "
        f"ORDER BY j.date DESC, j.user_name",
        jp
    )

    result = []
    for r in rows:
        wh = float(r["total_working_hours"]) if r["total_working_hours"] else 0
        pt = float(r["productive_time_mins"]) / 60.0 if r["productive_time_mins"] else 0
        result.append({
            "date": str(r["date"]) if r["date"] else None,
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "route_code": r["route_code"],
            "route_name": r["route_name"],
            "sales_org": r["sales_org_code"],
            "vehicle": r["vehicle_code"],
            "journey_start": str(r["start_time"])[11:16] if r["start_time"] else None,
            "journey_end": str(r["end_time"])[11:16] if r["end_time"] else None,
            "first_checkin": str(r["first_checkin"])[11:16] if r["first_checkin"] else None,
            "last_checkout": str(r["last_checkout"])[11:16] if r["last_checkout"] else None,
            "total_visits": int(r["total_visits"]) if r["total_visits"] else 0,
            "total_working_hours": round(max(0, wh), 2),
            "productive_time": round(pt, 2),
            "idle_time": round(max(0, wh - pt), 2),
        })

    return result
