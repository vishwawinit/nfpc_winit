"""Productivity & Coverage report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/productivity-coverage")
def get_productivity_coverage(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='visit_date')

    # Summary totals
    summary_row = query_one(
        f"""
        SELECT
            COALESCE(SUM(scheduled_calls), 0) AS total_scheduled,
            COALESCE(SUM(total_actual_calls), 0) AS total_actual,
            COALESCE(SUM(planned_calls), 0) AS planned,
            COALESCE(SUM(unplanned_calls), 0) AS unplanned,
            COALESCE(SUM(planned_selling_calls), 0) AS productive_planned,
            COALESCE(SUM(selling_calls) - SUM(planned_selling_calls), 0) AS productive_unplanned,
            CASE WHEN SUM(scheduled_calls) > 0
                THEN ROUND(SUM(total_actual_calls)::numeric / SUM(scheduled_calls) * 100, 2)
                ELSE 0 END AS coverage_pct
        FROM rpt_coverage_summary
        WHERE {w}
        """,
        p
    )

    summary = {
        "total_scheduled": int(summary_row["total_scheduled"]) if summary_row else 0,
        "total_actual": int(summary_row["total_actual"]) if summary_row else 0,
        "planned": int(summary_row["planned"]) if summary_row else 0,
        "unplanned": int(summary_row["unplanned"]) if summary_row else 0,
        "productive_planned": int(summary_row["productive_planned"]) if summary_row else 0,
        "productive_unplanned": int(summary_row["productive_unplanned"]) if summary_row else 0,
        "coverage_pct": float(summary_row["coverage_pct"]) if summary_row else 0,
    }

    # Per-user breakdown
    users = query(
        f"""
        SELECT
            user_code,
            user_name,
            COALESCE(SUM(scheduled_calls), 0) AS scheduled,
            COALESCE(SUM(total_actual_calls), 0) AS actual,
            COALESCE(SUM(selling_calls), 0) AS productive,
            CASE WHEN SUM(scheduled_calls) > 0
                THEN ROUND(SUM(total_actual_calls)::numeric / SUM(scheduled_calls) * 100, 2)
                ELSE 0 END AS coverage_pct
        FROM rpt_coverage_summary
        WHERE {w}
        GROUP BY user_code, user_name
        ORDER BY user_name
        """,
        p
    )

    return {
        "summary": summary,
        "users": users,
    }
