"""Journey Plan Compliance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/journey-plan-compliance")
def get_journey_plan_compliance(
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'date_from': date_from,
        'date_to': date_to, 'sales_org': sales_org,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='visit_date')

    # Summary grouped by date
    summary = query(
        f"""
        SELECT
            visit_date AS date,
            COUNT(DISTINCT user_code) AS num_users,
            COALESCE(SUM(scheduled_calls), 0) AS scheduled_calls,
            COALESCE(SUM(planned_calls), 0) AS planned_calls,
            COALESCE(SUM(unplanned_calls), 0) AS unplanned,
            CASE WHEN SUM(scheduled_calls) > 0
                THEN ROUND(SUM(planned_calls)::numeric / SUM(scheduled_calls) * 100, 2)
                ELSE 0 END AS coverage_pct
        FROM rpt_coverage_summary
        WHERE {w}
        GROUP BY visit_date
        ORDER BY visit_date DESC
        """,
        p
    )

    # Drill-down by date and user
    drill_down = query(
        f"""
        SELECT
            visit_date AS date,
            user_code,
            user_name,
            COALESCE(SUM(scheduled_calls), 0) AS scheduled,
            COALESCE(SUM(planned_calls), 0) AS planned,
            COALESCE(SUM(unplanned_calls), 0) AS unplanned,
            CASE WHEN SUM(scheduled_calls) > 0
                THEN ROUND(SUM(planned_calls)::numeric / SUM(scheduled_calls) * 100, 2)
                ELSE 0 END AS coverage_pct
        FROM rpt_coverage_summary
        WHERE {w}
        GROUP BY visit_date, user_code, user_name
        ORDER BY visit_date DESC, user_name
        """,
        p
    )

    return {
        "summary": summary,
        "drill_down": drill_down,
    }
