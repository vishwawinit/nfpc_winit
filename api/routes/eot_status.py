"""EOT Status report endpoint.
End-of-trip summary: user info, route compliance, KPIs, call metrics, journey stops.

Sources:
  - User/Journey: rpt_journeys, rpt_eot
  - Route plan: rpt_journey_plan + rpt_customer_visits
  - Sales: rpt_route_sales_by_item_customer
  - Collection: rpt_collections
  - Calls: rpt_coverage_summary (with journey_plan fallback)
  - Stops: rpt_customer_visits
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/eot-status")
def get_eot_status(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_code: Optional[str] = None,
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
            user_code = "__NO_MATCH__"
        elif resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # --- User & Journey Info ---
    jw, jp = build_where(filters, date_col='date')
    journey_row = query_one(
        f"SELECT user_code, user_name, route_code, route_name, "
        f"  vehicle_code, date, start_time, end_time "
        f"FROM rpt_journeys WHERE {jw} ORDER BY date DESC LIMIT 1", jp
    )

    user_info = None
    if journey_row:
        user_info = {
            "user_code": journey_row["user_code"],
            "user_name": journey_row["user_name"],
            "route_code": journey_row["route_code"],
            "route_name": journey_row["route_name"],
            "vehicle": journey_row["vehicle_code"],
            "date": str(journey_row["date"]) if journey_row["date"] else None,
            "start_time": str(journey_row["start_time"]) if journey_row["start_time"] else None,
            "end_time": str(journey_row["end_time"]) if journey_row["end_time"] else None,
        }

    # --- EOT info ---
    ew, ep = build_where(filters, date_col='trip_date')
    eot_row = query_one(
        f"SELECT eot_type, eot_time FROM rpt_eot WHERE {ew} ORDER BY trip_date DESC LIMIT 1", ep
    )
    if user_info and eot_row:
        user_info["eot_type"] = eot_row["eot_type"]
        user_info["eot_time"] = str(eot_row["eot_time"]) if eot_row["eot_time"] else None

    # --- Route plan compliance ---
    jpw, jpp = build_where(filters, date_col='date')
    plan_row = query_one(
        f"SELECT COUNT(*) AS total_planned FROM rpt_journey_plan WHERE {jpw}", jpp
    )
    total_planned = int(plan_row["total_planned"]) if plan_row else 0

    # Visited = planned customers that got a visit
    visited_row = query_one(
        f"SELECT COUNT(*) AS visited FROM rpt_journey_plan jp "
        f"WHERE EXISTS (SELECT 1 FROM rpt_customer_visits cv "
        f"  WHERE cv.route_code = jp.route_code AND cv.date = jp.date "
        f"  AND cv.customer_code = jp.customer_code) AND {jpw}", jpp
    )
    visited = int(visited_row["visited"]) if visited_row else 0
    route_plan_followed = total_planned > 0 and visited >= total_planned
    all_customers_visited = route_plan_followed

    # --- KPIs: order count, sales, collection ---
    # Sales from rpt_route_sales_by_item_customer (correct, no double-count)
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date')
    sales_row = query_one(
        f"SELECT COALESCE(SUM(total_sales), 0) AS sales_amount "
        f"FROM rpt_route_sales_by_item_customer WHERE {rw}", rp
    )

    # Order count from rpt_sales_detail (dedup by trx_code, status=200)
    sw, sp = build_where(filters, date_col='trx_date')
    order_row = query_one(
        f"SELECT COUNT(DISTINCT trx_code) AS order_count "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND trx_status = 200 AND {sw}", sp
    )

    # Collection
    colw, colp = build_where(filters, date_col='receipt_date')
    col_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS collection_amount "
        f"FROM rpt_collections WHERE {colw}", colp
    )

    kpis = {
        "order_count": int(order_row["order_count"]) if order_row else 0,
        "sales_amount": float(sales_row["sales_amount"]) if sales_row else 0,
        "collection_amount": float(col_row["collection_amount"]) if col_row else 0,
    }

    # --- Call Metrics ---
    # Primary: rpt_coverage_summary
    cw, cp = build_where(filters, date_col='visit_date')
    call_row = query_one(
        f"SELECT COALESCE(SUM(scheduled_calls),0) AS scheduled, "
        f"  COALESCE(SUM(total_actual_calls),0) AS total_actual, "
        f"  COALESCE(SUM(planned_calls),0) AS planned, "
        f"  COALESCE(SUM(selling_calls),0) AS selling, "
        f"  COALESCE(SUM(planned_selling_calls),0) AS planned_selling "
        f"FROM rpt_coverage_summary WHERE {cw}", cp
    )

    scheduled = int(call_row["scheduled"]) if call_row else 0
    total_actual = int(call_row["total_actual"]) if call_row else 0
    planned = int(call_row["planned"]) if call_row else 0
    selling = int(call_row["selling"]) if call_row else 0

    # Fallback to raw tables if no coverage data
    if scheduled == 0 and total_actual == 0:
        scheduled = total_planned
        vw, vp = build_where(filters, date_col='date')
        vis_row = query_one(f"SELECT COUNT(*) AS cnt FROM rpt_customer_visits WHERE {vw}", vp)
        total_actual = int(vis_row["cnt"]) if vis_row else 0
        planned = visited
        selling = 0

    unplanned = max(0, total_actual - planned)
    productive = selling
    unproductive = max(0, total_actual - selling)
    missed = max(0, scheduled - planned)
    strike_rate = round(selling / total_actual * 100, 2) if total_actual else 0

    call_metrics = {
        "planned": scheduled,
        "visited": total_actual,
        "productive": productive,
        "unproductive": unproductive,
        "missed": missed,
        "total_calls": total_actual,
        "strike_rate": strike_rate,
    }

    # --- Users with journey stops ---
    # Group visits by user, each user has their stops
    vw2, vp2 = build_where(filters, date_col='date')
    # Get visits
    user_visits = query(
        f"SELECT cv.user_code, cv.user_name, cv.route_code, cv.route_name, "
        f"  cv.customer_code, cv.customer_name, "
        f"  cv.arrival_time, cv.out_time, cv.total_time_mins, "
        f"  cv.is_productive, cv.latitude, cv.longitude, cv.date "
        f"FROM rpt_customer_visits cv WHERE {vw2} "
        f"ORDER BY cv.user_code, cv.arrival_time", vp2
    )

    # Pre-compute productive set: (route, customer, date) combos that have a sale
    # Use a simpler query - just get distinct combos with sales > 0
    f_rsic2 = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw3, rp3 = build_where(f_rsic2, date_col='date')
    prod_rows = query(
        f"SELECT route_code, customer_code, date "
        f"FROM rpt_route_sales_by_item_customer WHERE total_sales > 0 AND {rw3} "
        f"GROUP BY route_code, customer_code, date", rp3
    )
    productive_set = set((r["route_code"], r["customer_code"], str(r["date"])) for r in prod_rows)

    # Group by user
    from collections import OrderedDict
    users_map = OrderedDict()
    for v in user_visits:
        uc = v["user_code"]
        if uc not in users_map:
            users_map[uc] = {
                "user_code": uc,
                "user_name": v["user_name"],
                "route_code": v["route_code"],
                "route_name": v["route_name"],
                "date": str(v["date"]) if v["date"] else None,
                "total_visits": 0,
                "productive_visits": 0,
                "total_time_mins": 0,
                "stops": [],
            }
        u = users_map[uc]
        is_prod = (v["route_code"], v["customer_code"], str(v["date"])) in productive_set
        u["total_visits"] += 1
        if is_prod:
            u["productive_visits"] += 1
        u["total_time_mins"] += v["total_time_mins"] or 0
        u["stops"].append({
            "sequence": len(u["stops"]) + 1,
            "customer_code": v["customer_code"],
            "customer_name": v["customer_name"],
            "arrival_time": str(v["arrival_time"]) if v["arrival_time"] else None,
            "departure_time": str(v["out_time"]) if v["out_time"] else None,
            "duration_mins": v["total_time_mins"],
            "productive": is_prod,
            "latitude": v["latitude"],
            "longitude": v["longitude"],
        })

    users_list = list(users_map.values())
    # Sort by total visits descending
    users_list.sort(key=lambda u: u["total_visits"], reverse=True)

    return {
        "route_plan_followed": route_plan_followed,
        "all_customers_visited": all_customers_visited,
        "kpis": kpis,
        "call_metrics": call_metrics,
        "users": users_list,
    }
