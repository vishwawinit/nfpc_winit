"""MTD Wastage Summary report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/mtd-wastage-summary")
def get_mtd_wastage_summary(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'route': route, 'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org, 'user_code': user_code,
    }.items() if v is not None}

    ww, wp = build_where(filters, date_col='trx_date')

    # --- Summary totals ---
    summary_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(CASE WHEN trx_type = 4 THEN qty_cases ELSE 0 END), 0) AS total_returns_qty, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 4 THEN net_amount ELSE 0 END), 0) AS total_returns, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount ELSE 0 END), 0) AS total_sales "
        f"FROM rpt_sales_detail WHERE {ww}",
        wp
    )

    total_returns_qty = float(summary_row["total_returns_qty"]) if summary_row else 0
    total_returns = float(summary_row["total_returns"]) if summary_row else 0
    total_sales = float(summary_row["total_sales"]) if summary_row else 0
    total_pct = round(total_returns / total_sales * 100, 2) if total_sales else 0

    summary = {
        "total_qty": total_returns_qty,
        "total_pct": total_pct,
        "total_expired_value": 0,
        "total_damaged_value": 0,
        "total_wastage_value": total_returns,
        "total_sales": total_sales,
        "damaged_pct": 0,
    }

    # --- Customer-level breakdown ---
    details = query(
        f"SELECT "
        f"  customer_code, customer_name, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 4 THEN qty_cases ELSE 0 END), 0) AS qty, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 4 THEN net_amount ELSE 0 END), 0) AS returns_value, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount ELSE 0 END), 0) AS cust_total_sales "
        f"FROM rpt_sales_detail "
        f"WHERE {ww} "
        f"GROUP BY customer_code, customer_name "
        f"HAVING SUM(CASE WHEN trx_type = 4 THEN qty_cases ELSE 0 END) > 0 "
        f"ORDER BY qty DESC",
        wp
    )

    detail_list = []
    for row in details:
        qty = float(row["qty"])
        returns_v = float(row["returns_value"])
        cust_sales = float(row["cust_total_sales"])
        pct = round(returns_v / cust_sales * 100, 2) if cust_sales else 0
        detail_list.append({
            "customer_code": row["customer_code"],
            "customer_name": row["customer_name"],
            "qty": qty,
            "pct": pct,
            "expired_value": 0,
            "damaged_value": returns_v,
        })

    return {
        "summary": summary,
        "details": detail_list,
    }
