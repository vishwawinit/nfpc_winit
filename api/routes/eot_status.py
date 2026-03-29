"""EOT Status report endpoint.
Only shows users who submitted an EOT (End of Trip) for the selected date range.
Per-user journey stops, KPIs, and call metrics are derived from their EOT records.
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes
from collections import OrderedDict

router = APIRouter()


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

    # --- Step 1: Get one row per (user_code, trip_date) ---
    ew, ep = build_where(filters, date_col='trip_date')
    eot_rows = query(
        f"SELECT DISTINCT ON (user_code, trip_date) user_code, user_name, route_code, route_name, "
        f"  sales_org_code, eot_type, eot_time, trip_date, "
        f"  route_start_datetime, unload_datetime, eot_status "
        f"FROM rpt_eot WHERE {ew} "
        f"ORDER BY user_code, trip_date DESC",
        ep
    )

    if not eot_rows:
        return {"kpis": {}, "call_metrics": {}, "users": []}

    eot_user_codes = set(r["user_code"] for r in eot_rows)

    # --- Step 2: Customer visits for EOT users ---
    vw, vp = build_where(filters, date_col='date')
    user_visits = query(
        f"SELECT cv.user_code, cv.user_name, cv.route_code, cv.route_name, "
        f"  cv.customer_code, cv.customer_name, "
        f"  cv.arrival_time, cv.out_time, cv.total_time_mins, "
        f"  cv.is_productive, cv.latitude, cv.longitude, cv.date "
        f"FROM rpt_customer_visits cv WHERE {vw} "
        f"ORDER BY cv.user_code, cv.arrival_time",
        vp
    )
    # Filter to EOT users only
    user_visits = [v for v in user_visits if v["user_code"] in eot_user_codes]

    # --- Step 3: Productive set from sales ---
    rsic_keys = {'date_from', 'date_to', 'route', 'user_code'}
    f_rsic = {k: v for k, v in filters.items() if k in rsic_keys}
    rw, rp = build_where(f_rsic, date_col='date')
    prod_rows = query(
        f"SELECT route_code, customer_code, date "
        f"FROM rpt_route_sales_by_item_customer WHERE total_sales > 0 AND {rw} "
        f"GROUP BY route_code, customer_code, date",
        rp
    )
    productive_set = set((r["route_code"], r["customer_code"], str(r["date"])) for r in prod_rows)

    # --- Step 4: Build per-(user, date) data ---
    users_map = OrderedDict()
    for eot in eot_rows:
        uc = eot["user_code"]
        td = str(eot["trip_date"]) if eot["trip_date"] else None
        key = (uc, td)
        users_map[key] = {
            "user_code": uc,
            "user_name": eot["user_name"],
            "route_code": eot["route_code"],
            "route_name": eot["route_name"],
            "eot_type": eot["eot_type"],
            "eot_time": str(eot["eot_time"]) if eot["eot_time"] else None,
            "trip_date": td,
            "route_start_datetime": str(eot["route_start_datetime"]) if eot.get("route_start_datetime") else None,
            "unload_datetime": str(eot["unload_datetime"]) if eot.get("unload_datetime") else None,
            "eot_status": eot.get("eot_status") or "Submitted",
            "total_visits": 0,
            "productive_visits": 0,
            "total_time_mins": 0,
        }

    for v in user_visits:
        uc = v["user_code"]
        vdate = str(v["date"]) if v["date"] else None
        key = (uc, vdate)
        if key not in users_map:
            continue
        u = users_map[key]
        is_prod = (v["route_code"], v["customer_code"], vdate) in productive_set
        u["total_visits"] += 1
        if is_prod:
            u["productive_visits"] += 1
        u["total_time_mins"] += v["total_time_mins"] or 0

    users_list = list(users_map.values())
    users_list.sort(key=lambda u: (u["trip_date"] or "", u["total_visits"]), reverse=True)

    # --- Step 5: Aggregate KPIs across EOT users ---
    cw, cp = build_where(filters, date_col='visit_date')
    call_row = query_one(
        f"SELECT COALESCE(SUM(scheduled_calls),0) AS scheduled, "
        f"  COALESCE(SUM(total_actual_calls),0) AS total_actual, "
        f"  COALESCE(SUM(planned_calls),0) AS planned, "
        f"  COALESCE(SUM(selling_calls),0) AS selling "
        f"FROM rpt_coverage_summary WHERE {cw}",
        cp
    )
    scheduled = int(call_row["scheduled"]) if call_row else 0
    total_actual = int(call_row["total_actual"]) if call_row else 0
    planned = int(call_row["planned"]) if call_row else 0
    selling = int(call_row["selling"]) if call_row else 0

    unproductive = max(0, total_actual - selling)
    missed = max(0, scheduled - planned)
    strike_rate = round(selling / total_actual * 100, 2) if total_actual else 0

    call_metrics = {
        "planned": scheduled,
        "visited": total_actual,
        "productive": selling,
        "unproductive": unproductive,
        "missed": missed,
        "total_calls": total_actual,
        "strike_rate": strike_rate,
    }

    sales_filters = {k: v for k, v in filters.items() if k in {'date_from', 'date_to', 'route', 'user_code'}}
    sw_s, sp_s = build_where(sales_filters, date_col='date')
    org_cond_s = ""
    org_params_s = []
    if filters.get('sales_org'):
        orgs_s = [v.strip() for v in filters['sales_org'].split(',') if v.strip()]
        org_ph_s = ','.join(['%s'] * len(orgs_s))
        org_cond_s = f" AND sales_org_code IN ({org_ph_s})"
        org_params_s = orgs_s
    sales_row = query_one(
        f"SELECT COALESCE(SUM(total_sales), 0) AS sales_amount "
        f"FROM (SELECT DISTINCT ON (route_code, item_code, date) total_sales "
        f"  FROM rpt_route_sales_summary_by_item WHERE {sw_s}{org_cond_s} "
        f"  ORDER BY route_code, item_code, date) t",
        sp_s + org_params_s
    )
    sw, sp = build_where(filters, date_col='trx_date')
    order_row = query_one(
        f"SELECT COUNT(DISTINCT trx_code) AS order_count "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND trx_status = 200 AND {sw}", sp
    )
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

    return {
        "kpis": kpis,
        "call_metrics": call_metrics,
        "users": users_list,
    }
