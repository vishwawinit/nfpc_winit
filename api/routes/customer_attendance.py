"""Customer Attendance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where

router = APIRouter()


@router.get("/customer-attendance")
def get_customer_attendance(
    user_code: Optional[str] = None,
    customer: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'customer': customer,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='date')

    rows = query(
        f"""
        SELECT
            date,
            route_name AS area,
            user_name,
            customer_code,
            customer_name,
            arrival_time AS start_time,
            out_time AS end_time,
            total_time_mins AS spent_time
        FROM rpt_customer_visits
        WHERE {w}
        ORDER BY date DESC, arrival_time
        """,
        p
    )

    result = []
    for r in rows:
        result.append({
            "date": str(r["date"]) if r["date"] else None,
            "area": r["area"],
            "user_name": r["user_name"],
            "customer_code": r["customer_code"],
            "customer_name": r["customer_name"],
            "start_time": str(r["start_time"]) if r["start_time"] else None,
            "end_time": str(r["end_time"]) if r["end_time"] else None,
            "spent_time": float(r["spent_time"]) if r["spent_time"] else 0,
        })

    return result
