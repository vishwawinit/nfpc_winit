"""Revenue Dispersion report endpoint.
Revenue: bucket customers by total billing amount range (per month)
SKU: bucket customers by distinct item count (per month)

Source: rpt_route_sales_by_item_customer (fast, pre-aggregated)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/revenue-dispersion")
def get_revenue_dispersion(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
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

    if not date_from:
        today = date.today()
        date_from = date(today.year, today.month, 1)
    if not date_to:
        date_to = date.today()

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}

    # Resolve sales_org
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs)
        if org_rows:
            org_users = set(r['code'] for r in org_rows)
            if base_filters.get('user_code'):
                intersected = set(base_filters['user_code'].split(',')) & org_users
                if not intersected:
                    return _empty()
                base_filters['user_code'] = ','.join(intersected)
            else:
                base_filters['user_code'] = ','.join(org_users)

    f_rsic = {k: v for k, v in base_filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    # --- Revenue Dispersion ---
    # Aggregate total_sales per customer per month, then bucket by amount range
    revenue_dispersion = query(
        f"""
        WITH customer_totals AS (
            SELECT TO_CHAR(r.date, 'YYYY-MM') AS month,
                r.customer_code,
                SUM(r.total_sales) AS total_amount
            FROM rpt_route_sales_by_item_customer r
            WHERE {rw}
            GROUP BY TO_CHAR(r.date, 'YYYY-MM'), r.customer_code
        ),
        bucketed AS (
            SELECT month, customer_code,
                CASE
                    WHEN total_amount BETWEEN 0 AND 200 THEN '0-200'
                    WHEN total_amount BETWEEN 200.01 AND 500 THEN '200-500'
                    WHEN total_amount BETWEEN 500.01 AND 1000 THEN '500-1000'
                    WHEN total_amount BETWEEN 1000.01 AND 2500 THEN '1000-2500'
                    WHEN total_amount BETWEEN 2500.01 AND 5000 THEN '2500-5000'
                    ELSE '5000+'
                END AS billing_range
            FROM customer_totals
            WHERE total_amount >= 0
        )
        SELECT month, billing_range,
            COUNT(*) AS invoice_count,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM bucketed
        GROUP BY month, billing_range
        ORDER BY month,
            CASE billing_range
                WHEN '0-200' THEN 1 WHEN '200-500' THEN 2 WHEN '500-1000' THEN 3
                WHEN '1000-2500' THEN 4 WHEN '2500-5000' THEN 5 WHEN '5000+' THEN 6
            END
        """,
        rp
    )

    month_totals = {}
    for r in revenue_dispersion:
        m = r["month"]
        month_totals[m] = month_totals.get(m, 0) + int(r["invoice_count"])
    for r in revenue_dispersion:
        total = month_totals.get(r["month"], 1)
        r["pct"] = round(int(r["invoice_count"]) / total * 100, 2)

    # --- SKU Dispersion ---
    # Count distinct items per customer per month, then bucket
    sku_dispersion = query(
        f"""
        WITH customer_items AS (
            SELECT TO_CHAR(r.date, 'YYYY-MM') AS month,
                r.customer_code,
                COUNT(DISTINCT r.item_code) AS item_count
            FROM rpt_route_sales_by_item_customer r
            WHERE r.total_sales >= 0 AND {rw}
            GROUP BY TO_CHAR(r.date, 'YYYY-MM'), r.customer_code
        ),
        bucketed AS (
            SELECT month, customer_code,
                CASE
                    WHEN item_count BETWEEN 0 AND 5 THEN '0-5'
                    WHEN item_count BETWEEN 6 AND 10 THEN '5-10'
                    WHEN item_count BETWEEN 11 AND 15 THEN '10-15'
                    WHEN item_count BETWEEN 16 AND 20 THEN '15-20'
                    ELSE '20+'
                END AS sku_range
            FROM customer_items
        )
        SELECT month, sku_range,
            COUNT(*) AS invoice_count,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM bucketed
        GROUP BY month, sku_range
        ORDER BY month,
            CASE sku_range
                WHEN '0-5' THEN 1 WHEN '5-10' THEN 2 WHEN '10-15' THEN 3
                WHEN '15-20' THEN 4 WHEN '20+' THEN 5
            END
        """,
        rp
    )

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


def _empty():
    return {"revenue_dispersion": [], "sku_dispersion": []}
