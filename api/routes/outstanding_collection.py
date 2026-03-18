"""Outstanding Collection report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()


def _build_summary_where(filters: dict):
    """Build WHERE for rpt_outstanding_summary (pre-aggregated table)."""
    conditions = []
    params = []
    if filters.get('year'):
        conditions.append("year = %s")
        params.append(int(filters['year']))
    if filters.get('sales_org'):
        vals = [v.strip() for v in filters['sales_org'].split(',') if v.strip()]
        if len(vals) == 1:
            conditions.append("org_code = %s")
            params.append(vals[0])
        else:
            conditions.append(f"org_code IN ({','.join(['%s']*len(vals))})")
            params.extend(vals)
    if filters.get('customer'):
        conditions.append("customer_code = %s")
        params.append(filters['customer'])
    if filters.get('user_code'):
        vals = [v.strip() for v in filters['user_code'].split(',') if v.strip()]
        if len(vals) == 1:
            conditions.append("user_code = %s")
            params.append(vals[0])
        else:
            conditions.append(f"user_code IN ({','.join(['%s']*len(vals))})")
            params.extend(vals)
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
    year: Optional[int] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy filters (hos/asm/supervisor/depot) to user_codes
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

    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route,
        'year': year,
    }.items() if v is not None}

    w, p = _build_summary_where(filters)

    # Query 1: Bucket KPIs from pre-aggregated summary (fast)
    aging_buckets = query(
        f"""
        SELECT aging_bucket AS bucket,
            COALESCE(SUM(pending_amount), 0) AS amount,
            COUNT(DISTINCT customer_code) AS customer_count
        FROM rpt_outstanding_summary
        WHERE {w}
        GROUP BY aging_bucket
        ORDER BY CASE aging_bucket
            WHEN 'Current' THEN 1 WHEN '1-30' THEN 2 WHEN '31-60' THEN 3
            WHEN '61-90' THEN 4 WHEN '91-120' THEN 5 WHEN '120+' THEN 6 ELSE 7 END
        """,
        p
    )

    # Query 2: Customer-level from summary (filtered by bucket if selected)
    bucket_cond = ""
    bucket_params = []
    if bucket:
        bucket_cond = " AND aging_bucket = %s"
        bucket_params = [bucket]

    customers = query(
        f"""
        SELECT customer_code, MIN(customer_name) AS customer_name,
            SUM(invoice_count) AS invoice_count,
            COALESCE(SUM(pending_amount), 0) AS pending_amount
        FROM rpt_outstanding_summary
        WHERE {w}{bucket_cond}
        GROUP BY customer_code
        ORDER BY pending_amount DESC
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
    year: Optional[int] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy filters (hos/asm/supervisor/depot) to user_codes
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

    filters = {k: v for k, v in {
        'customer': customer, 'sales_org': sales_org,
        'user_code': user_code, 'route': route,
        'year': year,
    }.items() if v is not None}

    # Build WHERE for raw rpt_outstanding table (invoices detail)
    conds, prms = [], []
    if filters.get('sales_org'):
        conds.append("org_code = %s"); prms.append(filters['sales_org'])
    if filters.get('customer'):
        conds.append("customer_code = %s"); prms.append(filters['customer'])
    if filters.get('user_code'):
        vals = [v.strip() for v in filters['user_code'].split(',') if v.strip()]
        if len(vals) == 1:
            conds.append("user_code = %s"); prms.append(vals[0])
        else:
            conds.append(f"user_code IN ({','.join(['%s']*len(vals))})"); prms.extend(vals)
    if filters.get('route'):
        conds.append("route_code = %s"); prms.append(filters['route'])
    if filters.get('year'):
        y = int(filters['year'])
        conds.append("trx_date >= %s AND trx_date < %s"); prms.extend([f"{y}-01-01", f"{y+1}-01-01"])
    w = " AND ".join(conds) if conds else "1=1"
    p = prms

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
        """,
        p
    )

    return invoices
