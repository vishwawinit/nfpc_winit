"""Revenue Dispersion — optimized single-pass approach.

Revenue: bucket customers by net billing amount range.
SKU: bucket customers by distinct item count.

Strategy: 2 parallel queries (revenue + SKU), each scanning rpt_sales_detail
ONCE from ytd_start to date_to. SQL UNION combines monthly + YTD in a single pass.
Previously made 6 separate CTE queries → now 2 parallel queries.
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
import calendar as cal
from concurrent.futures import ThreadPoolExecutor, as_completed
from api.database import query
from api.models import resolve_user_codes

router = APIRouter()

REVENUE_ORDER = ['0-200', '200-500', '500-1000', '1000-2500', '2500-5000', '5000+']
SKU_ORDER = ['0-5', '5-10', '10-15', '15-20', '20+']


def _build_where(route, user_code, ytd_start, date_to, sales_org):
    """Single WHERE covering ytd_start→date_to with all filters."""
    conditions = ["trx_date >= %s", "trx_date <= %s", "trx_type IN (1, 4)", "trx_status = 200"]
    params = [ytd_start, date_to]
    if user_code == "__NO_MATCH__":
        conditions.append("1=0")
    elif user_code:
        u_vals = [v.strip() for v in user_code.split(',') if v.strip()]
        conditions.append(f"user_code IN ({','.join(['%s']*len(u_vals))})")
        params.extend(u_vals)
    if route:
        r_vals = [v.strip() for v in route.split(',') if v.strip()]
        conditions.append(f"route_code IN ({','.join(['%s']*len(r_vals))})")
        params.extend(r_vals)
    if sales_org:
        o_vals = [v.strip() for v in sales_org.split(',') if v.strip()]
        conditions.append(f"sales_org_code IN ({','.join(['%s']*len(o_vals))})")
        params.extend(o_vals)
    return ' AND '.join(conditions), params


def _run_revenue(whr, params):
    """Revenue dispersion — one scan, monthly + YTD via UNION."""
    return query(
        f"""
        WITH customer_totals AS (
            SELECT
                TO_CHAR(trx_date, 'YYYY-MM') AS month,
                customer_code,
                COUNT(DISTINCT trx_code) AS invoice_count,
                SUM(net_amount) AS total_amount
            FROM rpt_sales_detail
            WHERE {whr}
            GROUP BY TO_CHAR(trx_date, 'YYYY-MM'), customer_code
        ),
        bucketed AS (
            SELECT month, customer_code, invoice_count,
                CASE
                    WHEN total_amount BETWEEN 0 AND 200       THEN '0-200'
                    WHEN total_amount BETWEEN 200.01 AND 500  THEN '200-500'
                    WHEN total_amount BETWEEN 500.01 AND 1000 THEN '500-1000'
                    WHEN total_amount BETWEEN 1000.01 AND 2500 THEN '1000-2500'
                    WHEN total_amount BETWEEN 2500.01 AND 5000 THEN '2500-5000'
                    ELSE '5000+'
                END AS billing_range
            FROM customer_totals
            WHERE total_amount >= 0
        ),
        monthly_agg AS (
            SELECT month, billing_range,
                SUM(invoice_count)::int       AS invoice_count,
                COUNT(DISTINCT customer_code) AS customer_count
            FROM bucketed GROUP BY month, billing_range
        ),
        ytd_agg AS (
            SELECT 'YTD' AS month, billing_range,
                SUM(invoice_count)::int       AS invoice_count,
                COUNT(DISTINCT customer_code) AS customer_count
            FROM bucketed GROUP BY billing_range
        )
        SELECT month, billing_range, invoice_count, customer_count FROM monthly_agg
        UNION ALL
        SELECT month, billing_range, invoice_count, customer_count FROM ytd_agg
        """,
        params
    )


def _run_sku(whr, params):
    """SKU dispersion — one scan, monthly + YTD via UNION."""
    return query(
        f"""
        WITH customer_items AS (
            SELECT
                TO_CHAR(trx_date, 'YYYY-MM') AS month,
                customer_code,
                COUNT(DISTINCT trx_code)  AS invoice_count,
                COUNT(DISTINCT item_code) AS item_count
            FROM rpt_sales_detail
            WHERE {whr} AND net_amount >= 0
            GROUP BY TO_CHAR(trx_date, 'YYYY-MM'), customer_code
        ),
        bucketed AS (
            SELECT month, customer_code, invoice_count,
                CASE
                    WHEN item_count BETWEEN 0  AND 5  THEN '0-5'
                    WHEN item_count BETWEEN 6  AND 10 THEN '5-10'
                    WHEN item_count BETWEEN 11 AND 15 THEN '10-15'
                    WHEN item_count BETWEEN 16 AND 20 THEN '15-20'
                    ELSE '20+'
                END AS sku_range
            FROM customer_items
        ),
        monthly_agg AS (
            SELECT month, sku_range,
                SUM(invoice_count)::int       AS invoice_count,
                COUNT(DISTINCT customer_code) AS customer_count
            FROM bucketed GROUP BY month, sku_range
        ),
        ytd_agg AS (
            SELECT 'YTD' AS month, sku_range,
                SUM(invoice_count)::int       AS invoice_count,
                COUNT(DISTINCT customer_code) AS customer_count
            FROM bucketed GROUP BY sku_range
        )
        SELECT month, sku_range, invoice_count, customer_count FROM monthly_agg
        UNION ALL
        SELECT month, sku_range, invoice_count, customer_count FROM ytd_agg
        """,
        params
    )


def _bucket_pct(rows, range_key):
    totals = {}
    for r in rows:
        m = r["month"]
        totals[m] = totals.get(m, 0) + int(r["customer_count"])
    for r in rows:
        total = totals.get(r["month"], 1)
        r["pct"] = round(int(r["customer_count"]) / total * 100, 2)
    return rows


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

    selected_month = date_from.strftime('%Y-%m')

    # Previous calendar month
    if date_from.month == 1:
        prev_year, prev_month_num = date_from.year - 1, 12
    else:
        prev_year, prev_month_num = date_from.year, date_from.month - 1
    prev_month_start = date(prev_year, prev_month_num, 1)
    prev_month_str = prev_month_start.strftime('%Y-%m')

    # YTD start: Jan 1 of selected year
    ytd_start = date(date_from.year, 1, 1)

    # Single WHERE covering full range ytd_start → date_to
    whr, wparams = _build_where(route, user_code, ytd_start, date_to, sales_org)

    # Run revenue + SKU in parallel — 2 queries instead of 6
    with ThreadPoolExecutor(max_workers=2) as ex:
        rev_future = ex.submit(_run_revenue, whr, wparams)
        sku_future = ex.submit(_run_sku, whr, wparams)
        all_rev = rev_future.result()
        all_sku = sku_future.result()

    # Filter to curr / prev / YTD (YTD rows already labelled 'YTD' by SQL)
    rev_rows = [r for r in all_rev if r['month'] in (selected_month, prev_month_str, 'YTD')]
    sku_rows = [r for r in all_sku if r['month'] in (selected_month, prev_month_str, 'YTD')]

    return {
        "revenue_dispersion": _bucket_pct(rev_rows, 'billing_range'),
        "sku_dispersion": _bucket_pct(sku_rows, 'sku_range'),
        "selected_month": selected_month,
        "prev_month": prev_month_str,
    }
