"""MTD Sales Overview report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/mtd-sales-overview")
def get_mtd_sales_overview(
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    today = date.today()
    d_from = date_from or date(today.year, today.month, 1)
    d_to = date_to or today

    filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': d_from, 'date_to': d_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # --- Header info ---
    vw, vp = build_where(filters, date_col='date')
    header_row = query_one(
        f"SELECT "
        f"  sales_org_code AS depot, "
        f"  user_code, user_name AS salesman, "
        f"  route_code, route_name, "
        f"  ROUND(AVG(CASE WHEN is_productive THEN total_time_mins ELSE NULL END)::numeric, 1) "
        f"    AS avg_productive_mins, "
        f"  ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT date), 0), 1) AS avg_daily_calls "
        f"FROM rpt_customer_visits "
        f"WHERE {vw} "
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

    # --- Daily data: sales by day with target ---
    sw, sp = build_where(filters, date_col='trx_date')
    daily_sales = query(
        f"SELECT "
        f"  trx_date AS sale_date, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '1' THEN net_amount ELSE 0 END), 0) AS cash_sales, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '0' THEN net_amount ELSE 0 END), 0) AS credit_sales, "
        f"  COALESCE(SUM(net_amount), 0) AS total_sales "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND {sw} "
        f"GROUP BY trx_date "
        f"ORDER BY trx_date",
        sp
    )

    # Get monthly target and compute daily target
    target_filters = {k: v for k, v in {
        'sales_org': sales_org, 'route': route, 'user_code': user_code,
    }.items() if v is not None}
    tf = {**target_filters, 'date_from': d_from, 'date_to': d_to}
    tf = {k: v for k, v in tf.items() if v is not None}
    tw, tp = build_where(tf, date_col='start_date')
    target_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS monthly_target "
        f"FROM rpt_targets WHERE is_active = true AND {tw}",
        tp
    )
    monthly_target = float(target_row["monthly_target"]) if target_row else 0

    # Count working days in the month (approximation: weekdays)
    month_start = date(d_from.year, d_from.month, 1)
    if d_from.month == 12:
        month_end = date(d_from.year, 12, 31)
    else:
        month_end = date(d_from.year, d_from.month + 1, 1) - timedelta(days=1)

    working_days = sum(
        1 for i in range((month_end - month_start).days + 1)
        if (month_start + timedelta(days=i)).weekday() < 6  # Mon-Sat
    )
    daily_target = monthly_target / working_days if working_days else 0

    # Build daily data
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    cumulative_sales = 0
    cumulative_target = 0

    daily_data = []
    for row in daily_sales:
        d = row["sale_date"]
        cash = float(row["cash_sales"])
        credit = float(row["credit_sales"])
        total = float(row["total_sales"])
        cumulative_sales += total
        cumulative_target += daily_target

        daily_var = total - daily_target
        daily_var_pct = round(daily_var / daily_target * 100, 2) if daily_target else 0

        daily_data.append({
            "date": str(d),
            "day_name": DAY_NAMES[d.weekday()] if hasattr(d, 'weekday') else "",
            "cash_sales": cash,
            "credit_sales": credit,
            "total_sales": total,
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
