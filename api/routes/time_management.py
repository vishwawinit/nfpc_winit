"""Time Management report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/time-management")
def get_time_management(
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'date_from': date_from,
        'date_to': date_to, 'sales_org': sales_org,
    }.items() if v is not None}

    jw, jp = build_where(filters, date_col='date', prefix='j')

    # Join journeys + EOT (start/end) + customer visits (first checkin, last checkout, productive time)
    rows = query(
        f"""
        SELECT
            j.date,
            j.user_code,
            j.user_name,
            j.start_time AS journey_start,
            j.end_time AS journey_end,
            eot_start.eot_time AS eot_start_time,
            eot_end.eot_time AS eot_end_time,
            cv.first_checkin,
            cv.last_checkout,
            CASE WHEN j.start_time IS NOT NULL AND j.end_time IS NOT NULL
                THEN GREATEST(0, LEAST(24,
                    EXTRACT(EPOCH FROM (j.end_time - j.start_time)) / 3600.0
                ))
                ELSE 0 END AS total_working_hours,
            cv.productive_time_mins
        FROM rpt_journeys j
        LEFT JOIN (
            SELECT user_code, trip_date, eot_time
            FROM rpt_eot WHERE eot_type = 'START'
        ) eot_start ON j.user_code = eot_start.user_code AND j.date = eot_start.trip_date
        LEFT JOIN (
            SELECT user_code, trip_date, eot_time
            FROM rpt_eot WHERE eot_type = 'END'
        ) eot_end ON j.user_code = eot_end.user_code AND j.date = eot_end.trip_date
        LEFT JOIN (
            SELECT
                user_code, date,
                MIN(arrival_time) AS first_checkin,
                MAX(out_time) AS last_checkout,
                COALESCE(SUM(total_time_mins), 0) AS productive_time_mins
            FROM rpt_customer_visits
            GROUP BY user_code, date
        ) cv ON j.user_code = cv.user_code AND j.date = cv.date
        WHERE {jw}
        ORDER BY j.date DESC, j.user_name
        LIMIT 500
        """,
        jp
    )

    result = []
    for r in rows:
        result.append({
            "date": str(r["date"]) if r["date"] else None,
            "user_code": r["user_code"],
            "user_name": r["user_name"],
            "eot_start_time": str(r["eot_start_time"]) if r["eot_start_time"] else None,
            "eot_end_time": str(r["eot_end_time"]) if r["eot_end_time"] else None,
            "first_checkin": str(r["first_checkin"]) if r["first_checkin"] else None,
            "last_checkout": str(r["last_checkout"]) if r["last_checkout"] else None,
            "total_working_hours": round(float(r["total_working_hours"]), 2) if r["total_working_hours"] else 0,
            "productive_time": round(float(r["productive_time_mins"]) / 60, 2) if r["productive_time_mins"] else 0,
        })

    return result
