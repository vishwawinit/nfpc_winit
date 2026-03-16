"""Dashboard report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()


def _filter_keys(filters: dict, allowed_keys: set) -> dict:
    """Return a copy of filters containing only keys that the target table supports."""
    return {k: v for k, v in filters.items() if k in allowed_keys}


# Column availability per table
# rpt_sales_detail has: date_from/to, sales_org, route, user_code, channel, brand, category, item
SALES_DETAIL_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code', 'channel', 'brand', 'category', 'item'}
# rpt_collections has: date_from/to, sales_org, route, user_code (NO channel, brand, category)
COLLECTIONS_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_targets has: date_from/to, sales_org, route, user_code (as salesman_code) (NO channel, brand)
TARGETS_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_coverage_summary has: date_from/to, sales_org, route, user_code (NO channel, brand)
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_route_sales_collection has: date_from/to, sales_org, route, user_code (NO channel, brand)
ROUTE_SC_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_customer_visits has: date_from/to, sales_org, route, user_code (NO channel, brand)
VISITS_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_journey_plan has: date_from/to, sales_org, route, user_code
JOURNEY_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}


@router.get("/dashboard")
def get_dashboard(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    channel: Optional[str] = None,
    brand: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    asm: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'date_from': date_from, 'date_to': date_to, 'sales_org': sales_org,
        'route': route, 'user_code': user_code, 'channel': channel,
        'brand': brand,
    }.items() if v}

    # Resolve hierarchy filters (asm/depot/supervisor) to user_codes
    hierarchy_filters = {k: v for k, v in {
        'depot': depot, 'supervisor': supervisor, 'asm': asm,
    }.items() if v}
    if hierarchy_filters:
        resolved = resolve_user_codes(hierarchy_filters)
        if resolved == "__NO_MATCH__":
            return _empty_response()
        if resolved and not filters.get('user_code'):
            filters['user_code'] = resolved
        elif resolved and filters.get('user_code'):
            # Intersect with existing user_code filter
            existing = set(filters['user_code'].split(','))
            resolved_set = set(resolved.split(','))
            intersected = existing & resolved_set
            if not intersected:
                return _empty_response()
            filters['user_code'] = ','.join(intersected)

    # --- Total Sales (trx_type=1 sales, minus trx_type=4 returns) ---
    f_sales = _filter_keys(filters, SALES_DETAIL_KEYS)
    sw, sp = build_where(f_sales, date_col='trx_date')
    total_sales_row = query_one(
        f"SELECT COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount "
        f"  WHEN trx_type = 4 THEN -net_amount ELSE 0 END),0) AS total_sales "
        f"FROM rpt_sales_detail WHERE trx_type IN (1,4) AND {sw}", sp
    )
    total_sales = float(total_sales_row["total_sales"]) if total_sales_row else 0

    # --- Total Collection ---
    f_coll = _filter_keys(filters, COLLECTIONS_KEYS)
    cw, cp = build_where(f_coll, date_col='receipt_date')
    total_coll_row = query_one(
        f"SELECT COALESCE(SUM(amount),0) AS total_collection "
        f"FROM rpt_collections WHERE {cw}", cp
    )
    total_collection = float(total_coll_row["total_collection"]) if total_coll_row else 0

    # --- Total Target for the period ---
    f_target = _filter_keys(filters, TARGETS_KEYS)
    tw, tp = build_where(f_target, date_col='start_date')
    # Targets use salesman_code not user_code - adjust filter
    tw_target = tw.replace('user_code', 'salesman_code')
    target_row = query_one(
        f"SELECT COALESCE(SUM(amount),0) AS total_target "
        f"FROM rpt_targets WHERE is_active = true AND {tw_target}", tp
    )
    total_target = float(target_row["total_target"]) if target_row else 0

    # --- Daily sales breakdown (net of returns) ---
    f_sales2 = _filter_keys(filters, SALES_DETAIL_KEYS)
    sw2, sp2 = build_where(f_sales2, date_col='trx_date')
    daily_sales = query(
        f"SELECT trx_date AS date, COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount "
        f"  WHEN trx_type = 4 THEN -net_amount ELSE 0 END),0) AS sales "
        f"FROM rpt_sales_detail WHERE trx_type IN (1,4) AND {sw2} "
        f"GROUP BY trx_date ORDER BY trx_date", sp2
    )

    # --- Daily collection breakdown ---
    f_coll2 = _filter_keys(filters, COLLECTIONS_KEYS)
    cw2, cp2 = build_where(f_coll2, date_col='receipt_date')
    daily_collection = query(
        f"SELECT receipt_date AS date, COALESCE(SUM(amount),0) AS collection "
        f"FROM rpt_collections WHERE {cw2} "
        f"GROUP BY receipt_date ORDER BY receipt_date", cp2
    )

    # --- Week-wise sales & collection ---
    f_sales3 = _filter_keys(filters, SALES_DETAIL_KEYS)
    sw3, sp3 = build_where(f_sales3, date_col='trx_date')
    weekly_sales = query(
        f"SELECT DATE_TRUNC('week', trx_date)::date AS week_start, "
        f"  'W' || EXTRACT(WEEK FROM trx_date)::int AS week_label, "
        f"  COALESCE(SUM(CASE WHEN trx_type = 1 THEN net_amount "
        f"    WHEN trx_type = 4 THEN -net_amount ELSE 0 END),0) AS sales "
        f"FROM rpt_sales_detail WHERE trx_type IN (1,4) AND {sw3} "
        f"GROUP BY DATE_TRUNC('week', trx_date), EXTRACT(WEEK FROM trx_date) "
        f"ORDER BY week_start", sp3
    )
    f_coll3 = _filter_keys(filters, COLLECTIONS_KEYS)
    cw3, cp3 = build_where(f_coll3, date_col='receipt_date')
    weekly_collection = query(
        f"SELECT DATE_TRUNC('week', receipt_date)::date AS week_start, "
        f"  'W' || EXTRACT(WEEK FROM receipt_date)::int AS week_label, "
        f"  COALESCE(SUM(amount),0) AS collection "
        f"FROM rpt_collections WHERE {cw3} "
        f"GROUP BY DATE_TRUNC('week', receipt_date), EXTRACT(WEEK FROM receipt_date) "
        f"ORDER BY week_start", cp3
    )

    # --- Call metrics from coverage summary ---
    f_cov = _filter_keys(filters, COVERAGE_KEYS)
    vw, vp = build_where(f_cov, date_col='visit_date')
    call_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(scheduled_calls),0) AS scheduled_calls, "
        f"  COALESCE(SUM(total_actual_calls),0) AS actual_calls, "
        f"  COALESCE(SUM(planned_calls),0) AS planned_calls, "
        f"  COALESCE(SUM(unplanned_calls),0) AS unplanned_calls, "
        f"  COALESCE(SUM(selling_calls),0) AS selling_calls, "
        f"  COALESCE(SUM(planned_selling_calls),0) AS planned_selling_calls "
        f"FROM rpt_coverage_summary WHERE {vw}", vp
    )
    scheduled = int(call_row["scheduled_calls"]) if call_row else 0
    actual = int(call_row["actual_calls"]) if call_row else 0
    planned = int(call_row["planned_calls"]) if call_row else 0
    unplanned = int(call_row["unplanned_calls"]) if call_row else 0
    selling = int(call_row["selling_calls"]) if call_row else 0
    planned_selling = int(call_row["planned_selling_calls"]) if call_row else 0

    # Fallback: compute from raw visits when coverage_summary has no data
    if actual == 0:
        f_vis = _filter_keys(filters, VISITS_KEYS)
        vw_cv, vp_cv = build_where(f_vis, date_col='date')
        fallback = query_one(
            f"SELECT COUNT(*) AS actual_calls "
            f"FROM rpt_customer_visits WHERE {vw_cv}", vp_cv
        )
        actual = int(fallback["actual_calls"]) if fallback else 0

        # Planned from visits
        vw_pl, vp_pl = build_where(f_vis, date_col='date')
        planned_row = query_one(
            f"SELECT COUNT(*) AS planned_calls "
            f"FROM rpt_customer_visits WHERE is_planned = true AND {vw_pl}", vp_pl
        )
        planned = int(planned_row["planned_calls"]) if planned_row else 0
        unplanned = max(0, actual - planned)

        # Scheduled from journey plan
        f_jp = _filter_keys(filters, JOURNEY_KEYS)
        vw_jp, vp_jp = build_where(f_jp, date_col='date')
        jp_row = query_one(
            f"SELECT COUNT(*) AS scheduled "
            f"FROM rpt_journey_plan WHERE {vw_jp}", vp_jp
        )
        scheduled = int(jp_row["scheduled"]) if jp_row else 0

        # Selling calls = customers visited who also have a sale
        f_sell = _filter_keys(filters, SALES_DETAIL_KEYS)
        sw_sell, sp_sell = build_where(f_sell, date_col='trx_date')
        sell_row = query_one(
            f"SELECT COUNT(DISTINCT customer_code) AS selling "
            f"FROM rpt_sales_detail WHERE trx_type = 1 AND {sw_sell}", sp_sell
        )
        selling = int(sell_row["selling"]) if sell_row else 0

    # Strike rate: based on scheduled visits (selling / scheduled * 100)
    # Coverage: actual / scheduled, capped at 100%
    strike_rate = round(selling / scheduled * 100, 2) if scheduled else 0
    coverage_pct = min(100.0, round(actual / scheduled * 100, 2)) if scheduled else 0

    # Productive planned and unplanned
    productive_unplanned = max(0, selling - planned_selling)

    call_metrics = {
        "scheduled_calls": scheduled,
        "actual_calls": actual,
        "planned_calls": planned,
        "unplanned_calls": unplanned,
        "selling_calls": selling,
        "planned_selling_calls": planned_selling,
        "productive_unplanned": productive_unplanned,
        "strike_rate": strike_rate,
        "coverage_pct": coverage_pct,
    }

    # --- Route-wise Sales vs Target vs Collection ---
    f_rsc = _filter_keys(filters, ROUTE_SC_KEYS)
    rw, rp = build_where(f_rsc, date_col='date')
    route_sales_target = query(
        f"SELECT route_code, route_name, "
        f"  COALESCE(SUM(total_sales),0) AS sales, "
        f"  COALESCE(SUM(total_collection),0) AS collection, "
        f"  COALESCE(SUM(target_amount),0) AS target "
        f"FROM rpt_route_sales_collection WHERE {rw} "
        f"GROUP BY route_code, route_name ORDER BY sales DESC", rp
    )

    # --- Route-wise Visits ---
    f_cov2 = _filter_keys(filters, COVERAGE_KEYS)
    vw2, vp2 = build_where(f_cov2, date_col='visit_date')
    route_visits = query(
        f"SELECT route_code, route_name, "
        f"  COALESCE(SUM(scheduled_calls),0) AS scheduled, "
        f"  COALESCE(SUM(total_actual_calls),0) AS actual, "
        f"  COALESCE(SUM(selling_calls),0) AS selling "
        f"FROM rpt_coverage_summary WHERE {vw2} "
        f"GROUP BY route_code, route_name ORDER BY route_name", vp2
    )

    return {
        "total_sales": total_sales,
        "total_collection": total_collection,
        "total_target": total_target,
        "weekly_sales": daily_sales,
        "weekly_collection": daily_collection,
        "week_chart_sales": weekly_sales,
        "week_chart_collection": weekly_collection,
        "call_metrics": call_metrics,
        "route_wise_sales_vs_target": route_sales_target,
        "route_wise_visits": route_visits,
    }


def _empty_response():
    return {
        "total_sales": 0,
        "total_collection": 0,
        "total_target": 0,
        "weekly_sales": [],
        "weekly_collection": [],
        "week_chart_sales": [],
        "week_chart_collection": [],
        "call_metrics": {
            "scheduled_calls": 0, "actual_calls": 0, "planned_calls": 0,
            "unplanned_calls": 0, "selling_calls": 0, "planned_selling_calls": 0,
            "productive_unplanned": 0, "strike_rate": 0, "coverage_pct": 0,
        },
        "route_wise_sales_vs_target": [],
        "route_wise_visits": [],
    }
