"""MTD Attendance report endpoint.
Attendance = distinct dates a user had a journey (from rpt_journeys).
Working days = weekdays Mon-Sat minus holidays in date range.

Sources:
  - Present days: rpt_journeys (COUNT DISTINCT date per user)
  - Holidays: rpt_holidays
  - User info: dim_user (route, sales_org)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()


@router.get("/mtd-attendance")
def get_mtd_attendance(
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
            return []
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    today = date.today()
    d_from = date_from or date(today.year, today.month, 1)
    d_to = date_to or today

    filters = {k: v for k, v in {
        'user_code': user_code, 'route': route,
        'date_from': d_from, 'date_to': d_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # Working days: Mon-Sat (weekday < 6) minus holidays
    holidays = query(
        "SELECT DISTINCT holiday_date FROM rpt_holidays "
        "WHERE holiday_date >= %s AND holiday_date <= %s",
        [d_from, d_to]
    )
    holiday_dates = set(str(r["holiday_date"]) for r in holidays)

    total_days = (d_to - d_from).days + 1
    planned_working_days = sum(
        1 for i in range(total_days)
        if (d_from + timedelta(days=i)).weekday() < 6  # Mon-Sat
        and str(d_from + timedelta(days=i)) not in holiday_dates
    )

    # Build set of working dates for filtering
    working_dates = []
    for i in range(total_days):
        d = d_from + timedelta(days=i)
        if d.weekday() < 6 and str(d) not in holiday_dates:
            working_dates.append(str(d))

    # Present days per user from rpt_journeys (only count working days)
    jw, jp = build_where(filters, date_col='date')
    # Exclude Sundays (weekday=0 in PG is Sunday? No - PG EXTRACT(DOW) 0=Sun, 6=Sat)
    user_days = query(
        f"SELECT j.user_code, j.user_name, j.route_code, j.route_name, "
        f"  j.sales_org_code, "
        f"  COUNT(DISTINCT j.date) FILTER (WHERE EXTRACT(DOW FROM j.date) != 0) AS present_days "
        f"FROM rpt_journeys j WHERE {jw} "
        f"GROUP BY j.user_code, j.user_name, j.route_code, j.route_name, j.sales_org_code "
        f"ORDER BY j.user_name",
        jp
    )

    result = []
    for r in user_days:
        present = int(r["present_days"])
        absent = max(0, planned_working_days - present)
        pct = round(present / planned_working_days * 100, 2) if planned_working_days > 0 else 0
        result.append({
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "route_code": r["route_code"],
            "route_name": r["route_name"],
            "sales_org_code": r["sales_org_code"],
            "total_working_days": planned_working_days,
            "planned_working_days": present,
            "total_absent_days": absent,
            "attendance_pct": pct,
        })

    return result
