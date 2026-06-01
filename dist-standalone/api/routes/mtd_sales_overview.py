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

    # Resolve sales_org to route JOIN for RSIC tables (no sales_org_code column)
    _org_join = ""
    _org_params = []
    if sales_org and not base_filters.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _org_params = orgs

    # Channel filter — EXISTS on dim_customer (avoids row multiplication)
    channel_cond = ""
    channel_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        channel_cond = (
            f" AND EXISTS (SELECT 1 FROM dim_customer _chdc "
            f"  WHERE _chdc.code = r.customer_code AND TRIM(_chdc.channel_code) IN ({ch_ph}))"
        )
        channel_params = ch_vals

    # Brand/Category — JOIN dim_item (avoids item-code format mismatch with RSIC)
    brand_dim_join = ""
    brand_dim_join_params = []
    if brand or category:
        i_conds, i_params = [], []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            i_conds.append(f"TRIM(_di.brand_code) IN ({','.join(['%s'] * len(b_vals))})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            i_conds.append(f"_di.category_code IN ({','.join(['%s'] * len(c_vals))})")
            i_params.extend(c_vals)
        brand_dim_join = f"JOIN dim_item _di ON _di.code = r.item_code AND {' AND '.join(i_conds)} "
        brand_dim_join_params = i_params

    # Use RSIC when channel/brand/category filter active (summary table lacks these columns)
    _use_rsic = bool(channel or brand or category)

    filters = {**base_filters, 'date_from': d_from, 'date_to': d_to}

    # --- Header info from rpt_customer_visits ---
    hdr_filters = {k: v for k, v in filters.items() if k in COVERAGE_KEYS | {'date_from', 'date_to', 'sales_org'}}
    vw, vp = build_where(hdr_filters, date_col='date')
    header_row = query_one(
        f"SELECT "
        f"  ROUND(AVG(CASE WHEN is_productive THEN total_time_mins ELSE NULL END)::numeric, 0) AS avg_productive_mins, "
        f"  ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT date), 0), 1) AS avg_daily_calls "
        f"FROM rpt_customer_visits WHERE {vw}",
        vp
    )
    first_row = query_one(
        f"SELECT sales_org_code AS depot, user_code, user_name AS salesman, "
        f"  route_code, route_name "
        f"FROM rpt_customer_visits WHERE {vw} LIMIT 1",
        vp
    )
    header = {}
    if header_row:
        header = {
            "depot": first_row["depot"] if first_row else "",
            "user_code": first_row["user_code"] if first_row else "",
            "salesman": first_row["salesman"] if first_row else "",
            "route_code": first_row["route_code"] if first_row else "",
            "route_name": first_row["route_name"] if first_row else "",
            "avg_productive_mins": float(header_row["avg_productive_mins"]) if header_row["avg_productive_mins"] else 0,
            "avg_daily_calls": float(header_row["avg_daily_calls"]) if header_row["avg_daily_calls"] else 0,
        }

    # --- Daily Sales total ---
    # No filter: summary table with DISTINCT ON (matches dashboard)
    # Filter active: RSIC with JOIN dim_item / EXISTS dim_customer
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rsw, rsp = build_where(f_rsic, date_col='date', prefix='r')

    if not _use_rsic:
        f_rssi = {k: v for k, v in {
            'route': route, 'user_code': user_code,
            'date_from': d_from, 'date_to': d_to,
        }.items() if v is not None}
        sw_s, sp_s = build_where(f_rssi, date_col='date')
        org_cond_s = ""
        org_params_s = []
        if sales_org:
            orgs_s = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph_s = ','.join(['%s'] * len(orgs_s))
            org_cond_s = f" AND sales_org_code IN ({org_ph_s})"
            org_params_s = orgs_s
        daily_summary = query(
            f"SELECT date AS sale_date, COALESCE(SUM(total_sales), 0) AS total_sales "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) date, total_sales "
            f"  FROM rpt_route_sales_summary_by_item WHERE {sw_s}{org_cond_s} "
            f"  ORDER BY route_code, item_code, date) t "
            f"GROUP BY date ORDER BY date",
            sp_s + org_params_s
        )
    else:
        daily_summary = query(
            f"SELECT r.date AS sale_date, COALESCE(SUM(r.total_sales), 0) AS total_sales "
            f"FROM rpt_route_sales_by_item_customer r {_org_join}{brand_dim_join}"
            f"WHERE {rsw}{channel_cond} "
            f"GROUP BY r.date ORDER BY r.date",
            _org_params + brand_dim_join_params + rsp + channel_params
        )
    summary_map = {str(r["sale_date"]): round(float(r["total_sales"]), 2) for r in daily_summary}

    # --- Cash/Credit split from RSIC + dim_customer.customer_type ---
    # Uses DISTINCT ON dim_customer to avoid row multiplication from multi-org customers
    daily_cc = query(
        f"SELECT r.date AS sale_date, "
        f"  COALESCE(SUM(CASE WHEN dc.customer_type = 'Cash' THEN r.total_sales ELSE 0 END), 0) AS cash_sales, "
        f"  COALESCE(SUM(CASE WHEN dc.customer_type = 'Credit' THEN r.total_sales ELSE 0 END), 0) AS credit_sales "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN (SELECT DISTINCT ON (code) code, customer_type FROM dim_customer ORDER BY code) dc ON dc.code = r.customer_code "
        f"{_org_join}{brand_dim_join}"
        f"WHERE {rsw}{channel_cond} "
        f"GROUP BY r.date ORDER BY r.date",
        _org_params + brand_dim_join_params + rsp + channel_params
    )
    cc_map = {
        str(r["sale_date"]): (round(float(r["cash_sales"]), 2), round(float(r["credit_sales"]), 2))
        for r in daily_cc
    }

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

    all_dates = sorted(set(list(summary_map.keys()) + list(cc_map.keys())))
    daily_data = []
    for d_str in all_dates:
        d_obj = date.fromisoformat(d_str)
        total = summary_map.get(d_str, 0)
        cash, credit = cc_map.get(d_str, (0, 0))

        daily_var = total - daily_target
        daily_var_pct = round(daily_var / daily_target * 100, 2) if daily_target else 0

        daily_data.append({
            "date": d_str,
            "day_name": DAY_NAMES[d_obj.weekday()],
            "cash_sales": round(cash, 2),
            "credit_sales": round(credit, 2),
            "bill_to_bill_sales": 0,
            "total_sales": round(total, 2),
            "target": round(daily_target, 2),
            "daily_var": round(daily_var, 2),
            "daily_var_pct": daily_var_pct,
        })

    total_achieved = sum(d["total_sales"] for d in daily_data)
    return {
        "header": header,
        "monthly_target": monthly_target,
        "daily_target": round(daily_target, 2),
        "total_achieved": round(total_achieved, 2),
        "achievement_pct": round(total_achieved / monthly_target * 100, 2) if monthly_target else 0,
        "daily_data": daily_data,
    }


def _empty():
    return {
        "header": {},
        "monthly_target": 0, "daily_target": 0,
        "total_achieved": 0, "achievement_pct": 0,
        "daily_data": [],
    }
