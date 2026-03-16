"""Endorsement Report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/endorsement")
def get_endorsement(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'route': route, 'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org, 'user_code': user_code,
    }.items() if v is not None}

    # --- Header: route info + depot times ---
    hw, hp = build_where(filters, date_col='date')
    header_row = query_one(
        f"SELECT "
        f"  route_code, route_name, user_code, user_name, sales_org_code, "
        f"  MIN(arrival_time) AS depot_out_time, "
        f"  MAX(out_time) AS depot_in_time, "
        f"  EXTRACT(EPOCH FROM MAX(out_time) - MIN(arrival_time)) / 60 AS total_driving_mins, "
        f"  COUNT(*) AS total_visits, "
        f"  SUM(CASE WHEN is_productive THEN 1 ELSE 0 END) AS productive_visits, "
        f"  ROUND(AVG(total_time_mins)::numeric, 1) AS avg_time_per_visit "
        f"FROM rpt_customer_visits "
        f"WHERE {hw} "
        f"GROUP BY route_code, route_name, user_code, user_name, sales_org_code",
        hp
    )

    header = {}
    if header_row:
        header = {
            "route_code": header_row["route_code"],
            "route_name": header_row["route_name"],
            "user_code": header_row["user_code"],
            "user_name": header_row["user_name"],
            "sales_org_code": header_row["sales_org_code"],
            "depot_out_time": str(header_row["depot_out_time"]) if header_row["depot_out_time"] else None,
            "depot_in_time": str(header_row["depot_in_time"]) if header_row["depot_in_time"] else None,
            "total_driving_mins": float(header_row["total_driving_mins"]) if header_row["total_driving_mins"] else 0,
            "total_visits": int(header_row["total_visits"]),
            "productive_visits": int(header_row["productive_visits"]),
            "avg_time_per_visit": float(header_row["avg_time_per_visit"]) if header_row["avg_time_per_visit"] else 0,
        }

    # --- Customer visit details with sales values ---
    vw, vp = build_where(filters, date_col='date', prefix='v')
    customers = query(
        f"SELECT "
        f"  v.customer_code, v.customer_name, v.channel_name, "
        f"  v.is_planned, v.arrival_time, v.out_time, v.total_time_mins, "
        f"  v.is_productive, v.latitude, v.longitude, "
        f"  COALESCE(s.total_value, 0) AS total_value, "
        f"  COALESCE(s.total_returns, 0) AS total_returns "
        f"FROM rpt_customer_visits v "
        f"LEFT JOIN ( "
        f"  SELECT customer_code, trx_date, route_code, "
        f"    SUM(CASE WHEN trx_type = 1 THEN net_amount ELSE 0 END) AS total_value, "
        f"    SUM(CASE WHEN trx_type = 4 THEN net_amount ELSE 0 END) AS total_returns "
        f"  FROM rpt_sales_detail "
        f"  GROUP BY customer_code, trx_date, route_code "
        f") s ON v.customer_code = s.customer_code "
        f"  AND v.date = s.trx_date "
        f"  AND v.route_code = s.route_code "
        f"WHERE {vw} "
        f"ORDER BY v.arrival_time "
        f"LIMIT 500",
        vp
    )

    # Format customer rows
    customer_list = []
    for c in customers:
        customer_list.append({
            "customer_code": c["customer_code"],
            "customer_name": c["customer_name"],
            "channel_name": c["channel_name"],
            "is_planned": c["is_planned"],
            "visit_type": "JP" if c["is_planned"] else "UJP",
            "arrival_time": str(c["arrival_time"]) if c["arrival_time"] else None,
            "out_time": str(c["out_time"]) if c["out_time"] else None,
            "time_spent_mins": float(c["total_time_mins"]) if c["total_time_mins"] else 0,
            "is_productive": c["is_productive"],
            "total_value": float(c["total_value"]),
            "total_returns": float(c["total_returns"]),
            "latitude": float(c["latitude"]) if c["latitude"] else None,
            "longitude": float(c["longitude"]) if c["longitude"] else None,
        })

    return {
        "header": header,
        "customers": customer_list,
    }
