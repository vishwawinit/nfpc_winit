"""Endorsement Report endpoint — optimized single-query approach."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/endorsement")
def get_endorsement(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    channel: Optional[str] = None,
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
            return {"header": {}, "customers": []}
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'route': route, 'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org, 'user_code': user_code,
    }.items() if v is not None}

    vw, vp = build_where(filters, date_col='date', prefix='cv')

    # Single optimized query: visits + planned + sales in one go
    customers = query(
        f"SELECT cv.customer_code, cv.customer_name, cv.channel_name, "
        f"  cv.route_code, cv.user_code, cv.user_name, cv.date, "
        f"  cv.arrival_time, cv.out_time, cv.total_time_mins, "
        f"  cv.latitude, cv.longitude, "
        f"  CASE WHEN jp.customer_code IS NOT NULL THEN true ELSE false END AS is_planned, "
        f"  COALESCE(s.total_value, 0) AS total_value, "
        f"  COALESCE(s.total_returns, 0) AS total_returns "
        f"FROM rpt_customer_visits cv "
        f"LEFT JOIN rpt_journey_plan jp "
        f"  ON cv.route_code = jp.route_code AND cv.customer_code = jp.customer_code AND cv.date = jp.date "
        f"LEFT JOIN ( "
        f"  SELECT route_code, customer_code, date, "
        f"    ROUND(SUM(total_sales)::numeric, 2) AS total_value, "
        f"    ROUND(SUM(total_gr_sales + total_damage_sales + total_expiry_sales)::numeric, 2) AS total_returns "
        f"  FROM rpt_route_sales_by_item_customer "
        f"  GROUP BY route_code, customer_code, date "
        f") s ON cv.route_code = s.route_code AND cv.customer_code = s.customer_code AND cv.date = s.date "
        f"WHERE {vw} "
        f"ORDER BY cv.arrival_time",
        vp
    )

    # Build response + track seen customers for dedup
    customer_list = []
    seen = set()
    planned_count = 0
    productive_count = 0
    total_visits = 0

    for c in customers:
        is_planned = c["is_planned"]
        is_productive = float(c["total_value"]) > 0
        cust_key = (c["customer_code"], str(c["date"]))
        first_visit = cust_key not in seen
        seen.add(cust_key)

        total_visits += 1
        if is_planned:
            planned_count += 1
        if is_productive:
            productive_count += 1

        customer_list.append({
            "customer_code": c["customer_code"],
            "customer_name": c["customer_name"],
            "channel_name": c["channel_name"],
            "is_planned": is_planned,
            "visit_type": "JP" if is_planned else "UJP",
            "arrival_time": str(c["arrival_time"])[11:16] if c["arrival_time"] else None,
            "out_time": str(c["out_time"])[11:16] if c["out_time"] else None,
            "time_spent_mins": float(c["total_time_mins"]) if c["total_time_mins"] else 0,
            "is_productive": is_productive,
            "total_value": float(c["total_value"]) if first_visit else 0,
            "total_returns": float(c["total_returns"]) if first_visit else 0,
            "latitude": float(c["latitude"]) if c["latitude"] else None,
            "longitude": float(c["longitude"]) if c["longitude"] else None,
        })

    # Header from first row or aggregate
    header = {}
    if customers:
        first = customers[0]
        header = {
            "route_code": first["route_code"],
            "route_name": "",
            "user_code": first["user_code"],
            "user_name": first["user_name"],
            "total_visits": total_visits,
            "scheduled": len(set((c["route_code"], c["customer_code"], str(c["date"])) for c in customers if c["is_planned"])),
            "planned_visits": planned_count,
            "productive_visits": productive_count,
        }

    return {
        "header": header,
        "customers": customer_list,
    }
