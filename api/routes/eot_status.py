"""EOT Status report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/eot-status")
def get_eot_status(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_code: Optional[str] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # --- User & Journey Info ---
    jw, jp = build_where(filters, date_col='date')
    journey_row = query_one(
        f"""
        SELECT
            user_code, user_name, route_code, route_name,
            vehicle_code, date, start_time, end_time
        FROM rpt_journeys
        WHERE {jw}
        ORDER BY date DESC
        LIMIT 1
        """,
        jp
    )

    user_info = None
    if journey_row:
        user_info = {
            "user_code": journey_row["user_code"],
            "user_name": journey_row["user_name"],
            "route_code": journey_row["route_code"],
            "route_name": journey_row["route_name"],
            "vehicle": journey_row["vehicle_code"],
            "date": str(journey_row["date"]) if journey_row["date"] else None,
        }

    # --- Route plan followed & all customers visited ---
    # Check journey plan compliance
    jpw, jpp = build_where(filters, date_col='date')
    plan_row = query_one(
        f"""
        SELECT
            COUNT(*) AS total_planned,
            COUNT(*) FILTER (WHERE visit_status::text = '1') AS visited
        FROM rpt_journey_plan
        WHERE {jpw}
        """,
        jpp
    )
    total_planned = int(plan_row["total_planned"]) if plan_row else 0
    visited = int(plan_row["visited"]) if plan_row else 0
    route_plan_followed = total_planned > 0 and visited == total_planned
    all_customers_visited = route_plan_followed

    # --- KPIs: order count, sales, collection ---
    sw, sp = build_where(filters, date_col='trx_date')
    kpi_row = query_one(
        f"""
        SELECT
            COUNT(DISTINCT trx_code) AS order_count,
            COALESCE(SUM(net_amount), 0) AS sales_amount
        FROM rpt_sales_detail
        WHERE trx_type = 1 AND {sw}
        """,
        sp
    )

    colw, colp = build_where(filters, date_col='receipt_date')
    col_row = query_one(
        f"SELECT COALESCE(SUM(amount), 0) AS collection_amount "
        f"FROM rpt_collections WHERE {colw}",
        colp
    )

    kpis = {
        "order_count": int(kpi_row["order_count"]) if kpi_row else 0,
        "sales_amount": float(kpi_row["sales_amount"]) if kpi_row else 0,
        "collection_amount": float(col_row["collection_amount"]) if col_row else 0,
    }

    # --- Call Metrics from coverage summary ---
    cw, cp = build_where(filters, date_col='visit_date')
    call_row = query_one(
        f"""
        SELECT
            COALESCE(SUM(scheduled_calls), 0) AS scheduled_calls,
            COALESCE(SUM(total_actual_calls), 0) AS total_actual_calls,
            COALESCE(SUM(planned_calls), 0) AS planned_calls,
            COALESCE(SUM(unplanned_calls), 0) AS unplanned_calls,
            COALESCE(SUM(selling_calls), 0) AS selling_calls,
            COALESCE(SUM(planned_selling_calls), 0) AS planned_selling_calls
        FROM rpt_coverage_summary
        WHERE {cw}
        """,
        cp
    )
    call_metrics = {
        "scheduled_calls": int(call_row["scheduled_calls"]) if call_row else 0,
        "total_actual_calls": int(call_row["total_actual_calls"]) if call_row else 0,
        "planned_calls": int(call_row["planned_calls"]) if call_row else 0,
        "unplanned_calls": int(call_row["unplanned_calls"]) if call_row else 0,
        "selling_calls": int(call_row["selling_calls"]) if call_row else 0,
        "planned_selling_calls": int(call_row["planned_selling_calls"]) if call_row else 0,
    }

    # --- Journey Stops from customer visits ---
    vw, vp = build_where(filters, date_col='date')
    journey_stops = query(
        f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY arrival_time) AS sequence,
            customer_code,
            customer_name,
            is_planned,
            arrival_time,
            latitude,
            longitude
        FROM rpt_customer_visits
        WHERE {vw}
        ORDER BY arrival_time
        """,
        vp
    )

    return {
        "user_info": user_info,
        "route_plan_followed": route_plan_followed,
        "all_customers_visited": all_customers_visited,
        "kpis": kpis,
        "call_metrics": call_metrics,
        "journey_stops": journey_stops,
    }
