"""Endorsement Report endpoint."""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS     = {'date_from', 'date_to', 'route', 'user_code'}
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}


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

    # --- Detail rows: visits + journey plan check + deduplicated customer sales ---
    vw, vp = build_where(filters, date_col='date', prefix='cv')

    # RSIC subquery filtered by date+route to avoid full table scan
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rsic_w, rsic_p = build_where(f_rsic, date_col='date')

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
        f"  ON cv.route_code = jp.route_code "
        f"  AND cv.customer_code = jp.customer_code "
        f"  AND cv.date = jp.date "
        f"LEFT JOIN ( "
        f"  SELECT route_code, customer_code, date, "
        f"    ROUND(SUM(total_sales)::numeric, 2) AS total_value, "
        f"    ROUND(SUM(total_gr_sales + total_damage_sales + total_expiry_sales)::numeric, 2) AS total_returns "
        f"  FROM ( "
        f"    SELECT DISTINCT ON (route_code, item_code, customer_code, date) "
        f"      route_code, customer_code, date, total_sales, "
        f"      total_gr_sales, total_damage_sales, total_expiry_sales "
        f"    FROM rpt_route_sales_by_item_customer "
        f"    WHERE {rsic_w} "
        f"    ORDER BY route_code, item_code, customer_code, date "
        f"  ) dedup "
        f"  GROUP BY route_code, customer_code, date "
        f") s ON cv.route_code = s.route_code "
        f"  AND cv.customer_code = s.customer_code "
        f"  AND cv.date = s.date "
        f"WHERE {vw} "
        f"ORDER BY cv.date, cv.arrival_time",
        rsic_p + vp
    )

    # Get RSSI total per (route, date) — authoritative total matching Dashboard
    RSSI_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'sales_org'}
    f_rssi = {k: v for k, v in filters.items() if k in RSSI_KEYS}
    sw, sp = build_where(f_rssi, date_col='date')
    org_cond, org_params = "", []
    if filters.get('sales_org') and not filters.get('route'):
        orgs = [v.strip() for v in filters['sales_org'].split(',') if v.strip()]
        org_cond = f" AND sales_org_code IN ({','.join(['%s']*len(orgs))})"
        org_params = orgs
    rssi_rows = query(
        f"SELECT date, route_code, ROUND(SUM(total_sales)::numeric, 2) AS total_sales "
        f"FROM (SELECT DISTINCT ON (route_code, item_code, date) "
        f"  date, route_code, total_sales "
        f"  FROM rpt_route_sales_summary_by_item WHERE {sw}{org_cond} "
        f"  ORDER BY route_code, item_code, date) t "
        f"GROUP BY date, route_code",
        sp + org_params
    )
    rssi_map = {(str(r['date']), r['route_code']): float(r['total_sales']) for r in rssi_rows}

    # Build customer detail list (dedup sales on repeated visits to same customer+date)
    customer_list = []
    seen = set()
    rsic_totals = {}  # (date, route_code) -> RSIC sum for scaling
    raw_rows = []

    for c in customers:
        cust_key = (c["customer_code"], str(c["date"]))
        first_visit = cust_key not in seen
        seen.add(cust_key)
        raw_val = float(c["total_value"]) if first_visit else 0
        raw_ret = float(c["total_returns"]) if first_visit else 0
        dk = (str(c["date"]), c["route_code"])
        rsic_totals[dk] = rsic_totals.get(dk, 0) + raw_val
        raw_rows.append({
            "date":           str(c["date"]) if c["date"] else None,
            "salesman_code":  c["user_code"],
            "salesman_name":  c["user_name"],
            "customer_code":  c["customer_code"],
            "customer_name":  c["customer_name"],
            "channel_name":   c["channel_name"],
            "route_code":     c["route_code"],
            "is_planned":     c["is_planned"],
            "check_in":       str(c["arrival_time"])[11:19] if c["arrival_time"] else None,
            "check_out":      str(c["out_time"])[11:19] if c["out_time"] else None,
            "raw_value":      raw_val,
            "raw_returns":    raw_ret,
            "latitude":       float(c["latitude"]) if c["latitude"] else None,
            "longitude":      float(c["longitude"]) if c["longitude"] else None,
        })

    # Scale each customer's sales proportionally to RSSI total (matches Dashboard)
    for row in raw_rows:
        dk = (row["date"], row["route_code"])
        rsic_sum = rsic_totals.get(dk, 0)
        rssi_total = rssi_map.get(dk, 0)
        if rsic_sum > 0 and rssi_total > 0:
            scale = rssi_total / rsic_sum
            scaled_val = round(row["raw_value"] * scale, 2)
            scaled_ret = round(row["raw_returns"] * scale, 2)
        else:
            scaled_val = row["raw_value"]
            scaled_ret = row["raw_returns"]
        customer_list.append({
            **{k: v for k, v in row.items() if k not in ("raw_value", "raw_returns")},
            "is_productive":  scaled_val > 0,
            "total_value":    scaled_val,
            "total_returns":  scaled_ret,
        })

    # --- KPI totals from rpt_coverage_summary ---
    # When no route/user filter: JOIN dim_route has_active_assignment=true (matches Dashboard first load)
    # When route/user filter applied: query directly without active-assignment restriction
    f_cov = {k: v for k, v in filters.items() if k in COVERAGE_KEYS}
    cw, cp = build_where(f_cov, date_col='visit_date', prefix='c')
    _has_specific_filter = bool(filters.get('route') or filters.get('user_code'))
    if _has_specific_filter:
        cov_row = query_one(
            f"SELECT "
            f"  COALESCE(SUM(c.scheduled_calls), 0)    AS scheduled, "
            f"  COALESCE(SUM(c.total_actual_calls), 0) AS total_actual, "
            f"  COALESCE(SUM(c.planned_calls), 0)      AS planned, "
            f"  COALESCE(SUM(c.selling_calls), 0)      AS selling "
            f"FROM rpt_coverage_summary c "
            f"WHERE {cw}",
            cp
        )
    else:
        cov_row = query_one(
            f"SELECT "
            f"  COALESCE(SUM(c.scheduled_calls), 0)    AS scheduled, "
            f"  COALESCE(SUM(c.total_actual_calls), 0) AS total_actual, "
            f"  COALESCE(SUM(c.planned_calls), 0)      AS planned, "
            f"  COALESCE(SUM(c.selling_calls), 0)      AS selling "
            f"FROM rpt_coverage_summary c "
            f"JOIN dim_route _dr ON c.route_code = _dr.code AND _dr.has_active_assignment = true "
            f"WHERE {cw}",
            cp
        )

    scheduled_calls = int(cov_row['scheduled'])    if cov_row else 0
    total_actual    = int(cov_row['total_actual']) if cov_row else 0
    planned_count   = int(cov_row['planned'])      if cov_row else 0
    selling_count   = int(cov_row['selling'])      if cov_row else 0
    unplanned_count = max(0, total_actual - planned_count)
    # Coverage = planned / scheduled * 100 — matches Dashboard formula
    coverage_pct    = min(100.0, round(planned_count / scheduled_calls * 100, 1)) if scheduled_calls else 0

    # Header: identity info from first visit row, KPIs from coverage_summary
    header = {}
    if customers or cov_row:
        first = customers[0] if customers else None
        header = {
            "route_code":            first["route_code"] if first else "",
            "route_name":            "",
            "user_code":             first["user_code"] if first else "",
            "user_name":             first["user_name"] if first else "",
            "total_visits":          total_actual,
            "scheduled_calls":       scheduled_calls,
            "planned_visits":        planned_count,
            "unplanned_visits":      unplanned_count,
            "productive_visits":     selling_count,
            "non_productive_visits": max(0, total_actual - selling_count),
            "coverage_pct":          coverage_pct,
        }

    return {
        "header": header,
        "customers": customer_list,
    }
