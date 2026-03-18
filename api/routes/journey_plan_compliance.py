"""Journey Plan Compliance report endpoint.
Matches: usp_Populate_RouteCoverageReportSummary_Data logic

Sources:
  - Scheduled: rpt_journey_plan (COUNT per user per date)
  - Actual visits: rpt_customer_visits (DISTINCT date+customer+route)
  - Planned visited: journey plan entries matched by a visit
  - Selling: visits with matching sales in rpt_route_sales_by_item_customer

Primary: rpt_coverage_summary when available, fallback to raw computation.
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()

COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
JOURNEY_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}


@router.get("/journey-plan-compliance")
def get_journey_plan_compliance(
    user_code: Optional[str] = None,
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return {"summary": [], "drill_down": []}
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'user_code': user_code, 'route': route,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # Try rpt_coverage_summary first (fast, pre-computed)
    cw, cp = build_where(filters, date_col='visit_date')
    summary = query(
        f"SELECT visit_date AS date, "
        f"  COUNT(DISTINCT user_code) AS num_users, "
        f"  COALESCE(SUM(scheduled_calls), 0) AS scheduled_calls, "
        f"  COALESCE(SUM(total_actual_calls), 0) AS actual_calls, "
        f"  COALESCE(SUM(planned_calls), 0) AS planned_calls, "
        f"  COALESCE(SUM(selling_calls), 0) AS selling_calls, "
        f"  COALESCE(SUM(scheduled_calls - planned_calls), 0) AS unplanned, "
        f"  CASE WHEN SUM(scheduled_calls) > 0 "
        f"    THEN ROUND(SUM(total_actual_calls)::numeric / SUM(scheduled_calls) * 100, 2) "
        f"    ELSE 0 END AS coverage_pct "
        f"FROM rpt_coverage_summary WHERE {cw} "
        f"GROUP BY visit_date ORDER BY visit_date DESC",
        cp
    )

    # If no coverage data, compute from raw tables
    if not summary:
        jw, jp = build_where(filters, date_col='date')

        # Scheduled per date per user from journey plan
        summary = query(
            f"WITH scheduled AS ( "
            f"  SELECT jp.date, COUNT(*) AS scheduled_calls, "
            f"    COUNT(DISTINCT jp.user_code) AS num_users "
            f"  FROM rpt_journey_plan jp WHERE {jw} "
            f"  GROUP BY jp.date "
            f"), "
            f"visited AS ( "
            f"  SELECT cv.date, COUNT(DISTINCT cv.customer_code || cv.route_code) AS actual_calls "
            f"  FROM rpt_customer_visits cv WHERE {jw} "
            f"  GROUP BY cv.date "
            f"), "
            f"planned_visited AS ( "
            f"  SELECT jp.date, COUNT(*) AS planned_calls "
            f"  FROM rpt_journey_plan jp "
            f"  WHERE EXISTS (SELECT 1 FROM rpt_customer_visits cv "
            f"    WHERE cv.route_code = jp.route_code AND cv.date = jp.date "
            f"    AND cv.customer_code = jp.customer_code) "
            f"  AND {jw} GROUP BY jp.date "
            f") "
            f"SELECT s.date, s.num_users, s.scheduled_calls, "
            f"  COALESCE(v.actual_calls, 0) AS actual_calls, "
            f"  COALESCE(p.planned_calls, 0) AS planned_calls, "
            f"  0 AS selling_calls, "
            f"  GREATEST(s.scheduled_calls - COALESCE(p.planned_calls, 0), 0) AS unplanned, "
            f"  CASE WHEN s.scheduled_calls > 0 "
            f"    THEN ROUND(COALESCE(v.actual_calls, 0)::numeric / s.scheduled_calls * 100, 2) "
            f"    ELSE 0 END AS coverage_pct "
            f"FROM scheduled s "
            f"LEFT JOIN visited v ON s.date = v.date "
            f"LEFT JOIN planned_visited p ON s.date = p.date "
            f"ORDER BY s.date DESC",
            jp + jp + jp
        )

    # Drill-down: per user per date from coverage summary
    drill_down = query(
        f"SELECT visit_date AS date, user_code, user_name, route_code, "
        f"  COALESCE(SUM(scheduled_calls), 0) AS scheduled, "
        f"  COALESCE(SUM(total_actual_calls), 0) AS actual, "
        f"  COALESCE(SUM(planned_calls), 0) AS planned, "
        f"  COALESCE(SUM(selling_calls), 0) AS selling, "
        f"  COALESCE(SUM(scheduled_calls - planned_calls), 0) AS unplanned, "
        f"  CASE WHEN SUM(scheduled_calls) > 0 "
        f"    THEN ROUND(SUM(total_actual_calls)::numeric / SUM(scheduled_calls) * 100, 2) "
        f"    ELSE 0 END AS coverage_pct "
        f"FROM rpt_coverage_summary WHERE {cw} "
        f"GROUP BY visit_date, user_code, user_name, route_code "
        f"ORDER BY visit_date DESC, user_name",
        cp
    )

    return {
        "summary": summary,
        "drill_down": drill_down,
    }
