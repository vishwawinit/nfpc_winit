"""Market Sales Performance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/market-sales-performance")
def get_market_sales_performance(
    sales_org: Optional[str] = None,
    year: Optional[int] = None,
):
    cur_year = year or date.today().year
    last_year = cur_year - 1

    base_filters = {k: v for k, v in {'sales_org': sales_org}.items() if v}

    # Monthly sales for current year and last year (Jan-Dec)
    cur_f = {**base_filters, 'date_from': date(cur_year, 1, 1), 'date_to': date(cur_year, 12, 31)}
    cw, cp = build_where(cur_f, date_col='trx_date')

    last_f = {**base_filters, 'date_from': date(last_year, 1, 1), 'date_to': date(last_year, 12, 31)}
    lw, lp = build_where(last_f, date_col='trx_date')

    monthly_cur = query(
        f"SELECT EXTRACT(MONTH FROM trx_date)::int AS month, "
        f"  COALESCE(SUM(net_amount),0) AS sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND {cw} "
        f"GROUP BY EXTRACT(MONTH FROM trx_date) ORDER BY month", cp
    )

    monthly_last = query(
        f"SELECT EXTRACT(MONTH FROM trx_date)::int AS month, "
        f"  COALESCE(SUM(net_amount),0) AS sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND {lw} "
        f"GROUP BY EXTRACT(MONTH FROM trx_date) ORDER BY month", lp
    )

    # Build lookup dicts
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
        growth = round((cs - ls) / ls * 100, 2) if ls else 0
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
