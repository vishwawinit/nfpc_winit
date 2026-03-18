"""Market Sales Performance report endpoint.
Matches: Usp_GetMarketSalesPerformanceData

Source: rpt_route_sales_by_item_customer (monthly aggregation, current vs last year)
Returns: 12 months of sales data with YoY growth.
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/market-sales-performance")
def get_market_sales_performance(
    sales_org: Optional[str] = None,
    year: Optional[int] = None,
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy
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

    cur_year = year or date.today().year
    last_year = cur_year - 1

    base_filters = {k: v for k, v in {'route': route, 'user_code': user_code}.items() if v}

    # Resolve sales_org to user_codes
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        if org_rows:
            org_users = set(r['code'] for r in org_rows)
            if base_filters.get('user_code'):
                existing = set(base_filters['user_code'].split(','))
                intersected = existing & org_users
                if not intersected:
                    return _empty()
                base_filters['user_code'] = ','.join(intersected)
            else:
                base_filters['user_code'] = ','.join(org_users)

    # Current year: monthly from rpt_route_sales_by_item_customer
    cur_f = {**base_filters, 'date_from': date(cur_year, 1, 1), 'date_to': date(cur_year, 12, 31)}
    f_rsic = {k: v for k, v in cur_f.items() if k in RSIC_KEYS}
    cw, cp = build_where(f_rsic, date_col='date')
    monthly_cur = query(
        f"SELECT EXTRACT(MONTH FROM date)::int AS month, "
        f"  ROUND(COALESCE(SUM(total_sales),0)::numeric, 0) AS sales "
        f"FROM rpt_route_sales_by_item_customer WHERE {cw} "
        f"GROUP BY EXTRACT(MONTH FROM date) ORDER BY month", cp
    )

    # Last year
    last_f = {**base_filters, 'date_from': date(last_year, 1, 1), 'date_to': date(last_year, 12, 31)}
    f_rsic_l = {k: v for k, v in last_f.items() if k in RSIC_KEYS}
    lw, lp = build_where(f_rsic_l, date_col='date')
    monthly_last = query(
        f"SELECT EXTRACT(MONTH FROM date)::int AS month, "
        f"  ROUND(COALESCE(SUM(total_sales),0)::numeric, 0) AS sales "
        f"FROM rpt_route_sales_by_item_customer WHERE {lw} "
        f"GROUP BY EXTRACT(MONTH FROM date) ORDER BY month", lp
    )

    cur_map = {int(r["month"]): float(r["sales"]) for r in monthly_cur}
    last_map = {int(r["month"]): float(r["sales"]) for r in monthly_last}

    monthly_data = []
    ytd_current = 0
    ytd_last = 0
    today = date.today()
    ytd_month = today.month if cur_year == today.year else 12

    for m in range(1, 13):
        cs = cur_map.get(m, 0)
        ls = last_map.get(m, 0)
        if ls == 0 and cs == 0:
            growth = 0
        elif ls == 0:
            growth = 100
        else:
            growth = round((cs - ls) / ls * 100, 2)
        monthly_data.append({
            "month": m,
            "current_year_sales": cs,
            "last_year_sales": ls,
            "growth_pct": growth,
        })
        if m <= ytd_month:
            ytd_current += cs
            ytd_last += ls

    ytd_growth = round((ytd_current - ytd_last) / ytd_last * 100, 2) if ytd_last else 0

    return {
        "monthly_data": monthly_data,
        "ytd_current": ytd_current,
        "ytd_last": ytd_last,
        "ytd_growth": ytd_growth,
    }


def _empty():
    return {
        "monthly_data": [{"month": m, "current_year_sales": 0, "last_year_sales": 0, "growth_pct": 0} for m in range(1, 13)],
        "ytd_current": 0, "ytd_last": 0, "ytd_growth": 0,
    }
