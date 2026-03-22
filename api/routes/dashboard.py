"""Dashboard report endpoint - aligned with MSSQL stored procedures.

Source SPs:
  - sp_tblOrder_Total_SalesAndCollection_Dashboard_Reports_ByItem (total sales/collection)
  - sp_tblOrder_Weekly_Dashboard_Reports_V1_NEw_OPTS_ByItem_V1 (daily sales trend)
  - sp_tblPaymentHeader_Weekly_Dashboard_Reports_V1_New_OPTS (daily collection trend)
  - SP_CoverageReport_ForDashboard_Reports_V1_NEW_OPTS (coverage/call metrics)
  - SP_StrikeRate_ForDashboard_Reports (strike rate)
  - sp_GetSalesmanWiseCollection_Dashboard_Reports_By_Item (route-wise sales+collection)
  - SP_GetDashboardRouteDetails_Dashboard_Reports_V1_New_OPTS (route-wise coverage)
  - SP_tblCommonTarget_SELECT_TARGET_FOR_DASHBOARD_ByItem (targets)
"""
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
# rpt_route_sales_summary_by_item: date, sales_org, route, user_code, item, category, brand
ROUTE_SALES_ITEM_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code', 'item', 'category', 'brand'}
# rpt_route_sales_collection: date, sales_org, route, user_code
ROUTE_SC_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_coverage_summary: date, sales_org, route, user_code
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_sales_detail: all filter keys
SALES_DETAIL_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code', 'channel', 'brand', 'category', 'item'}
# rpt_customer_visits: date, sales_org, route, user_code
VISITS_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_journey_plan: date, sales_org, route, user_code
JOURNEY_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_invoice_totals: trx_date, sales_org, route, user_code
INVOICE_TOTALS_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
# rpt_route_sales_by_item_customer: date, route, user_code (no sales_org)
RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/dashboard")
def get_dashboard(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    channel: Optional[str] = None,
    brand: Optional[str] = None,
    hos: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    asm: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'date_from': date_from, 'date_to': date_to, 'sales_org': sales_org,
        'route': route, 'user_code': user_code, 'channel': channel,
        'brand': brand,
    }.items() if v}

    # Resolve hierarchy filters (hos/asm/depot/supervisor) to user_codes
    hierarchy_filters = {k: v for k, v in {
        'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm,
    }.items() if v}
    if hierarchy_filters:
        resolved = resolve_user_codes(hierarchy_filters)
        if resolved == "__NO_MATCH__":
            return _empty_response()
        if resolved and not filters.get('user_code'):
            filters['user_code'] = resolved
        elif resolved and filters.get('user_code'):
            existing = set(filters['user_code'].split(','))
            resolved_set = set(resolved.split(','))
            intersected = existing & resolved_set
            if not intersected:
                return _empty_response()
            filters['user_code'] = ','.join(intersected)

    # When sales_org is set, build a JOIN clause for RSIC tables (which lack sales_org_code)
    _rsic_org_join = ""
    _rsic_org_params = []
    if filters.get('sales_org') and not filters.get('route'):
        orgs = [v.strip() for v in filters['sales_org'].split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _rsic_org_join = f"JOIN dim_route _dr ON {{alias}}.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _rsic_org_params = orgs

    def _rsic_filters():
        """Get RSIC filters (without sales_org since RSIC table lacks it)."""
        return _filter_keys(filters, RSIC_KEYS)

    def _rsic_query(select, table, alias, where, params, group_by="", order_by=""):
        """Helper for RSIC table queries that need sales_org via JOIN."""
        join = _rsic_org_join.replace("{alias}", alias) if _rsic_org_join else ""
        all_params = _rsic_org_params + params
        sql = f"{select} FROM {table} {alias} {join}WHERE {where}"
        if group_by: sql += f" {group_by}"
        if order_by: sql += f" {order_by}"
        return sql, all_params

    # =========================================================
    # TOTAL SALES — primary: rpt_route_sales_by_item_customer (matches MSSQL exactly)
    # rpt_route_sales_summary_by_item has duplicate rows, so we avoid it for totals
    # =========================================================
    f_rsic = _rsic_filters()
    rsicw, rsicp = build_where(f_rsic, date_col='date', prefix='rc')
    join_clause = _rsic_org_join.replace("{alias}", "rc") if _rsic_org_join else ""
    sales_row = query_one(
        f"SELECT COALESCE(SUM(rc.total_sales),0) AS total_sales, "
        f"  COALESCE(SUM(rc.total_gr_sales + rc.total_damage_sales + rc.total_expiry_sales),0) AS total_wastage "
        f"FROM rpt_route_sales_by_item_customer rc {join_clause}WHERE {rsicw}",
        _rsic_org_params + rsicp
    )
    total_sales = float(sales_row["total_sales"]) if sales_row else 0
    total_sales_with_tax = total_sales  # same source, tax included
    total_wastage = float(sales_row["total_wastage"]) if sales_row else 0

    # Fallback: rpt_invoice_totals
    if total_sales == 0:
        f_it = _filter_keys(filters, INVOICE_TOTALS_KEYS)
        itw, itp = build_where(f_it, date_col='trx_date')
        it_row = query_one(
            f"SELECT COALESCE(SUM(total_sales),0) AS total_sales, "
            f"  COALESCE(SUM(total_returns),0) AS total_returns "
            f"FROM rpt_invoice_totals WHERE {itw}", itp
        )
        if it_row:
            it_sales = float(it_row["total_sales"])
            it_returns = float(it_row["total_returns"])
            total_sales = max(0.0, it_sales - it_returns)

    # =========================================================
    # TOTAL COLLECTION — primary: rpt_route_sales_collection
    # Fallback: rpt_collections
    # =========================================================
    f_rsc = _filter_keys(filters, ROUTE_SC_KEYS)
    cw, cp = build_where(f_rsc, date_col='date')
    coll_row = query_one(
        f"SELECT COALESCE(SUM(total_collection),0) AS total_collection "
        f"FROM rpt_route_sales_collection WHERE {cw}", cp
    )
    total_collection = float(coll_row["total_collection"]) if coll_row else 0

    # Fallback: use rpt_collections when summary table has no data
    if total_collection == 0:
        f_coll_fb = _filter_keys(filters, ROUTE_SC_KEYS)
        cfw, cfp = build_where(f_coll_fb, date_col='receipt_date')
        coll_fb = query_one(
            f"SELECT COALESCE(SUM(amount),0) AS total_collection "
            f"FROM rpt_collections WHERE {cfw}", cfp
        )
        total_collection = float(coll_fb["total_collection"]) if coll_fb else 0

    # =========================================================
    # TOTAL TARGET — from rpt_route_sales_summary_by_item (dedup)
    # =========================================================
    f_rssi = _filter_keys(filters, ROUTE_SALES_ITEM_KEYS)
    sw_tgt, sp_tgt = build_where(f_rssi, date_col='date')
    tgt_row = query_one(
        f"SELECT COALESCE(SUM(target_amount),0) AS target FROM ("
        f"  SELECT DISTINCT ON (route_code, item_code, date) target_amount "
        f"  FROM rpt_route_sales_summary_by_item WHERE {sw_tgt}"
        f") t", sp_tgt
    )
    total_target = float(tgt_row["target"]) if tgt_row else 0

    # Fallback: use rpt_targets
    if total_target == 0:
        tgt_row2 = query_one(
            "SELECT COALESCE(SUM(amount),0) AS target "
            "FROM rpt_targets WHERE is_active = true "
            "AND start_date <= %s AND end_date >= %s",
            [filters.get('date_to') or '2026-12-31', filters.get('date_from') or '2026-01-01']
        )
        total_target = float(tgt_row2["target"]) if tgt_row2 else 0

    # =========================================================
    # DAILY SALES TREND — primary: rpt_route_sales_by_item_customer
    # =========================================================
    f_rsic2 = _rsic_filters()
    rsicw2, rsicp2 = build_where(f_rsic2, date_col='date', prefix='rc')
    join2 = _rsic_org_join.replace("{alias}", "rc") if _rsic_org_join else ""
    daily_sales = query(
        f"SELECT rc.date, COALESCE(SUM(rc.total_sales), 0) AS sales "
        f"FROM rpt_route_sales_by_item_customer rc {join2}WHERE {rsicw2} "
        f"GROUP BY rc.date ORDER BY rc.date", _rsic_org_params + rsicp2
    )

    # Fallback: rpt_invoice_totals
    if not daily_sales:
        f_it2 = _filter_keys(filters, INVOICE_TOTALS_KEYS)
        itw2, itp2 = build_where(f_it2, date_col='trx_date')
        daily_sales = query(
            f"SELECT trx_date AS date, "
            f"  COALESCE(SUM(total_sales) - SUM(total_returns), 0) AS sales "
            f"FROM rpt_invoice_totals WHERE {itw2} "
            f"GROUP BY trx_date ORDER BY trx_date", itp2
        )

    # =========================================================
    # DAILY COLLECTION TREND — primary: rpt_route_sales_collection
    # Fallback: rpt_collections
    # =========================================================
    f_rsc2 = _filter_keys(filters, ROUTE_SC_KEYS)
    cw2, cp2 = build_where(f_rsc2, date_col='date')
    daily_collection = query(
        f"SELECT date, COALESCE(SUM(total_collection), 0) AS collection "
        f"FROM rpt_route_sales_collection WHERE {cw2} "
        f"GROUP BY date ORDER BY date", cp2
    )

    # Fallback: use rpt_collections for daily collection trend
    if not daily_collection:
        f_coll2 = _filter_keys(filters, ROUTE_SC_KEYS)
        cfw2, cfp2 = build_where(f_coll2, date_col='receipt_date')
        daily_collection = query(
            f"SELECT receipt_date AS date, COALESCE(SUM(amount), 0) AS collection "
            f"FROM rpt_collections WHERE {cfw2} "
            f"GROUP BY receipt_date ORDER BY receipt_date", cfp2
        )

    # =========================================================
    # WEEK-WISE SALES & COLLECTION
    # =========================================================
    f_rsic3 = _rsic_filters()
    rsicw3, rsicp3 = build_where(f_rsic3, date_col='date', prefix='rc')
    join3 = _rsic_org_join.replace("{alias}", "rc") if _rsic_org_join else ""
    weekly_sales = query(
        f"SELECT DATE_TRUNC('week', rc.date)::date AS week_start, "
        f"  'W' || EXTRACT(WEEK FROM rc.date)::int AS week_label, "
        f"  COALESCE(SUM(rc.total_sales), 0) AS sales "
        f"FROM rpt_route_sales_by_item_customer rc {join3}WHERE {rsicw3} "
        f"GROUP BY DATE_TRUNC('week', rc.date), EXTRACT(WEEK FROM rc.date) "
        f"ORDER BY week_start", _rsic_org_params + rsicp3
    )

    # Fallback: weekly sales from rpt_invoice_totals
    if not weekly_sales:
        f_it3 = _filter_keys(filters, INVOICE_TOTALS_KEYS)
        itw3, itp3 = build_where(f_it3, date_col='trx_date')
        weekly_sales = query(
            f"SELECT DATE_TRUNC('week', trx_date)::date AS week_start, "
            f"  'W' || EXTRACT(WEEK FROM trx_date)::int AS week_label, "
            f"  COALESCE(SUM(total_sales) - SUM(total_returns), 0) AS sales "
            f"FROM rpt_invoice_totals WHERE {itw3} "
            f"GROUP BY DATE_TRUNC('week', trx_date), EXTRACT(WEEK FROM trx_date) "
            f"ORDER BY week_start", itp3
        )

    f_rsc3 = _filter_keys(filters, ROUTE_SC_KEYS)
    cw3, cp3 = build_where(f_rsc3, date_col='date')
    weekly_collection = query(
        f"SELECT DATE_TRUNC('week', date)::date AS week_start, "
        f"  'W' || EXTRACT(WEEK FROM date)::int AS week_label, "
        f"  COALESCE(SUM(total_collection), 0) AS collection "
        f"FROM rpt_route_sales_collection WHERE {cw3} "
        f"GROUP BY DATE_TRUNC('week', date), EXTRACT(WEEK FROM date) "
        f"ORDER BY week_start", cp3
    )

    # Fallback: weekly collection from rpt_collections
    if not weekly_collection:
        f_coll3 = _filter_keys(filters, ROUTE_SC_KEYS)
        cfw3, cfp3 = build_where(f_coll3, date_col='receipt_date')
        weekly_collection = query(
            f"SELECT DATE_TRUNC('week', receipt_date)::date AS week_start, "
            f"  'W' || EXTRACT(WEEK FROM receipt_date)::int AS week_label, "
            f"  COALESCE(SUM(amount), 0) AS collection "
            f"FROM rpt_collections WHERE {cfw3} "
            f"GROUP BY DATE_TRUNC('week', receipt_date), EXTRACT(WEEK FROM receipt_date) "
            f"ORDER BY week_start", cfp3
        )

    # =========================================================
    # CALL METRICS — exact replica of usp_Populate_RouteCoverageReportSummary_Data
    #
    # Step 1: ScheduledCalls = COUNT of journey plan entries (PlannedCustomers)
    # Step 2: TotalActualCalls = COUNT of DISTINCT (date, client, route) visits
    # Step 3: ActualCalls = COUNT of journey plan entries that have a matching visit
    #         (LEFT JOIN journey_plan → visits, count where visit exists)
    # Step 4: SellingCalls = COUNT of DISTINCT (date, client, route) from
    #         transactions that have a matching visit (#Transactions)
    # Step 5: PlannedSellingCalls = COUNT of #Transactions that also match
    #         a journey plan entry
    # =========================================================

    # Primary: use rpt_coverage_summary (pre-computed, matches MSSQL tblRouteCoverageSummary)
    # When no hierarchy/user filter: restrict to routes with active user-location assignments
    # When specific users are filtered: show all their routes (already scoped by user_code)
    _has_user_filter = bool(filters.get('user_code'))
    _cov_route_join = "" if _has_user_filter else "JOIN dim_route r ON c.route_code = r.code AND r.has_active_assignment = true "
    f_cov = _filter_keys(filters, COVERAGE_KEYS)
    covw, covp = build_where(f_cov, date_col='visit_date', prefix='c')
    cov_row = query_one(
        f"SELECT COALESCE(SUM(c.scheduled_calls),0) AS scheduled, "
        f"  COALESCE(SUM(c.total_actual_calls),0) AS total_actual, "
        f"  COALESCE(SUM(c.planned_calls),0) AS actual_calls, "
        f"  COALESCE(SUM(c.selling_calls),0) AS selling, "
        f"  COALESCE(SUM(c.planned_selling_calls),0) AS planned_selling "
        f"FROM rpt_coverage_summary c "
        f"{_cov_route_join}"
        f"WHERE {covw}", covp
    )
    scheduled = int(cov_row["scheduled"]) if cov_row else 0
    total_actual = int(cov_row["total_actual"]) if cov_row else 0
    actual_calls = int(cov_row["actual_calls"]) if cov_row else 0
    selling = int(cov_row["selling"]) if cov_row else 0
    planned_selling = int(cov_row["planned_selling"]) if cov_row else 0

    # Fallback: compute from raw tables when rpt_coverage_summary has no data
    if scheduled == 0 and total_actual == 0:
        f_jp = _filter_keys(filters, JOURNEY_KEYS)
        vw_jp, vp_jp = build_where(f_jp, date_col='date')
        f_vis = _filter_keys(filters, VISITS_KEYS)
        vw_cv, vp_cv = build_where(f_vis, date_col='date')
        f_sd = _filter_keys(filters, SALES_DETAIL_KEYS)
        sdw, sdp = build_where(f_sd, date_col='trx_date', prefix='sd')

        call_row = query_one(
            f"WITH "
            f"visits AS ( "
            f"  SELECT DISTINCT date, customer_code, route_code "
            f"  FROM rpt_customer_visits WHERE {vw_cv} "
            f"), "
            f"plan AS ( "
            f"  SELECT date, customer_code, route_code "
            f"  FROM rpt_journey_plan WHERE {vw_jp} "
            f"), "
            f"selling AS ( "
            f"  SELECT DISTINCT sd.trx_date AS date, sd.customer_code, sd.route_code "
            f"  FROM rpt_sales_detail sd "
            f"  WHERE sd.trx_type = 1 AND {sdw} "
            f"    AND EXISTS (SELECT 1 FROM visits v "
            f"      WHERE v.route_code = sd.route_code AND v.date = sd.trx_date "
            f"        AND v.customer_code = sd.customer_code) "
            f") "
            f"SELECT "
            f"  (SELECT COUNT(*) FROM plan) AS scheduled, "
            f"  (SELECT COUNT(*) FROM visits) AS total_actual, "
            f"  (SELECT COUNT(*) FROM plan p WHERE EXISTS ( "
            f"    SELECT 1 FROM visits v WHERE v.route_code = p.route_code "
            f"      AND v.date = p.date AND v.customer_code = p.customer_code)) AS actual_calls, "
            f"  (SELECT COUNT(*) FROM selling) AS selling, "
            f"  (SELECT COUNT(*) FROM selling sv WHERE EXISTS ( "
            f"    SELECT 1 FROM plan p WHERE p.route_code = sv.route_code "
            f"      AND p.date = sv.date AND p.customer_code = sv.customer_code)) AS planned_selling",
            vp_cv + vp_jp + sdp
        )
        scheduled = int(call_row["scheduled"]) if call_row else 0
        total_actual = int(call_row["total_actual"]) if call_row else 0
        actual_calls = int(call_row["actual_calls"]) if call_row else 0
        selling = int(call_row["selling"]) if call_row else 0
        planned_selling = int(call_row["planned_selling"]) if call_row else 0

    planned = actual_calls  # actual_calls = visits that matched journey plan
    unplanned = max(0, total_actual - actual_calls)  # total visits minus planned visits

    # =========================================================
    # STRIKE RATE — matches SP_StrikeRate_ForDashboard_Reports
    # MSSQL: groups tblTrxHeader by route+date+client, SUM(TotalAmount)
    # net_amount in rpt_sales_detail = header-level TotalAmount (repeated per line)
    # Must deduplicate by trx_code first to avoid double-counting
    # Strike = 1 if SUM(TotalAmount) > 100, else 0 per (route, date, client)
    # =========================================================
    # Strike Rate = selling_calls / total_actual_calls * 100
    # (matches old dashboard which displays selling/actual as strike rate)
    strike_rate = min(100.0, round(selling / total_actual * 100, 2)) if total_actual else 0

    # Coverage: planned (adherence) calls / scheduled calls * 100
    # Matches old dashboard: ActualCalls(planned) / ScheduledCalls
    coverage_pct = min(100.0, round(actual_calls / scheduled * 100, 2)) if scheduled else 0

    # Productive unplanned
    productive_unplanned = max(0, selling - planned_selling)

    call_metrics = {
        "scheduled_calls": scheduled,
        "actual_calls": total_actual,
        "planned_calls": planned,
        "unplanned_calls": unplanned,
        "selling_calls": selling,
        "planned_selling_calls": planned_selling,
        "productive_unplanned": productive_unplanned,
        "strike_rate": strike_rate,
        "coverage_pct": coverage_pct,
    }

    # =========================================================
    # ROUTE-WISE SALES VS COLLECTION
    # Matches: sp_GetSalesmanWiseCollection_Dashboard_Reports_By_Item
    # Sales from tblRouteSalesSummaryByItem, Collection from tblRouteSalesCollectionSummary
    # =========================================================
    # Route-wise: sales from rpt_route_sales_by_item_customer, collection from rpt_route_sales_collection
    f_rsic_rt = _rsic_filters()
    rsicw_rt, rsicp_rt = build_where(f_rsic_rt, date_col='date', prefix='r')
    join_rt = _rsic_org_join.replace("{alias}", "r") if _rsic_org_join else ""
    f_rsc_rt = _filter_keys(filters, ROUTE_SC_KEYS)
    rw_c, rp_c = build_where(f_rsc_rt, date_col='date', prefix='c')
    route_sales_target = query(
        f"SELECT COALESCE(s.route_code, c.route_code) AS route_code, "
        f"  COALESCE(s.route_name, c.route_name) AS route_name, "
        f"  COALESCE(s.sales, 0) AS sales, "
        f"  COALESCE(c.collection, 0) AS collection, "
        f"  0 AS target "
        f"FROM ( "
        f"  SELECT r.route_code, COALESCE(dr.name, r.route_code) AS route_name, "
        f"    SUM(r.total_sales) AS sales "
        f"  FROM rpt_route_sales_by_item_customer r "
        f"  LEFT JOIN dim_route dr ON r.route_code = dr.code "
        f"  {join_rt}"
        f"  WHERE {rsicw_rt} "
        f"  GROUP BY r.route_code, COALESCE(dr.name, r.route_code) "
        f") s "
        f"FULL OUTER JOIN ( "
        f"  SELECT c.route_code, c.route_name, SUM(c.total_collection) AS collection "
        f"  FROM rpt_route_sales_collection c WHERE {rw_c} "
        f"  GROUP BY c.route_code, c.route_name "
        f") c ON s.route_code = c.route_code "
        f"ORDER BY sales DESC NULLS LAST",
        _rsic_org_params + rsicp_rt + rp_c
    )

    # =========================================================
    # ROUTE-WISE VISITS / COVERAGE
    # Matches: SP_GetDashboardRouteDetails_Dashboard_Reports_V1_New_OPTS
    # Returns SUM(ScheduledCalls) as TotalCount, SUM(ActualCalls) as VisitCount
    # MSSQL ActualCalls = our planned_calls (planned actual calls)
    # =========================================================
    f_cov2 = _filter_keys(filters, COVERAGE_KEYS)
    vw2, vp2 = build_where(f_cov2, date_col='visit_date', prefix='c')
    _cov2_join = "" if _has_user_filter else "JOIN dim_route r ON c.route_code = r.code AND r.has_active_assignment = true "
    route_visits = query(
        f"SELECT c.route_code, c.route_name, "
        f"  COALESCE(SUM(c.scheduled_calls),0) AS scheduled, "
        f"  COALESCE(SUM(c.planned_calls),0) AS actual, "
        f"  COALESCE(SUM(c.selling_calls),0) AS selling "
        f"FROM rpt_coverage_summary c "
        f"{_cov2_join}"
        f"WHERE {vw2} "
        f"GROUP BY c.route_code, c.route_name ORDER BY c.route_name", vp2
    )

    # Fallback: build route-wise visits from raw tables when coverage_summary has no data
    if not route_visits:
        f_rv = _filter_keys(filters, VISITS_KEYS)
        vw_rv, vp_rv = build_where(f_rv, date_col='date')
        f_jp_rv = _filter_keys(filters, JOURNEY_KEYS)
        vw_jp_rv, vp_jp_rv = build_where(f_jp_rv, date_col='date')

        # Actual visits per route from rpt_customer_visits
        route_actual = {
            r['route_code']: r for r in query(
                f"SELECT route_code, route_name, COUNT(*) AS actual, "
                f"  COALESCE(SUM(CASE WHEN is_planned THEN 1 ELSE 0 END), 0) AS planned "
                f"FROM rpt_customer_visits WHERE {vw_rv} "
                f"GROUP BY route_code, route_name", vp_rv
            )
        }

        # Scheduled per route from rpt_journey_plan
        route_scheduled = {
            r['route_code']: int(r['scheduled']) for r in query(
                f"SELECT route_code, COUNT(*) AS scheduled "
                f"FROM rpt_journey_plan WHERE {vw_jp_rv} "
                f"GROUP BY route_code", vp_jp_rv
            )
        }

        # Merge both dicts — union of routes from either table
        all_rv_routes = set(route_actual.keys()) | set(route_scheduled.keys())
        route_visits = sorted([
            {
                'route_code': rc,
                'route_name': route_actual.get(rc, {}).get('route_name', rc),
                'scheduled': route_scheduled.get(rc, 0),
                'actual': int(route_actual.get(rc, {}).get('actual', 0)),
                'selling': 0,
            }
            for rc in all_rv_routes if rc
        ], key=lambda x: x['route_name'] or '')

    return {
        "total_sales": round(total_sales, 2),
        "total_collection": round(total_collection, 2),
        "total_target": round(total_target, 2),
        "total_sales_with_tax": round(total_sales_with_tax, 2),
        "total_wastage": round(total_wastage, 2),
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
        "total_sales_with_tax": 0,
        "total_wastage": 0,
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
