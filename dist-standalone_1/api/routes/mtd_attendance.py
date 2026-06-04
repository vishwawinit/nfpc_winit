"""MTD Attendance report endpoint.
Returns all journey records for the selected date range (no user deduplication).
Sources: rpt_journeys, dim_user
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query
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

    base_filters = {k: v for k, v in {
        'user_code': user_code, 'route': route,
        'date_from': d_from, 'date_to': d_to,
    }.items() if v is not None}

    jw, jp = build_where(base_filters, date_col='date', prefix='j')

    if sales_org:
        orgs = [o.strip() for o in sales_org.split(',') if o.strip()]
        ph = ','.join(['%s'] * len(orgs))
        jw += f" AND COALESCE(j.sales_org_code, du.sales_org_code) IN ({ph})"
        jp.extend(orgs)

    planned_days = (d_to - d_from).days + 1

    rows = query(
        f"SELECT j.user_code, j.user_name, "
        f"  COUNT(DISTINCT j.date) AS working_days "
        f"FROM rpt_journeys j "
        f"LEFT JOIN dim_user du ON du.code = j.user_code "
        f"WHERE {jw} "
        f"GROUP BY j.user_code, j.user_name "
        f"ORDER BY j.user_name",
        jp
    )

    return [
        {
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "total_working_days": int(r["working_days"]),
            "planned_working_days": planned_days,
            "total_absent_days": max(0, planned_days - int(r["working_days"])),
            "attendance_pct": round(int(r["working_days"]) / planned_days * 100, 1) if planned_days > 0 else 0,
        }
        for r in rows
    ]
