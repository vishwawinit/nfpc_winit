"""Salesman Journey report endpoint.

Two modes:
  1. No user_code → returns list of all salesmen with summary KPIs (for accordion list)
  2. With user_code → returns detailed journey with visits timeline (accordion expand)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/salesman-journey")
def get_salesman_journey(
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
            return {"users": [], "detail": None}
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

    # Auto-fallback: if requested date has no data, use latest available date
    if date_from and date_from == date_to:
        check = query(
            "SELECT MAX(date) AS latest FROM rpt_customer_visits WHERE date <= %s",
            [date_from]
        )
        if check and check[0]["latest"]:
            latest = check[0]["latest"]
            if str(latest) != str(date_from):
                filters['date_from'] = latest
                filters['date_to'] = latest

    # User list: visit-row-level productive/non-productive (consistent with detail endpoint)
    vw, vp = build_where(filters, date_col='date', prefix='cv')
    rw, rp = build_where({k: v for k, v in filters.items() if k in RSIC_KEYS}, date_col='date', prefix='rc')

    users = query(
        f"WITH prod_set AS ( "
        f"  SELECT DISTINCT rc.route_code, rc.customer_code, rc.date "
        f"  FROM rpt_route_sales_by_item_customer rc WHERE rc.total_sales > 0 AND {rw} "
        f"), "
        f"visit_stats AS ( "
        f"  SELECT cv.user_code, cv.user_name, cv.route_code, cv.route_name, "
        f"    COUNT(*) AS total_visits, "
        f"    COUNT(ps.customer_code) AS productive_count, "
        f"    COUNT(*) - COUNT(ps.customer_code) AS non_productive_count "
        f"  FROM rpt_customer_visits cv "
        f"  LEFT JOIN prod_set ps "
        f"    ON cv.route_code = ps.route_code AND cv.customer_code = ps.customer_code AND cv.date = ps.date "
        f"  WHERE {vw} "
        f"  GROUP BY cv.user_code, cv.user_name, cv.route_code, cv.route_name "
        f"), "
        f"sales_stats AS ( "
        f"  SELECT rc.user_code, "
        f"    ROUND(SUM(rc.total_sales)::numeric, 2) AS total_sales, "
        f"    COUNT(DISTINCT rc.item_code) AS sku_count "
        f"  FROM rpt_route_sales_by_item_customer rc WHERE {rw} "
        f"  GROUP BY rc.user_code "
        f") "
        f"SELECT vs.user_code, vs.user_name, vs.route_code, vs.route_name, "
        f"  vs.total_visits, vs.productive_count, vs.non_productive_count, "
        f"  COALESCE(ss.total_sales, 0) AS total_sales, "
        f"  COALESCE(ss.sku_count, 0) AS sku_count "
        f"FROM visit_stats vs "
        f"LEFT JOIN sales_stats ss ON vs.user_code = ss.user_code "
        f"ORDER BY total_sales DESC NULLS LAST",
        rp + vp + rp
    )

    return {
        "users": users,
        "detail": None,
        "effective_date_from": str(filters.get('date_from', date_from or '')),
        "effective_date_to": str(filters.get('date_to', date_to or '')),
    }


@router.get("/salesman-journey/detail")
def get_salesman_journey_detail(
    user_code: str = Query(..., description="Salesman code"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'route': route,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # Journey info
    jw, jp = build_where(filters, date_col='date')
    journey_row = query_one(
        f"SELECT user_code, user_name, route_code, route_name, "
        f"  sales_org_code, date, start_time, end_time, vehicle_code "
        f"FROM rpt_journeys WHERE {jw} ORDER BY date DESC LIMIT 1", jp
    )

    journey_info = {}
    if journey_row:
        journey_info = {
            "user_code": journey_row["user_code"],
            "user_name": journey_row["user_name"],
            "route_code": journey_row["route_code"],
            "route_name": journey_row["route_name"],
            "vehicle": journey_row["vehicle_code"],
            "journey_start": str(journey_row["start_time"])[11:16] if journey_row["start_time"] else None,
            "journey_end": str(journey_row["end_time"])[11:16] if journey_row["end_time"] else None,
        }

    # Sales KPIs
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date')
    sales_row = query_one(
        f"SELECT COALESCE(SUM(total_sales), 0) AS total_sales, "
        f"  COALESCE(SUM(total_gr_sales + total_damage_sales + total_expiry_sales), 0) AS total_returns "
        f"FROM rpt_route_sales_by_item_customer WHERE {rw}", rp
    )

    # Collection
    cw, cp = build_where(filters, date_col='receipt_date')
    coll_row = query_one(f"SELECT COALESCE(SUM(amount), 0) AS collection FROM rpt_collections WHERE {cw}", cp)

    kpis = {
        "total_sales": round(float(sales_row["total_sales"]), 2) if sales_row else 0,
        "collection": round(float(coll_row["collection"]), 2) if coll_row else 0,
    }

    # Visits with productive detection
    prod_rows = query(
        f"SELECT DISTINCT route_code, customer_code, date "
        f"FROM rpt_route_sales_by_item_customer WHERE total_sales > 0 AND {rw}", rp
    )
    productive_set = set((r["route_code"], r["customer_code"], str(r["date"])) for r in prod_rows)

    vw, vp = build_where(filters, date_col='date')
    raw_visits = query(
        f"SELECT date, customer_code, customer_name, route_code, "
        f"  arrival_time, out_time, total_time_mins, latitude, longitude "
        f"FROM rpt_customer_visits WHERE {vw} ORDER BY date, arrival_time", vp
    )

    visits = []
    for i, v in enumerate(raw_visits):
        is_prod = (v["route_code"], v["customer_code"], str(v["date"])) in productive_set
        visits.append({
            "sequence": i + 1,
            "date": str(v["date"]),
            "customer_code": v["customer_code"],
            "customer_name": v["customer_name"],
            "arrival_time": str(v["arrival_time"])[11:16] if v["arrival_time"] else None,
            "out_time": str(v["out_time"])[11:16] if v["out_time"] else None,
            "duration_mins": v["total_time_mins"],
            "productive": is_prod,
            "latitude": v["latitude"],
            "longitude": v["longitude"],
        })

    return {
        "journey_info": journey_info,
        "kpis": kpis,
        "visits": visits,
    }
