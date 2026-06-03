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
    # Filter to active routes only (matches dashboard behaviour)
    cw, cp = build_where(filters, date_col='visit_date', prefix='rc')
    active_join = "JOIN dim_route dr ON rc.route_code = dr.code AND dr.has_active_assignment = true "
    summary = query(
        f"SELECT rc.visit_date AS date, "
        f"  COUNT(DISTINCT rc.user_code) AS num_users, "
        f"  COALESCE(SUM(rc.scheduled_calls), 0) AS scheduled_calls, "
        f"  COALESCE(SUM(rc.total_actual_calls), 0) AS actual_calls, "
        f"  COALESCE(SUM(rc.planned_calls), 0) AS planned_calls, "
        f"  COALESCE(SUM(rc.selling_calls), 0) AS selling_calls, "
        f"  CASE WHEN SUM(rc.total_actual_calls) = 0 THEN 0 ELSE ABS(SUM(rc.total_actual_calls) - SUM(rc.scheduled_calls)) END AS unplanned, "
        f"  CASE WHEN SUM(rc.scheduled_calls) > 0 "
        f"    THEN LEAST(ROUND(SUM(rc.planned_calls)::numeric / SUM(rc.scheduled_calls) * 100, 2), 100) "
        f"    ELSE 0 END AS coverage_pct "
        f"FROM rpt_coverage_summary rc {active_join}WHERE {cw} "
        f"GROUP BY rc.visit_date ORDER BY rc.visit_date DESC",
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
            f"    THEN LEAST(ROUND(COALESCE(v.actual_calls, 0)::numeric / s.scheduled_calls * 100, 2), 100) "
            f"    ELSE 0 END AS coverage_pct "
            f"FROM scheduled s "
            f"LEFT JOIN visited v ON s.date = v.date "
            f"LEFT JOIN planned_visited p ON s.date = p.date "
            f"ORDER BY s.date DESC",
            jp + jp + jp
        )

    # Drill-down: per user per route per date
    drill_down = query(
        f"SELECT rc.visit_date AS date, rc.user_code, rc.user_name, rc.route_code, rc.route_name, "
        f"  COALESCE(SUM(rc.scheduled_calls), 0) AS scheduled, "
        f"  COALESCE(SUM(rc.total_actual_calls), 0) AS actual, "
        f"  COALESCE(SUM(rc.planned_calls), 0) AS planned, "
        f"  COALESCE(SUM(rc.selling_calls), 0) AS selling, "
        f"  CASE WHEN SUM(rc.total_actual_calls) = 0 THEN 0 ELSE ABS(SUM(rc.total_actual_calls) - SUM(rc.scheduled_calls)) END AS unplanned, "
        f"  CASE WHEN SUM(rc.scheduled_calls) > 0 "
        f"    THEN LEAST(ROUND(SUM(rc.planned_calls)::numeric / SUM(rc.scheduled_calls) * 100, 2), 100) "
        f"    ELSE 0 END AS coverage_pct "
        f"FROM rpt_coverage_summary rc {active_join}WHERE {cw} "
        f"GROUP BY rc.visit_date, rc.user_code, rc.user_name, rc.route_code, rc.route_name "
        f"ORDER BY rc.visit_date DESC, rc.user_name",
        cp
    )

    # Fallback drill_down from raw tables when coverage_summary has no data
    if not drill_down:
        jw2, jp2 = build_where(filters, date_col='date')
        drill_down = query(
            f"WITH scheduled AS ( "
            f"  SELECT jp.date, jp.user_code, jp.user_name, jp.route_code, "
            f"    COALESCE(dr.name, jp.route_code) AS route_name, "
            f"    COUNT(*) AS scheduled_calls "
            f"  FROM rpt_journey_plan jp "
            f"  LEFT JOIN dim_route dr ON dr.code = jp.route_code "
            f"  WHERE {jw2} AND jp.user_code != jp.route_code "
            f"  GROUP BY jp.date, jp.user_code, jp.user_name, jp.route_code, dr.name "
            f"), "
            f"visited AS ( "
            f"  SELECT cv.date, cv.route_code, "
            f"    COUNT(DISTINCT cv.customer_code) AS actual_calls "
            f"  FROM rpt_customer_visits cv WHERE {jw2} "
            f"  GROUP BY cv.date, cv.route_code "
            f"), "
            f"planned_visited AS ( "
            f"  SELECT jp.date, jp.route_code, COUNT(*) AS planned_calls "
            f"  FROM rpt_journey_plan jp "
            f"  WHERE EXISTS ( "
            f"    SELECT 1 FROM rpt_customer_visits cv "
            f"    WHERE cv.route_code = jp.route_code AND cv.date = jp.date "
            f"    AND cv.customer_code = jp.customer_code "
            f"  ) AND {jw2} AND jp.user_code != jp.route_code "
            f"  GROUP BY jp.date, jp.route_code "
            f"), "
            f"selling AS ( "
            f"  SELECT r.date, r.route_code, COUNT(DISTINCT r.customer_code) AS selling_calls "
            f"  FROM rpt_route_sales_by_item_customer r "
            f"  WHERE r.total_sales > 0 AND {jw2} "
            f"  GROUP BY r.date, r.route_code "
            f") "
            f"SELECT s.date, s.user_code, s.user_name, s.route_code, s.route_name, "
            f"  s.scheduled_calls AS scheduled, "
            f"  COALESCE(v.actual_calls, 0) AS actual, "
            f"  COALESCE(p.planned_calls, 0) AS planned, "
            f"  COALESCE(sl.selling_calls, 0) AS selling, "
            f"  ABS(COALESCE(v.actual_calls, 0) - s.scheduled_calls) AS unplanned, "
            f"  CASE WHEN s.scheduled_calls > 0 "
            f"    THEN LEAST(ROUND(COALESCE(v.actual_calls, 0)::numeric / s.scheduled_calls * 100, 2), 100) "
            f"    ELSE 0 END AS coverage_pct "
            f"FROM scheduled s "
            f"LEFT JOIN visited v ON s.date = v.date AND s.route_code = v.route_code "
            f"LEFT JOIN planned_visited p ON s.date = p.date AND s.route_code = p.route_code "
            f"LEFT JOIN selling sl ON s.date = sl.date AND s.route_code = sl.route_code "
            f"ORDER BY s.date DESC, s.user_name",
            jp2 + jp2 + jp2 + jp2
        )

    return {
        "summary": summary,
        "drill_down": drill_down,
    }
