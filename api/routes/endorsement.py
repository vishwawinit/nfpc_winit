"""Endorsement Report endpoint.
Matches: usp_EndorsementReport_Customers_BySubGroups

Customer visit details with sales, planned/unplanned, productive detection.

Sources:
  - Visits: rpt_customer_visits
  - Sales: rpt_route_sales_by_item_customer
  - Planned: rpt_journey_plan (match = planned visit)
  - Productive: has matching sale
"""
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

    vw, vp = build_where(filters, date_col='date')

    # Header: route info + summary
    header_row = query_one(
        f"SELECT route_code, route_name, user_code, user_name, sales_org_code, "
        f"  MIN(arrival_time) AS depot_out_time, MAX(out_time) AS depot_in_time, "
        f"  EXTRACT(EPOCH FROM MAX(out_time) - MIN(arrival_time)) / 60 AS total_driving_mins, "
        f"  COUNT(*) AS total_visits, "
        f"  ROUND(AVG(total_time_mins)::numeric, 1) AS avg_time_per_visit "
        f"FROM rpt_customer_visits WHERE {vw} "
        f"GROUP BY route_code, route_name, user_code, user_name, sales_org_code",
        vp
    )

    header = {}
    if header_row:
        header = {
            "route_code": header_row["route_code"],
            "route_name": header_row["route_name"],
            "user_code": header_row["user_code"],
            "user_name": header_row["user_name"],
            "sales_org_code": header_row["sales_org_code"],
            "depot_out_time": str(header_row["depot_out_time"])[11:16] if header_row["depot_out_time"] else None,
            "depot_in_time": str(header_row["depot_in_time"])[11:16] if header_row["depot_in_time"] else None,
            "total_driving_mins": round(float(header_row["total_driving_mins"]), 1) if header_row["total_driving_mins"] else 0,
            "total_visits": int(header_row["total_visits"]),
            "avg_time_per_visit": float(header_row["avg_time_per_visit"]) if header_row["avg_time_per_visit"] else 0,
        }

    # Pre-compute sets for planned + productive
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date')

    # Planned set: journey plan entries
    plan_rows = query(
        f"SELECT DISTINCT route_code, customer_code, date FROM rpt_journey_plan WHERE {rw}", rp
    )
    planned_set = set((r["route_code"], r["customer_code"], str(r["date"])) for r in plan_rows)

    # Productive set: has a sale
    prod_rows = query(
        f"SELECT DISTINCT route_code, customer_code, date "
        f"FROM rpt_route_sales_by_item_customer WHERE total_sales > 0 AND {rw}", rp
    )
    productive_set = set((r["route_code"], r["customer_code"], str(r["date"])) for r in prod_rows)

    # Sales per customer+route+date
    sales_rows = query(
        f"SELECT route_code, customer_code, date, "
        f"  ROUND(SUM(total_sales)::numeric, 2) AS total_value, "
        f"  ROUND(SUM(total_gr_sales + total_damage_sales + total_expiry_sales)::numeric, 2) AS total_returns "
        f"FROM rpt_route_sales_by_item_customer WHERE {rw} "
        f"GROUP BY route_code, customer_code, date",
        rp
    )
    sales_map = {(r["route_code"], r["customer_code"], str(r["date"])): r for r in sales_rows}

    # Visits
    visits = query(
        f"SELECT customer_code, customer_name, channel_name, "
        f"  route_code, date, arrival_time, out_time, total_time_mins, "
        f"  latitude, longitude "
        f"FROM rpt_customer_visits WHERE {vw} ORDER BY arrival_time",
        vp
    )

    customer_list = []
    planned_count = 0
    productive_count = 0
    seen_customers = set()  # Track to avoid double-counting sales on repeat visits
    for v in visits:
        key = (v["route_code"], v["customer_code"], str(v["date"]))
        is_planned = key in planned_set
        is_productive = key in productive_set
        s = sales_map.get(key, {})

        # Only count sales on first visit to this customer (avoid duplicate totals)
        cust_key = (v["customer_code"], str(v["date"]))
        first_visit = cust_key not in seen_customers
        seen_customers.add(cust_key)

        if is_planned:
            planned_count += 1
        if is_productive:
            productive_count += 1

        customer_list.append({
            "customer_code": v["customer_code"],
            "customer_name": v["customer_name"],
            "channel_name": v["channel_name"],
            "is_planned": is_planned,
            "visit_type": "JP" if is_planned else "UJP",
            "arrival_time": str(v["arrival_time"])[11:16] if v["arrival_time"] else None,
            "out_time": str(v["out_time"])[11:16] if v["out_time"] else None,
            "time_spent_mins": float(v["total_time_mins"]) if v["total_time_mins"] else 0,
            "is_productive": is_productive,
            "total_value": float(s.get("total_value", 0)) if first_visit else 0,
            "total_returns": float(s.get("total_returns", 0)) if first_visit else 0,
            "latitude": float(v["latitude"]) if v["latitude"] else None,
            "longitude": float(v["longitude"]) if v["longitude"] else None,
        })

    if header:
        header["scheduled"] = len(planned_set)  # Journey plan entries count
        header["planned_visits"] = planned_count  # Visit rows that matched plan
        header["productive_visits"] = productive_count

    return {
        "header": header,
        "customers": customer_list,
    }
