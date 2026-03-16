"""Top Products report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/top-products")
def get_top_products(
    customer: Optional[str] = None,
    user_code: Optional[str] = None,
    sales_org: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
):
    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month

    # Current period
    cur_start = date(cur_year, cur_month, 1)
    if cur_month == 12:
        cur_end = date(cur_year, 12, 31)
    else:
        cur_end = date(cur_year, cur_month + 1, 1) - timedelta(days=1)

    # Prior period (previous month)
    if cur_month == 1:
        prev_start = date(cur_year - 1, 12, 1)
        prev_end = date(cur_year - 1, 12, 31)
    else:
        prev_start = date(cur_year, cur_month - 1, 1)
        prev_end = cur_start - timedelta(days=1)

    base_filters = {k: v for k, v in {
        'customer': customer, 'user_code': user_code, 'sales_org': sales_org,
    }.items() if v}

    # Build WHERE for current period
    cur_filters = {**base_filters, 'date_from': cur_start, 'date_to': cur_end}
    cw, cp = build_where(cur_filters, date_col='trx_date')

    # Build WHERE for prior period
    prev_filters = {**base_filters, 'date_from': prev_start, 'date_to': prev_end}
    pw, pp = build_where(prev_filters, date_col='trx_date')

    rows = query(
        f"SELECT "
        f"  item_code, item_name, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END) AS total_sales, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN qty_cases ELSE 0 END) AS total_qty, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END) AS prev_sales "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND (({cw}) OR ({pw})) "
        f"GROUP BY item_code, item_name "
        f"ORDER BY total_sales DESC "
        f"LIMIT 20",
        [cur_start, cur_end, cur_start, cur_end, prev_start, prev_end] + cp + pp
    )

    for row in rows:
        cur_s = float(row.get("total_sales") or 0)
        prev_s = float(row.get("prev_sales") or 0)
        row["growth_pct"] = round((cur_s - prev_s) / prev_s * 100, 2) if prev_s else 0
        row.pop("prev_sales", None)

    return {"data": rows}
