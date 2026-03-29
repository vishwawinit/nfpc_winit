"""Outstanding Collection report endpoint.
Source: rpt_outstanding (pending invoices with aging buckets)
"""
from fastapi import APIRouter, Query
from typing import Optional
from api.database import query
from api.models import resolve_user_codes

router = APIRouter()


def _build_where(filters: dict):
    conditions = ["balance_amount != 0"]
    params = []
    if filters.get('year'):
        conditions.append("EXTRACT(YEAR FROM trx_date) = %s")
        params.append(int(filters['year']))
    if filters.get('sales_org'):
        vals = [v.strip() for v in filters['sales_org'].split(',') if v.strip()]
        ph = ','.join(['%s'] * len(vals))
        conditions.append(f"org_code IN ({ph})")
        params.extend(vals)
    if filters.get('customer'):
        conditions.append("customer_code = %s")
        params.append(filters['customer'])
    if filters.get('user_code'):
        vals = [v.strip() for v in filters['user_code'].split(',') if v.strip()]
        ph = ','.join(['%s'] * len(vals))
        conditions.append(f"user_code IN ({ph})")
        params.extend(vals)
    if filters.get('route'):
        conditions.append("route_code = %s")
        params.append(filters['route'])
    return " AND ".join(conditions), params


@router.get("/outstanding-collection")
def get_outstanding_collection(
    customer: Optional[str] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    bucket: Optional[str] = None,
    year: Optional[int] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return {"aging_buckets": [], "customers": []}
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route, 'year': year,
    }.items() if v is not None}

    w, p = _build_where(filters)

    # Aging buckets — computed from days_overdue
    _bucket_expr = (
        "CASE "
        "WHEN days_overdue BETWEEN 1 AND 15 THEN '1-15' "
        "WHEN days_overdue BETWEEN 16 AND 30 THEN '16-30' "
        "WHEN days_overdue BETWEEN 31 AND 90 THEN '31-90' "
        "WHEN days_overdue > 90 THEN '90+' "
        "ELSE '1-15' END"
    )
    aging_buckets = query(
        f"SELECT "
        f"  {_bucket_expr} AS bucket, "
        f"  ROUND(COALESCE(SUM(balance_amount), 0)::numeric, 2) AS amount, "
        f"  COUNT(DISTINCT customer_code) AS customer_count "
        f"FROM rpt_outstanding WHERE {w} "
        f"GROUP BY {_bucket_expr} "
        f"ORDER BY CASE {_bucket_expr} WHEN '1-15' THEN 1 WHEN '16-30' THEN 2 WHEN '31-90' THEN 3 WHEN '90+' THEN 4 END",
        p
    )

    # Customer breakdown
    bucket_cond = ""
    bucket_params = []
    if bucket:
        bucket_cond = f" AND {_bucket_expr} = %s"
        bucket_params = [bucket]

    customers = query(
        f"SELECT customer_code, customer_name, "
        f"  COUNT(*) AS invoice_count, "
        f"  ROUND(COALESCE(SUM(balance_amount), 0)::numeric, 2) AS pending_amount "
        f"FROM rpt_outstanding WHERE {w}{bucket_cond} "
        f"GROUP BY customer_code, customer_name "
        f"ORDER BY pending_amount DESC",
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
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return []
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route,
    }.items() if v is not None}

    w, p = _build_where(filters)

    return query(
        f"SELECT trx_code, trx_date, due_date, "
        f"  original_amount, balance_amount, pending_amount, collected_amount, "
        f"  days_overdue, aging_bucket, "
        f"  user_code, user_name, route_code, route_name "
        f"FROM rpt_outstanding WHERE {w} "
        f"ORDER BY trx_date DESC",
        p
    )
