"""Log Report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/log-report")
def get_log_report(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    customer: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code,
        'customer': customer, 'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}

    # --- Call Summary from coverage_summary ---
    cw, cp = build_where(filters, date_col='visit_date')
    call_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(scheduled_calls), 0) AS total_scheduled, "
        f"  COALESCE(SUM(planned_calls), 0) AS planned, "
        f"  COALESCE(SUM(unplanned_calls), 0) AS unplanned, "
        f"  COALESCE(SUM(total_actual_calls), 0) AS total_actual, "
        f"  COALESCE(SUM(planned_selling_calls), 0) AS productive_planned, "
        f"  COALESCE(SUM(selling_calls) - SUM(planned_selling_calls), 0) AS productive_unplanned "
        f"FROM rpt_coverage_summary WHERE {cw}",
        cp
    )
    call_summary = {
        "total_scheduled": int(call_row["total_scheduled"]) if call_row else 0,
        "planned": int(call_row["planned"]) if call_row else 0,
        "unplanned": int(call_row["unplanned"]) if call_row else 0,
        "total_actual": int(call_row["total_actual"]) if call_row else 0,
        "productive_planned": int(call_row["productive_planned"]) if call_row else 0,
        "productive_unplanned": int(call_row["productive_unplanned"]) if call_row else 0,
    }

    # --- Sales Summary ---
    sw, sp = build_where(filters, date_col='trx_date')

    # Total sales (trx_type=1)
    sales_row = query_one(
        f"SELECT COALESCE(SUM(net_amount), 0) AS total_sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND {sw}", sp
    )
    total_sales = float(sales_row["total_sales"]) if sales_row else 0

    # Credit notes (trx_type=3)
    credit_row = query_one(
        f"SELECT COALESCE(SUM(net_amount), 0) AS total_credit_notes "
        f"FROM rpt_sales_detail WHERE trx_type = 3 AND {sw}", sp
    )
    total_credit_notes = float(credit_row["total_credit_notes"]) if credit_row else 0

    # Collection received
    colw, colp = build_where(filters, date_col='receipt_date')
    col_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS collection_received "
        f"FROM rpt_collections WHERE {colw}", colp
    )
    collection_received = float(col_row["collection_received"]) if col_row else 0

    # Current month sales
    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    mtd_filters = {**{k: v for k, v in filters.items() if k not in ('date_from', 'date_to')},
                   'date_from': mtd_start, 'date_to': ref_date}
    mw, mp = build_where(mtd_filters, date_col='trx_date')
    mtd_row = query_one(
        f"SELECT COALESCE(SUM(net_amount), 0) AS current_month_sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND {mw}", mp
    )
    current_month_sales = float(mtd_row["current_month_sales"]) if mtd_row else 0

    sales_summary = {
        "total_sales": total_sales,
        "total_credit_notes": total_credit_notes,
        "collection_received": collection_received,
        "current_month_sales": current_month_sales,
    }

    # --- User Data ---
    user_sales = query(
        f"SELECT user_code, user_name, sales_org_name, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount ELSE 0 END), 0) AS sales_amount, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 3 THEN net_amount ELSE 0 END), 0) AS credit_amount "
        f"FROM rpt_sales_detail WHERE {sw} "
        f"GROUP BY user_code, user_name, sales_org_name "
        f"ORDER BY sales_amount DESC",
        sp
    )

    # Collection per user
    user_col = query(
        f"SELECT user_code, COALESCE(SUM(amount), 0) AS collection_amount "
        f"FROM rpt_collections WHERE {colw} "
        f"GROUP BY user_code",
        colp
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
