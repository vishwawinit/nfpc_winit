"""Log Report endpoint.
Matches: sp_LogReport + sp_LogReport_TotalSummary

Sources:
  - Call metrics: rpt_coverage_summary
  - Sales: rpt_route_sales_by_item_customer
  - Collection: rpt_collections
  - User breakdown: rpt_route_sales_by_item_customer + rpt_collections
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}


@router.get("/log-report")
def get_log_report(
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
            return _empty()
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code, 'route': route,
        'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}

    # --- Call Summary from rpt_coverage_summary ---
    f_cov = {k: v for k, v in filters.items() if k in COVERAGE_KEYS}
    cw, cp = build_where(f_cov, date_col='visit_date')
    call_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(scheduled_calls), 0) AS total_calls, "
        f"  COALESCE(SUM(selling_calls), 0) AS productive_calls, "
        f"  COALESCE(SUM(total_actual_calls) - SUM(selling_calls), 0) AS non_productive_calls "
        f"FROM rpt_coverage_summary WHERE {cw}", cp
    )
    total_calls = int(call_row["total_calls"]) if call_row else 0
    productive = int(call_row["productive_calls"]) if call_row else 0
    non_productive = int(call_row["non_productive_calls"]) if call_row else 0
    strike_rate = round(productive / total_calls * 100, 2) if total_calls else 0

    call_summary = {
        "total_calls": total_calls,
        "productive_calls": productive,
        "non_productive_calls": non_productive,
        "strike_rate": strike_rate,
    }

    # --- Sales Summary from rpt_route_sales_by_item_customer ---
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}

    # Resolve sales_org to user_codes for summary table
    rsic_filters = dict(f_rsic)
    if sales_org and 'user_code' not in rsic_filters:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs)
        if org_rows:
            rsic_filters['user_code'] = ','.join(r['code'] for r in org_rows)

    rw, rp = build_where(rsic_filters, date_col='date')
    sales_row = query_one(
        f"SELECT COALESCE(SUM(total_sales), 0) AS total_sales, "
        f"  COALESCE(SUM(total_gr_sales + total_damage_sales + total_expiry_sales), 0) AS total_returns "
        f"FROM rpt_route_sales_by_item_customer WHERE {rw}", rp
    )
    total_sales = float(sales_row["total_sales"]) if sales_row else 0
    total_returns = float(sales_row["total_returns"]) if sales_row else 0

    # Collection
    colw, colp = build_where(filters, date_col='receipt_date')
    col_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS collection "
        f"FROM rpt_collections WHERE {colw}", colp
    )
    collection = float(col_row["collection"]) if col_row else 0

    # Current month sales
    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    mtd_end = date(ref_date.year, 12, 31) if ref_date.month == 12 else date(ref_date.year, ref_date.month + 1, 1) - timedelta(days=1)
    mtd_f = {k: v for k, v in rsic_filters.items() if k != 'date_from' and k != 'date_to'}
    mtd_f['date_from'] = mtd_start
    mtd_f['date_to'] = mtd_end
    mw, mp = build_where(mtd_f, date_col='date')
    mtd_row = query_one(
        f"SELECT COALESCE(SUM(total_sales), 0) AS mtd_sales "
        f"FROM rpt_route_sales_by_item_customer WHERE {mw}", mp
    )

    sales_summary = {
        "total_sales": round(total_sales, 2),
        "total_credit_notes": round(total_returns, 2),
        "collection_received": round(collection, 2),
        "current_month_sales": round(float(mtd_row["mtd_sales"]) if mtd_row else 0, 2),
    }

    # --- User Data ---
    user_sales = query(
        f"SELECT r.user_code, COALESCE(du.name, r.user_code) AS user_name, "
        f"  COALESCE(du.sales_org_code, '') AS sales_org_name, "
        f"  ROUND(SUM(r.total_sales)::numeric, 2) AS sales_amount, "
        f"  ROUND(SUM(r.total_gr_sales + r.total_damage_sales + r.total_expiry_sales)::numeric, 2) AS credit_amount "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_user du ON r.user_code = du.code "
        f"WHERE {rw} "
        f"GROUP BY r.user_code, COALESCE(du.name, r.user_code), COALESCE(du.sales_org_code, '') "
        f"ORDER BY sales_amount DESC",
        rp
    )

    # Collection per user
    user_col = query(
        f"SELECT user_code, COALESCE(SUM(amount), 0) AS collection_amount "
        f"FROM rpt_collections WHERE {colw} GROUP BY user_code", colp
    )
    col_map = {r["user_code"]: float(r["collection_amount"]) for r in user_col}

    user_data = []
    for row in user_sales:
        user_data.append({
            "user_code": row["user_code"],
            "user_name": row["user_name"],
            "sales_org_name": row["sales_org_name"],
            "sales_amount": float(row["sales_amount"]),
            "credit_amount": float(row["credit_amount"]),
            "collection_amount": col_map.get(row["user_code"], 0),
        })

    return {
        "call_summary": call_summary,
        "sales_summary": sales_summary,
        "user_data": user_data,
    }


def _empty():
    return {
        "call_summary": {"total_calls": 0, "productive_calls": 0, "non_productive_calls": 0, "strike_rate": 0},
        "sales_summary": {"total_sales": 0, "total_credit_notes": 0, "collection_received": 0, "current_month_sales": 0},
        "user_data": [],
    }
