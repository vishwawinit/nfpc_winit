"""MTD Sales Overview report endpoint.
Matches: sp_GetMTDSalesOverviewReport_New + sp_MTDSalesPerformanceReportLableDate

Sources:
  - Daily Sales: rpt_route_sales_by_item_customer (total_sales by date)
  - Cash/Credit: rpt_sales_detail (dedup by trx_code, trx_status=200)
  - Header info: rpt_customer_visits (avg calls/productive mins)
  - Target: rpt_targets
  - Holidays: rpt_holidays
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}


@router.get("/mtd-sales-overview")
def get_mtd_sales_overview(
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    channel: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy filters
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
    d_from = date_from or date(today.year, today.month, 1)
    d_to = date_to or today

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
    }.items() if v is not None}

    # Resolve sales_org to user_codes (summary table has no sales_org column)
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        if not org_rows:
            return _empty()
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            existing = set(base_filters['user_code'].split(','))
            intersected = existing & org_users
            if not intersected:
                return _empty()
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

    # Channel filter: resolve to customer_codes
    channel_cond = ""
    channel_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        cust_rows = query(
            f"SELECT DISTINCT dc.code FROM dim_customer dc "
            f"JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code "
            f"WHERE TRIM(dc.channel_code) IN ({ch_ph})", ch_vals
        )
        if not cust_rows:
            return _empty()
        c_codes = [r['code'] for r in cust_rows]
        c_ph = ','.join(['%s'] * len(c_codes))
        channel_cond = f" AND r.customer_code IN ({c_ph})"
        channel_params = c_codes

    # Item filter (brand/category)
    item_cond = ""
    item_params = []
    if brand or category:
        i_conditions = []
        i_params = []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            b_ph = ','.join(['%s'] * len(b_vals))
            i_conditions.append(f"TRIM(brand_code) IN ({b_ph})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            c_ph = ','.join(['%s'] * len(c_vals))
            i_conditions.append(f"category_code IN ({c_ph})")
            i_params.extend(c_vals)
        i_where = " AND ".join(i_conditions)
        i_rows = query(f"SELECT DISTINCT code FROM dim_item WHERE {i_where}", i_params)
        if not i_rows:
            return _empty()
        i_codes = [r['code'] for r in i_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        item_cond = f" AND r.item_code IN ({i_ph})"
        item_params = i_codes

    filters = {**base_filters, 'date_from': d_from, 'date_to': d_to}

    # --- Header info from rpt_customer_visits ---
    vw, vp = build_where({k: v for k, v in filters.items() if k in COVERAGE_KEYS | {'date_from', 'date_to', 'sales_org'}},
                         date_col='date')
    header_row = query_one(
        f"SELECT "
        f"  sales_org_code AS depot, user_code, user_name AS salesman, "
        f"  route_code, route_name, "
        f"  ROUND(AVG(CASE WHEN is_productive THEN total_time_mins ELSE NULL END)::numeric, 1) AS avg_productive_mins, "
        f"  ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT date), 0), 1) AS avg_daily_calls "
        f"FROM rpt_customer_visits WHERE {vw} "
        f"GROUP BY sales_org_code, user_code, user_name, route_code, route_name",
        vp
    )
    header = {}
    if header_row:
        header = {
            "depot": header_row["depot"],
            "user_code": header_row["user_code"],
            "salesman": header_row["salesman"],
            "route_code": header_row["route_code"],
            "route_name": header_row["route_name"],
            "avg_productive_mins": float(header_row["avg_productive_mins"]) if header_row["avg_productive_mins"] else 0,
            "avg_daily_calls": float(header_row["avg_daily_calls"]) if header_row["avg_daily_calls"] else 0,
        }

    # --- Daily Sales from rpt_route_sales_by_item_customer ---
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rsw, rsp = build_where(f_rsic, date_col='date', prefix='r')
    daily_summary = query(
        f"SELECT r.date AS sale_date, COALESCE(SUM(r.total_sales), 0) AS total_sales "
        f"FROM rpt_route_sales_by_item_customer r "
        f"WHERE {rsw}{channel_cond}{item_cond} "
        f"GROUP BY r.date ORDER BY r.date",
        rsp + channel_params + item_params
    )
    summary_map = {str(r["sale_date"]): float(r["total_sales"]) for r in daily_summary}

    # --- Cash/Credit from rpt_sales_detail (dedup by trx_code, status=200) ---
    sd_filters = {k: v for k, v in filters.items() if k in {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}}
    sw, sp = build_where(sd_filters, date_col='trx_date')
    daily_cc = query(
        f"SELECT sale_date, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '1' THEN net_amount ELSE 0 END), 0) AS cash_sales, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '0' THEN net_amount ELSE 0 END), 0) AS credit_sales "
        f"FROM (SELECT trx_date AS sale_date, trx_code, "
        f"  MIN(payment_type) AS payment_type, MIN(net_amount) AS net_amount "
        f"  FROM rpt_sales_detail WHERE trx_type = 1 AND trx_status = 200 AND {sw} "
        f"  GROUP BY trx_date, trx_code) t "
        f"GROUP BY sale_date ORDER BY sale_date",
        sp
    )
    cc_map = {str(r["sale_date"]): (float(r["cash_sales"]), float(r["credit_sales"])) for r in daily_cc}

    # --- Monthly Target ---
    month_start = date(d_from.year, d_from.month, 1)
    if d_from.month == 12:
        month_end = date(d_from.year, 12, 31)
    else:
        month_end = date(d_from.year, d_from.month + 1, 1) - timedelta(days=1)

    target_filters = {k: v for k, v in {
        'sales_org': sales_org, 'route': route, 'user_code': user_code,
    }.items() if v is not None}
    tf = {**target_filters, 'date_from': month_start, 'date_to': month_end}
    tf = {k: v for k, v in tf.items() if v is not None}
    tw, tp = build_where(tf, date_col='start_date')
    tw_target = tw.replace('user_code', 'salesman_code')
    target_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS monthly_target "
        f"FROM rpt_targets WHERE is_active = true AND {tw_target}", tp
    )
    monthly_target = float(target_row["monthly_target"]) if target_row else 0

    # Working days (Mon-Sat minus holidays)
    holidays = query(
        "SELECT holiday_date FROM rpt_holidays "
        "WHERE holiday_date >= %s AND holiday_date <= %s",
        [month_start, month_end]
    )
    holiday_dates = set(str(r["holiday_date"]) for r in holidays)

    working_days = sum(
        1 for i in range((month_end - month_start).days + 1)
        if (month_start + timedelta(days=i)).weekday() < 6
        and str(month_start + timedelta(days=i)) not in holiday_dates
    )
    daily_target = monthly_target / working_days if working_days else 0

    # --- Build daily data ---
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    cumulative_sales = 0
    cumulative_target = 0

    all_dates = sorted(set(list(summary_map.keys()) + list(cc_map.keys())))
    daily_data = []
    for d_str in all_dates:
        d_obj = date.fromisoformat(d_str)
        total = summary_map.get(d_str, 0)
        cash, credit = cc_map.get(d_str, (0, 0))
        cumulative_sales += total
        cumulative_target += daily_target

        daily_var = total - daily_target
        daily_var_pct = round(daily_var / daily_target * 100, 2) if daily_target else 0

        daily_data.append({
            "date": d_str,
            "day_name": DAY_NAMES[d_obj.weekday()],
            "cash_sales": round(cash, 2),
            "credit_sales": round(credit, 2),
            "total_sales": round(total, 2),
            "target": round(daily_target, 2),
            "daily_var": round(daily_var, 2),
            "daily_var_pct": daily_var_pct,
            "cumulative_sales": round(cumulative_sales, 2),
            "cumulative_target": round(cumulative_target, 2),
        })

    return {
        "header": header,
        "monthly_target": monthly_target,
        "daily_target": round(daily_target, 2),
        "total_achieved": round(cumulative_sales, 2),
        "achievement_pct": round(cumulative_sales / monthly_target * 100, 2) if monthly_target else 0,
        "daily_data": daily_data,
    }


def _empty():
    return {
        "header": {},
        "monthly_target": 0, "daily_target": 0,
        "total_achieved": 0, "achievement_pct": 0,
        "daily_data": [],
    }
