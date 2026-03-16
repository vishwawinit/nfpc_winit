"""MTD Attendance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/mtd-attendance")
def get_mtd_attendance(
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'date_from': date_from,
        'date_to': date_to, 'sales_org': sales_org,
    }.items() if v is not None}

    jw, jp = build_where(filters, date_col='date')

    # Count distinct working days per user from journeys
    user_days = query(
        f"""
        SELECT
            user_code,
            user_name,
            sales_org_code,
            COUNT(DISTINCT date) AS total_working_days
        FROM rpt_journeys
        WHERE {jw}
        GROUP BY user_code, user_name, sales_org_code
        ORDER BY user_name
        """,
        jp
    )

    # Count holidays in the date range
    hw, hp = build_where(filters, date_col='holiday_date')
    holiday_row = query(
        f"SELECT COUNT(DISTINCT holiday_date) AS holiday_count FROM rpt_holidays WHERE {hw}",
        hp
    )
    holiday_count = int(holiday_row[0]["holiday_count"]) if holiday_row else 0

    # Calculate planned working days (weekdays in range minus holidays)
    d_from = date_from or date(date.today().year, date.today().month, 1)
    d_to = date_to or date.today()

    # Count weekdays (Mon-Fri) in date range
    total_days = (d_to - d_from).days + 1
    weekdays = 0
    for i in range(total_days):
        d = d_from + timedelta(days=i)
        if d.weekday() < 5:  # Mon-Fri
            weekdays += 1

    # Also count Saturdays as half-days? Keep simple: weekdays minus holidays
    planned_working_days = weekdays - holiday_count

    result = []
    for r in user_days:
        working = int(r["total_working_days"])
        absent = max(0, planned_working_days - working)
        pct = round(working / planned_working_days * 100, 2) if planned_working_days > 0 else 0
        result.append({
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "sales_org_code": r["sales_org_code"],
            "total_working_days": working,
            "planned_working_days": planned_working_days,
            "total_absent_days": absent,
            "attendance_pct": pct,
        })

    return result
