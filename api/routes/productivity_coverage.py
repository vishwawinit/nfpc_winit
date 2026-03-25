"""Productivity & Coverage report endpoint.
Uses same logic as dashboard SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS:
- Filters to routes with active assignments (has_active_assignment = true)
- coverage_pct = planned_calls / scheduled_calls (not selling/actual which is strike rate)
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()


@router.get("/productivity-coverage")
def get_productivity_coverage(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
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

    filters = {k: v for k, v in {
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org, 'route': route, 'user_code': user_code,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='visit_date', prefix='c')

    # Match dashboard: filter to routes with active user assignments only
    active_join = "JOIN dim_route _dr ON c.route_code = _dr.code AND _dr.has_active_assignment = true "

    # Summary totals — same columns as dashboard call metrics
    summary_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(c.scheduled_calls), 0) AS scheduled, "
        f"  COALESCE(SUM(c.total_actual_calls), 0) AS total_actual, "
        f"  COALESCE(SUM(c.planned_calls), 0) AS planned, "
        f"  COALESCE(SUM(c.selling_calls), 0) AS selling, "
        f"  COALESCE(SUM(c.planned_selling_calls), 0) AS planned_selling "
        f"FROM rpt_coverage_summary c "
        f"{active_join}"
        f"WHERE {w}",
        p
    )

    scheduled    = int(summary_row["scheduled"])     if summary_row else 0
    total_actual = int(summary_row["total_actual"])  if summary_row else 0
    planned      = int(summary_row["planned"])       if summary_row else 0
    selling      = int(summary_row["selling"])       if summary_row else 0
    planned_selling = int(summary_row["planned_selling"]) if summary_row else 0

    unplanned           = max(0, total_actual - planned)
    productive_unplanned = max(0, selling - planned_selling)
    # Coverage = planned visits / scheduled (matches dashboard formula)
    coverage_pct = min(100.0, round(planned / scheduled * 100, 2)) if scheduled else 0
    # Strike rate = selling / total actual (for reference in per-user table)
    strike_rate = min(100.0, round(selling / total_actual * 100, 2)) if total_actual else 0

    summary = {
        "total_scheduled":       scheduled,
        "total_actual":          total_actual,
        "planned":               planned,
        "unplanned":             unplanned,
        "productive_planned":    planned_selling,
        "productive_unplanned":  productive_unplanned,
        "selling_calls":         selling,
        "coverage_pct":          coverage_pct,
        "strike_rate":           strike_rate,
    }

    # Per-user breakdown
    user_rows = query(
        f"SELECT "
        f"  c.user_code, c.user_name, "
        f"  COALESCE(SUM(c.scheduled_calls), 0) AS scheduled, "
        f"  COALESCE(SUM(c.total_actual_calls), 0) AS actual, "
        f"  COALESCE(SUM(c.planned_calls), 0) AS planned_calls, "
        f"  COALESCE(SUM(c.selling_calls), 0) AS productive, "
        f"  COALESCE(SUM(c.planned_selling_calls), 0) AS planned_selling "
        f"FROM rpt_coverage_summary c "
        f"{active_join}"
        f"WHERE {w} "
        f"GROUP BY c.user_code, c.user_name "
        f"ORDER BY c.user_name",
        p
    )

    users = []
    for row in user_rows:
        sched = int(row["scheduled"])
        act   = int(row["actual"])
        plan  = int(row["planned_calls"])
        prod  = int(row["productive"])
        users.append({
            "user_code":    row["user_code"],
            "user_name":    row["user_name"],
            "scheduled":    sched,
            "actual":       act,
            "planned":      plan,
            "unplanned":    max(0, act - plan),
            "productive":   prod,
            "coverage_pct": min(100.0, round(plan / sched * 100, 2)) if sched else 0,
        })

    return {"summary": summary, "users": users}
