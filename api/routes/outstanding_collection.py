"""Outstanding Collection report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


def _build_outstanding_where(filters: dict):
    """Build WHERE for rpt_outstanding which has org_code instead of sales_org_code."""
    conditions = []
    params = []
    if filters.get('sales_org'):
        conditions.append("org_code = %s")
        params.append(filters['sales_org'])
    if filters.get('customer'):
        conditions.append("customer_code = %s")
        params.append(filters['customer'])
    if filters.get('user_code'):
        conditions.append("user_code = %s")
        params.append(filters['user_code'])
    if filters.get('route'):
        conditions.append("route_code = %s")
        params.append(filters['route'])
    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


@router.get("/outstanding-collection")
def get_outstanding_collection(
    customer: Optional[str] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    bucket: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route,
    }.items() if v is not None}

    w, p = _build_outstanding_where(filters)

    # Aging buckets
    aging_buckets = query(
        f"""
        SELECT
            aging_bucket AS bucket,
            COALESCE(SUM(balance_amount), 0) AS amount,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM rpt_outstanding
        WHERE balance_amount > 0 AND {w}
        GROUP BY aging_bucket
        ORDER BY
            CASE aging_bucket
                WHEN 'Current' THEN 1
                WHEN '1-30' THEN 2
                WHEN '31-60' THEN 3
                WHEN '61-90' THEN 4
                WHEN '91-120' THEN 5
                WHEN '120+' THEN 6
                ELSE 7
            END
        """,
        p
    )

    # Customer-level detail, optionally filtered by bucket
    bucket_cond = ""
    bucket_params = []
    if bucket:
        bucket_cond = " AND aging_bucket = %s"
        bucket_params = [bucket]

    customers = query(
        f"""
        SELECT
            customer_code,
            customer_name,
            COUNT(DISTINCT trx_code) AS invoice_count,
            COALESCE(SUM(balance_amount), 0) AS pending_amount
        FROM rpt_outstanding
        WHERE balance_amount > 0 AND {w}{bucket_cond}
        GROUP BY customer_code, customer_name
        ORDER BY pending_amount DESC
        LIMIT 100
        """,
        p + bucket_params
    )

    return {
        "aging_buckets": aging_buckets,
        "customers": customers,
    }


@router.get("/outstanding-collection/invoices")
def get_outstanding_invoices(
    customer: str = Query(..., description="Customer code"),
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    route: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route,
    }.items() if v is not None}

    w, p = _build_outstanding_where(filters)

    invoices = query(
        f"""
        SELECT
            trx_code,
            trx_date,
            due_date,
            original_amount,
            balance_amount,
            pending_amount,
            collected_amount,
            days_overdue,
            aging_bucket,
            user_code,
            user_name,
            route_code,
            route_name
        FROM rpt_outstanding
        WHERE {w}
        ORDER BY trx_date DESC
        LIMIT 200
        """,
        p
    )

    return invoices
