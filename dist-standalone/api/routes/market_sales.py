"""Market Sales Performance report endpoint.
Matches: Usp_GetMarketSalesPerformanceData

Source: rpt_route_sales_summary_by_item DISTINCT ON (route_code, item_code, date) — matches dashboard
Returns: 12 months of sales data with YoY growth.
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()


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

    if user_code == "__NO_MATCH__":
        return _empty()

    cur_year = year or date.today().year
    last_year = cur_year - 1

    base_filters = {k: v for k, v in {'route': route, 'user_code': user_code}.items() if v}

    # rpt_route_sales_summary_by_item has no user_code data — use RSIC when user_code is active
    _use_rsic = bool(user_code)

    if _use_rsic:
        # RSIC path: rpt_route_sales_by_item_customer supports user_code filtering
        org_join = ""
        org_join_params = []
        if sales_org and not route:
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
            org_join_params = orgs

        cur_f = {k: v for k, v in {**base_filters, 'date_from': date(cur_year, 1, 1), 'date_to': date(cur_year, 12, 31)}.items() if v}
        cw, cp = build_where(cur_f, date_col='date', prefix='r')
        monthly_cur = query(
            f"SELECT EXTRACT(MONTH FROM r.date)::int AS month, "
            f"  ROUND(COALESCE(SUM(r.total_sales),0)::numeric, 0) AS sales "
            f"FROM rpt_route_sales_by_item_customer r {org_join}"
            f"WHERE {cw} "
            f"GROUP BY EXTRACT(MONTH FROM r.date) ORDER BY month",
            org_join_params + cp
        )

        last_f = {k: v for k, v in {**base_filters, 'date_from': date(last_year, 1, 1), 'date_to': date(last_year, 12, 31)}.items() if v}
        lw, lp = build_where(last_f, date_col='date', prefix='r')
        monthly_last = query(
            f"SELECT EXTRACT(MONTH FROM r.date)::int AS month, "
            f"  ROUND(COALESCE(SUM(r.total_sales),0)::numeric, 0) AS sales "
            f"FROM rpt_route_sales_by_item_customer r {org_join}"
            f"WHERE {lw} "
            f"GROUP BY EXTRACT(MONTH FROM r.date) ORDER BY month",
            org_join_params + lp
        )
    else:
        # RSSI path — no user_code filter; route/sales_org only
        org_cond = ""
        org_params = []
        if sales_org:
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            org_cond = f" AND sales_org_code IN ({org_ph})"
            org_params = orgs

        cur_f = {k: v for k, v in {**base_filters, 'date_from': date(cur_year, 1, 1), 'date_to': date(cur_year, 12, 31)}.items() if v}
        cw, cp = build_where(cur_f, date_col='date')
        monthly_cur = query(
            f"SELECT EXTRACT(MONTH FROM date)::int AS month, "
            f"  ROUND(COALESCE(SUM(total_sales),0)::numeric, 0) AS sales "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) date, total_sales "
            f"  FROM rpt_route_sales_summary_by_item WHERE {cw}{org_cond} "
            f"  ORDER BY route_code, item_code, date) t "
            f"GROUP BY EXTRACT(MONTH FROM date) ORDER BY month",
            cp + org_params
        )

        last_f = {k: v for k, v in {**base_filters, 'date_from': date(last_year, 1, 1), 'date_to': date(last_year, 12, 31)}.items() if v}
        lw, lp = build_where(last_f, date_col='date')
        monthly_last = query(
            f"SELECT EXTRACT(MONTH FROM date)::int AS month, "
            f"  ROUND(COALESCE(SUM(total_sales),0)::numeric, 0) AS sales "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) date, total_sales "
            f"  FROM rpt_route_sales_summary_by_item WHERE {lw}{org_cond} "
            f"  ORDER BY route_code, item_code, date) t "
            f"GROUP BY EXTRACT(MONTH FROM date) ORDER BY month",
            lp + org_params
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
