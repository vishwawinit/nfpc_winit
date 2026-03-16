"""Revenue Dispersion report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/revenue-dispersion")
def get_revenue_dispersion(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    # Default to current month if no date range provided
    if not date_from:
        today = date.today()
        date_from = date(today.year, today.month, 1)
    if not date_to:
        date_to = date.today()

    filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='trx_date')

    # --- Revenue Dispersion ---
    # First aggregate invoice totals, then bucket them by month
    revenue_dispersion = query(
        f"""
        WITH invoice_totals AS (
            SELECT
                TO_CHAR(trx_date, 'YYYY-MM') AS month,
                trx_code,
                customer_code,
                SUM(net_amount) AS invoice_amount
            FROM rpt_sales_detail
            WHERE trx_type = 1 AND {w}
            GROUP BY TO_CHAR(trx_date, 'YYYY-MM'), trx_code, customer_code
        ),
        bucketed AS (
            SELECT
                month,
                CASE
                    WHEN invoice_amount BETWEEN 0 AND 200 THEN '0-200'
                    WHEN invoice_amount BETWEEN 200.01 AND 500 THEN '200-500'
                    WHEN invoice_amount BETWEEN 500.01 AND 1000 THEN '500-1000'
                    WHEN invoice_amount BETWEEN 1000.01 AND 2500 THEN '1000-2500'
                    WHEN invoice_amount BETWEEN 2500.01 AND 5000 THEN '2500-5000'
                    ELSE '5000+'
                END AS billing_range,
                trx_code,
                customer_code
            FROM invoice_totals
        )
        SELECT
            month,
            billing_range,
            COUNT(DISTINCT trx_code) AS invoice_count,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM bucketed
        GROUP BY month, billing_range
        ORDER BY month,
            CASE billing_range
                WHEN '0-200' THEN 1
                WHEN '200-500' THEN 2
                WHEN '500-1000' THEN 3
                WHEN '1000-2500' THEN 4
                WHEN '2500-5000' THEN 5
                WHEN '5000+' THEN 6
            END
        """,
        p
    )

    # Add percentage per month
    # Group by month and compute total per month
    month_totals = {}
    for r in revenue_dispersion:
        m = r["month"]
        month_totals[m] = month_totals.get(m, 0) + int(r["invoice_count"])

    for r in revenue_dispersion:
        total = month_totals.get(r["month"], 1)
        r["pct"] = round(int(r["invoice_count"]) / total * 100, 2)

    # --- SKU Dispersion ---
    # Count line items per invoice, then bucket
    sku_dispersion = query(
        f"""
        WITH invoice_lines AS (
            SELECT
                TO_CHAR(trx_date, 'YYYY-MM') AS month,
                trx_code,
                customer_code,
                COUNT(DISTINCT item_code) AS line_count
            FROM rpt_sales_detail
            WHERE trx_type = 1 AND {w}
            GROUP BY TO_CHAR(trx_date, 'YYYY-MM'), trx_code, customer_code
        ),
        bucketed AS (
            SELECT
                month,
                CASE
                    WHEN line_count BETWEEN 0 AND 5 THEN '0-5'
                    WHEN line_count BETWEEN 6 AND 10 THEN '5-10'
                    WHEN line_count BETWEEN 11 AND 15 THEN '10-15'
                    WHEN line_count BETWEEN 16 AND 20 THEN '15-20'
                    ELSE '20+'
                END AS sku_range,
                trx_code,
                customer_code
            FROM invoice_lines
        )
        SELECT
            month,
            sku_range,
            COUNT(DISTINCT trx_code) AS invoice_count,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM bucketed
        GROUP BY month, sku_range
        ORDER BY month,
            CASE sku_range
                WHEN '0-5' THEN 1
                WHEN '5-10' THEN 2
                WHEN '10-15' THEN 3
                WHEN '15-20' THEN 4
                WHEN '20+' THEN 5
            END
        """,
        p
    )

    # Add percentage per month for SKU
    sku_month_totals = {}
    for r in sku_dispersion:
        m = r["month"]
        sku_month_totals[m] = sku_month_totals.get(m, 0) + int(r["invoice_count"])

    for r in sku_dispersion:
        total = sku_month_totals.get(r["month"], 1)
        r["pct"] = round(int(r["invoice_count"]) / total * 100, 2)

    return {
        "revenue_dispersion": revenue_dispersion,
        "sku_dispersion": sku_dispersion,
    }
