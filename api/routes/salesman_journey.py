"""Salesman Journey report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/salesman-journey")
def get_salesman_journey(
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    filters = {k: v for k, v in {
        'user_code': user_code, 'date_from': date_from,
        'date_to': date_to,
    }.items() if v is not None}

    w, p = build_where(filters, date_col='date')

    # Journey start/end dates
    range_row = query_one(
        f"SELECT MIN(date) AS journey_start, MAX(date) AS journey_end "
        f"FROM rpt_customer_visits WHERE {w}",
        p
    )

    # Visit stops ordered by arrival time
    visits = query(
        f"""
        SELECT
            ROW_NUMBER() OVER (PARTITION BY date ORDER BY arrival_time) AS sequence,
            date,
            customer_code,
            customer_name,
            latitude,
            longitude,
            arrival_time,
            out_time
        FROM rpt_customer_visits
        WHERE {w}
        ORDER BY date, arrival_time
        """,
        p
    )

    return {
        "journey_start": str(range_row["journey_start"]) if range_row and range_row["journey_start"] else None,
        "journey_end": str(range_row["journey_end"]) if range_row and range_row["journey_end"] else None,
        "visits": visits,
    }
