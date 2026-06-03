"""Endorsement Report endpoint."""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}
RSSI_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'sales_org'}


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

    # ── Visit rows from rpt_customer_visits ──────────────────────────────
    vw, vp = build_where(filters, date_col='date', prefix='cv')

    # RSIC subquery: deduplicated customer sales (DISTINCT ON removes item duplicates)
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rsic_w, rsic_p = build_where(f_rsic, date_col='date')

    raw_visits = query(
        f"SELECT cv.customer_code, cv.customer_name, cv.channel_name, "
        f"  cv.route_code, cv.user_code, cv.user_name, cv.date, "
        f"  cv.arrival_time, cv.out_time, "
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

    # ── RSSI totals per (route, date) — authoritative sales total ─────────
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

    # ── Build customer list ───────────────────────────────────────────────
    # One row per unique (customer_code, date) — matches how coverage_summary counts visits.
    # KPIs are computed from this same deduplicated list so table count = KPI total_visits.
    seen = set()
    rsic_totals = {}
    rows_with_raw = []

    for c in raw_visits:
        cust_key = (c["customer_code"], str(c["date"]))
        if cust_key in seen:
            continue          # skip repeat visits — count each customer once per day
        seen.add(cust_key)

        raw_val = max(0.0, float(c["total_value"]))
        raw_ret = max(0.0, float(c["total_returns"]))

        if raw_val > 0:
            dk = (str(c["date"]), c["route_code"])
            rsic_totals[dk] = rsic_totals.get(dk, 0.0) + raw_val

        rows_with_raw.append({
            "date":          str(c["date"]) if c["date"] else None,
            "salesman_code": c["user_code"],
            "salesman_name": c["user_name"],
            "customer_code": c["customer_code"],
            "customer_name": c["customer_name"],
            "channel_name":  c["channel_name"],
            "route_code":    c["route_code"],
            "is_planned":    c["is_planned"],
            "check_in":      str(c["arrival_time"])[11:19] if c["arrival_time"] else None,
            "check_out":     str(c["out_time"])[11:19] if c["out_time"] else None,
            "latitude":      float(c["latitude"]) if c["latitude"] else None,
            "longitude":     float(c["longitude"]) if c["longitude"] else None,
            "_raw_val":      raw_val,
            "_raw_ret":      raw_ret,
        })

    # Apply proportional scaling to match RSSI totals
    customer_list = []
    for row in rows_with_raw:
        dk = (row["date"], row["route_code"])
        rsic_sum   = rsic_totals.get(dk, 0.0)
        rssi_total = rssi_map.get(dk, 0.0)

        if row["_raw_val"] > 0 and rsic_sum > 0 and rssi_total > 0:
            scale      = rssi_total / rsic_sum
            scaled_val = round(row["_raw_val"] * scale, 2)
            scaled_ret = round(row["_raw_ret"] * scale, 2)
        else:
            scaled_val = row["_raw_val"]
            scaled_ret = row["_raw_ret"]

        customer_list.append({
            "date":          row["date"],
            "salesman_code": row["salesman_code"],
            "salesman_name": row["salesman_name"],
            "customer_code": row["customer_code"],
            "customer_name": row["customer_name"],
            "channel_name":  row["channel_name"],
            "route_code":    row["route_code"],
            "is_planned":    row["is_planned"],
            "check_in":      row["check_in"],
            "check_out":     row["check_out"],
            "is_productive": scaled_val > 0,
            "total_value":   scaled_val,
            "total_returns": scaled_ret,
            "latitude":      row["latitude"],
            "longitude":     row["longitude"],
        })

    # ── KPIs — computed from customer_list so they always match the table ──
    jpw, jpp = build_where(filters, date_col='date')
    jp_row = query_one(f"SELECT COUNT(*) AS scheduled FROM rpt_journey_plan WHERE {jpw}", jpp)
    scheduled_calls  = int(jp_row['scheduled']) if jp_row else 0

    total_visits     = len(customer_list)
    planned_count    = sum(1 for r in customer_list if r['is_planned'])
    productive_count = sum(1 for r in customer_list if r['is_productive'])
    unplanned_count  = max(0, total_visits - planned_count)
    coverage_pct     = min(100.0, round(planned_count / scheduled_calls * 100, 1)) if scheduled_calls else 0

    header = {}
    if raw_visits:
        first = raw_visits[0]
        header = {
            "route_code":            first["route_code"],
            "route_name":            "",
            "user_code":             first["user_code"],
            "user_name":             first["user_name"],
            "total_visits":          total_visits,
            "scheduled_calls":       scheduled_calls,
            "planned_visits":        planned_count,
            "unplanned_visits":      unplanned_count,
            "productive_visits":     productive_count,
            "non_productive_visits": max(0, total_visits - productive_count),
            "coverage_pct":          coverage_pct,
        }

    return {"header": header, "customers": customer_list}
