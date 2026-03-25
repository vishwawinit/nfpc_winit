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

    rows = query(
        f"SELECT j.date, j.user_code, j.user_name, j.route_code, j.route_name, "
        f"  COALESCE(j.sales_org_code, du.sales_org_code) AS sales_org_code "
        f"FROM rpt_journeys j "
        f"LEFT JOIN dim_user du ON du.code = j.user_code "
        f"WHERE {jw} "
        f"ORDER BY j.date DESC, j.user_name",
        jp
    )

    return [
        {
            "date": str(r["date"]),
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "route_code": r["route_code"],
            "route_name": r["route_name"],
            "sales_org_code": r["sales_org_code"],
        }
        for r in rows
    ]
