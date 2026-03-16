"""Monthly Sales & Stock report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/monthly-sales-stock")
def get_monthly_sales_stock(
    sales_org: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
):
    # Determine MTD and YTD ranges
    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    ytd_start = date(ref_date.year, 1, 1)

    # Build base filters for YTD range (widest window needed)
    base_filters = {k: v for k, v in {
        'sales_org': sales_org, 'brand': brand, 'category': category,
        'date_from': ytd_start, 'date_to': ref_date,
    }.items() if v is not None}

    w, p = build_where(base_filters, date_col='trx_date')

    # Get item x channel breakdown with MTD and YTD amounts from rpt_sales_detail
    rows = query(
        f"""
        SELECT
            item_code,
            item_name,
            channel_name,
            COALESCE(SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END), 0) AS mtd_amount,
            COALESCE(SUM(net_amount), 0) AS ytd_amount
        FROM rpt_sales_detail
        WHERE trx_type = 1 AND {w}
        GROUP BY item_code, item_name, channel_name
        ORDER BY item_name, channel_name
        """,
        [mtd_start, ref_date] + p
    )

    # Pivot: group by item, nest channels
    items_map = {}
    for r in rows:
        key = r["item_code"]
        if key not in items_map:
            items_map[key] = {
                "item_code": r["item_code"],
                "item_name": r["item_name"],
                "channels": {},
            }
        channel = r["channel_name"] or "Unknown"
        items_map[key]["channels"][channel] = {
            "mtd_amount": float(r["mtd_amount"]),
            "ytd_amount": float(r["ytd_amount"]),
        }

    return {
        "items": list(items_map.values()),
    }
