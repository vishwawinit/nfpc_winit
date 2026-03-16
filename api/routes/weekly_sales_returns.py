"""Weekly Sales/Return History report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/weekly-sales-returns")
def get_weekly_sales_returns(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer: Optional[str] = None,
    route: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'customer': customer, 'route': route,
    }.items() if v is not None}

    ww, wp = build_where(filters, date_col='trx_date')

    rows = query(
        f"SELECT "
        f"  EXTRACT(ISOYEAR FROM trx_date)::int AS year, "
        f"  EXTRACT(WEEK FROM trx_date)::int AS week_number, "
        f"  MIN(trx_date) AS week_start, "
        f"  MAX(trx_date) AS week_end, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount ELSE 0 END), 0) AS sales_amount, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 4 THEN net_amount ELSE 0 END), 0) AS return_amount "
        f"FROM rpt_sales_detail "
        f"WHERE {ww} "
        f"GROUP BY EXTRACT(ISOYEAR FROM trx_date), EXTRACT(WEEK FROM trx_date) "
        f"ORDER BY year, week_number",
        wp
    )

    weekly_data = []
    for row in rows:
        sales = float(row["sales_amount"])
        returns = float(row["return_amount"])
        weekly_data.append({
            "year": row["year"],
            "week_number": row["week_number"],
            "week_start": str(row["week_start"]),
            "week_end": str(row["week_end"]),
            "sales_amount": sales,
            "return_amount": returns,
            "net_amount": sales - returns,
            "return_pct": round(returns / sales * 100, 2) if sales else 0,
        })

    # Totals
    total_sales = sum(w["sales_amount"] for w in weekly_data)
    total_returns = sum(w["return_amount"] for w in weekly_data)

    return {
        "weekly_data": weekly_data,
        "totals": {
            "total_sales": total_sales,
            "total_returns": total_returns,
            "net_amount": total_sales - total_returns,
            "return_pct": round(total_returns / total_sales * 100, 2) if total_sales else 0,
        },
    }
