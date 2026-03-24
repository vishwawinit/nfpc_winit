"""Revenue Dispersion report endpoint.
Revenue: bucket customers by net billing amount range (per month)
SKU: bucket customers by distinct item count (per month)

Source: rpt_sales_detail — same as daily_sales_overview, so invoice/customer counts match.
Returns: current month + previous month + YTD for comparison.
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
import calendar as cal
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()

SD_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


def _bucket_pct(rows):
    """Compute % of total customers per month for each bucket row."""
    totals = {}
    for r in rows:
        m = r["month"]
        totals[m] = totals.get(m, 0) + int(r["customer_count"])
    for r in rows:
        total = totals.get(r["month"], 1)
        r["pct"] = round(int(r["customer_count"]) / total * 100, 2)
    return rows


def _where_sd(filters, sales_org=None, period_label=None):
    """Build WHERE clause and params for rpt_sales_detail (alias sd)."""
    f = {k: v for k, v in filters.items() if k in SD_KEYS}
    rw, rp = build_where(f, date_col='trx_date', prefix='sd')
    # Always filter completed transactions
    rw = rw + " AND sd.trx_status = 200"
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        ph = ','.join(['%s'] * len(orgs))
        rw += f" AND sd.sales_org_code IN ({ph})"
        rp = rp + orgs
    return rw, rp


def _run_revenue_query(filters, sales_org, period_label=None):
    rw, rp = _where_sd(filters, sales_org, period_label)
    if period_label:
        month_select = f"'{period_label}' AS month"
        month_group = ""
    else:
        month_select = "TO_CHAR(sd.trx_date, 'YYYY-MM') AS month"
        month_group = "TO_CHAR(sd.trx_date, 'YYYY-MM'),"
    return query(
        f"""
        WITH customer_totals AS (
            SELECT {month_select},
                sd.customer_code,
                COUNT(DISTINCT sd.trx_code) AS invoice_count,
                SUM(sd.net_amount) AS total_amount
            FROM rpt_sales_detail sd
            WHERE {rw}
            GROUP BY {month_group} sd.customer_code
        ),
        bucketed AS (
            SELECT month, customer_code, invoice_count,
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
            SUM(invoice_count) AS invoice_count,
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


def _run_sku_query(filters, sales_org, period_label=None):
    rw, rp = _where_sd(filters, sales_org, period_label)
    if period_label:
        month_select = f"'{period_label}' AS month"
        month_group = ""
    else:
        month_select = "TO_CHAR(sd.trx_date, 'YYYY-MM') AS month"
        month_group = "TO_CHAR(sd.trx_date, 'YYYY-MM'),"
    return query(
        f"""
        WITH customer_items AS (
            SELECT {month_select},
                sd.customer_code,
                COUNT(DISTINCT sd.item_code) AS item_count,
                COUNT(DISTINCT sd.trx_code) AS invoice_count
            FROM rpt_sales_detail sd
            WHERE sd.net_amount >= 0 AND {rw}
            GROUP BY {month_group} sd.customer_code
        ),
        bucketed AS (
            SELECT month, customer_code, invoice_count,
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
            SUM(invoice_count) AS invoice_count,
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


def _make_filters(route, user_code, date_from, date_to):
    return {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}


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
    prev_month_last_day = cal.monthrange(prev_year, prev_month_num)[1]
    prev_month_end = date(prev_year, prev_month_num, prev_month_last_day)

    # YTD: Jan 1 of selected year to date_to
    ytd_start = date(date_from.year, 1, 1)

    curr_f = _make_filters(route, user_code, date_from, date_to)
    prev_f = _make_filters(route, user_code, prev_month_start, prev_month_end)
    ytd_f  = _make_filters(route, user_code, ytd_start, date_to)

    # Revenue dispersion
    rev_curr = _run_revenue_query(curr_f, sales_org)
    rev_prev = _run_revenue_query(prev_f, sales_org)
    rev_ytd  = _run_revenue_query(ytd_f,  sales_org, period_label='YTD')
    revenue_dispersion = _bucket_pct(rev_curr + rev_prev + rev_ytd)

    # SKU dispersion
    sku_curr = _run_sku_query(curr_f, sales_org)
    sku_prev = _run_sku_query(prev_f, sales_org)
    sku_ytd  = _run_sku_query(ytd_f,  sales_org, period_label='YTD')
    sku_dispersion = _bucket_pct(sku_curr + sku_prev + sku_ytd)

    return {
        "revenue_dispersion": revenue_dispersion,
        "sku_dispersion": sku_dispersion,
        "selected_month": selected_month,
        "prev_month": prev_month_start.strftime('%Y-%m'),
    }
