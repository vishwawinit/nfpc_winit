"""Sales Performance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

SALES_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code', 'channel', 'brand', 'category', 'item'}


def _month_range(year: int, month: int):
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last



@router.get("/sales-performance")
def get_sales_performance(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
    day: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    channel: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    today = date.today()

    # Get latest available data date
    latest_row = query_one("SELECT MAX(date) AS latest FROM rpt_route_sales_by_item_customer")
    latest_data = latest_row["latest"] if latest_row and latest_row["latest"] else today

    # Determine period
    # display_end = intended end date shown in label (not capped to latest data)
    if date_from and date_to:
        cur_start = date_from
        cur_end = date_to
        display_end = date_to
    elif day and month and year:
        requested = date(year, month, day)
        cur_start = date(year, month, 1)  # MTD always starts from month start
        display_end = requested           # label always shows the requested day
        cur_end = min(requested, latest_data)
    elif month and year:
        cur_start, cur_end = _month_range(year, month)
        if cur_end > latest_data:
            cur_end = latest_data
        display_end = cur_end
    else:
        cur_start = date(today.year, today.month, 1)
        display_end = today
        cur_end = min(today, latest_data)

    # LMTD: same day range in previous month (Feb 1 → Feb <same day>)
    # (used for filtered ROS/SKU queries only)
    if cur_start.month == 1:
        last_month_start = date(cur_start.year - 1, 12, 1)
    else:
        last_month_start = date(cur_start.year, cur_start.month - 1, 1)
    last_month_max = cur_start - timedelta(days=1)  # last calendar day of prev month
    last_month_day = min(display_end.day, last_month_max.day)
    last_month_end = date(last_month_start.year, last_month_start.month, last_month_day)

    # ── MTD / LMTD KPIs are independent of the day filter ──────────────────────
    # Always use today's day-of-month so selecting day=1 doesn't change the KPI.
    eff_month = month if month else today.month
    eff_year  = year  if year  else today.year
    mtd_kpi_start        = date(eff_year, eff_month, 1)
    _, month_last        = _month_range(eff_year, eff_month)
    is_current_month     = (eff_year == today.year and eff_month == today.month)
    # Current month → end at today; past/future month → use full month
    mtd_kpi_display = min(date(eff_year, eff_month, today.day), month_last) \
                      if is_current_month else month_last
    mtd_kpi_end     = min(mtd_kpi_display, latest_data)

    if mtd_kpi_start.month == 1:
        lmtd_kpi_start = date(mtd_kpi_start.year - 1, 12, 1)
    else:
        lmtd_kpi_start = date(mtd_kpi_start.year, mtd_kpi_start.month - 1, 1)
    lmtd_month_last = (mtd_kpi_start - timedelta(days=1))  # last day of lmtd month
    # Current month → LMTD ends on same day-of-month; past month → full lmtd month
    lmtd_kpi_end = date(lmtd_kpi_start.year, lmtd_kpi_start.month,
                        min(today.day, lmtd_month_last.day)) \
                   if is_current_month else lmtd_month_last

    # Year-to-date
    ytd_start = date(cur_start.year, 1, 1)

    # Current week
    week_start = today - timedelta(days=today.weekday())

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
    }.items() if v}

    # Resolve hierarchy filters (hos/asm/depot/supervisor) to user_codes
    hierarchy = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if hierarchy:
        resolved = resolve_user_codes(hierarchy)
        if resolved == "__NO_MATCH__":
            return _empty_response()
        if resolved and not base_filters.get('user_code'):
            base_filters['user_code'] = resolved
        elif resolved and base_filters.get('user_code'):
            existing = set(base_filters['user_code'].split(','))
            intersected = existing & set(resolved.split(','))
            if not intersected:
                return _empty_response()
            base_filters['user_code'] = ','.join(intersected)

    # Resolve sales_org to route JOIN for RSIC tables (no sales_org_code column)
    _org_join = ""
    _org_params = []
    if sales_org and not base_filters.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _org_params = orgs

    # Resolve brand/category to item_codes (table has item_code but no brand/category columns)
    item_filter_codes = None
    if brand or category:
        from api.database import query as db_query
        item_conditions = []
        item_params = []
        if brand:
            bvals = [v.strip() for v in brand.split(',') if v.strip()]
            bph = ','.join(['%s'] * len(bvals))
            item_conditions.append(f"TRIM(brand_code) IN ({bph})")
            item_params.extend(bvals)
        if category:
            cvals = [v.strip() for v in category.split(',') if v.strip()]
            cph = ','.join(['%s'] * len(cvals))
            item_conditions.append(f"category_code IN ({cph})")
            item_params.extend(cvals)
        iwhere = " AND ".join(item_conditions)
        item_rows = db_query(f"SELECT DISTINCT code FROM dim_item WHERE {iwhere}", item_params)
        if not item_rows:
            return _empty_response()
        item_filter_codes = ','.join(r['code'] for r in item_rows)
        base_filters['item'] = item_filter_codes

    # Resolve channel to customer_codes (table has customer_code but no channel column)
    if channel:
        from api.database import query as db_query
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        cust_rows = db_query(
            f"SELECT DISTINCT code FROM dim_customer WHERE TRIM(channel_code) IN ({ch_ph})",
            ch_vals
        )
        if not cust_rows:
            return _empty_response()
        base_filters['customer'] = ','.join(r['code'] for r in cust_rows)

    # --- Sales/Returns from rpt_route_sales_summary_by_item (consistent with Dashboard) ---
    RSSI_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code', 'item', 'category', 'brand'}
    RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}

    def get_sales_returns(d_start, d_end):
        f = {k: v for k, v in {**base_filters, 'date_from': d_start, 'date_to': d_end}.items() if k in RSSI_KEYS}
        if sales_org and 'sales_org' not in f:
            f['sales_org'] = sales_org
        sw, sp = build_where(f, date_col='date')
        row = query_one(
            f"SELECT COALESCE(SUM(total_sales),0) AS sales, "
            f"  COALESCE(SUM(total_wastage),0) AS total_wastage "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) "
            f"  total_sales, total_wastage "
            f"  FROM rpt_route_sales_summary_by_item WHERE {sw}) t",
            sp
        )
        # GR/Damage/Expiry breakdown still from rpt_route_sales_by_item_customer
        RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}
        f2 = {k: v for k, v in {**base_filters, 'date_from': d_start, 'date_to': d_end}.items() if k in RSIC_KEYS}
        sw2, sp2 = build_where(f2, date_col='date', prefix='r')
        row2 = query_one(
            f"SELECT COALESCE(SUM(r.total_gr_sales),0) AS gr, "
            f"  COALESCE(SUM(r.total_damage_sales),0) AS damage, "
            f"  COALESCE(SUM(r.total_expiry_sales),0) AS expiry "
            f"FROM rpt_route_sales_by_item_customer r {_org_join}WHERE {sw2}", _org_params + sp2
        )
        sales = float(row["sales"]) if row else 0
        gr = float(row2["gr"]) if row2 else 0
        damage = float(row2["damage"]) if row2 else 0
        expiry = float(row2["expiry"]) if row2 else 0
        return {"sales": sales, "gr": gr, "damage": damage, "expiry": expiry}

    def get_unfiltered_sales(d_start, d_end):
        """MTD/LMTD KPIs: date range only, no org/user/item filters."""
        row = query_one(
            "SELECT COALESCE(SUM(total_sales),0) AS sales "
            "FROM (SELECT DISTINCT ON (route_code, item_code, date) total_sales "
            "  FROM rpt_route_sales_summary_by_item "
            "  WHERE date BETWEEN %s AND %s) t",
            [d_start, d_end]
        )
        return float(row["sales"]) if row else 0

    def get_target(d_start, d_end):
        row = query_one(
            "SELECT COALESCE(SUM(amount),0) AS target "
            "FROM rpt_targets WHERE is_active = true "
            "AND start_date <= %s AND end_date >= %s",
            [d_end, d_start]
        )
        return float(row["target"]) if row else 0

    # Use exact selected period (respects day selection) — for ROS / SKU
    cur_data = get_sales_returns(cur_start, cur_end)
    last_data = get_sales_returns(last_month_start, last_month_end)
    # MTD/LMTD KPIs: company-wide, day-filter independent
    cur_sales  = get_unfiltered_sales(mtd_kpi_start, mtd_kpi_end)
    last_sales = get_unfiltered_sales(lmtd_kpi_start, lmtd_kpi_end)
    cur_target = get_target(cur_start, cur_end)
    last_target = get_target(last_month_start, last_month_end)

    cur_achievement = round(cur_sales / cur_target * 100, 2) if cur_target else 0
    last_achievement = round(last_sales / last_target * 100, 2) if last_target else 0

    # --- Return on Sales ---
    # Matches: sp_DashboardSales_SalesPercentage
    # Uses rpt_route_sales_by_item_customer (pre-aggregated, TRXStatus=200 only)
    # GR = TotalGRSales, Damage = TotalDamageSales, Expiry = TotalExpirySales
    total_s = float(cur_data["sales"])
    gr = float(cur_data["gr"])
    damage = float(cur_data["damage"])
    expiry = float(cur_data["expiry"])
    total_returns = gr + damage + expiry

    # --- Collection for full month (matches SP1: MONTH(Date)=M) ---
    COLL_KEYS = {'date_from', 'date_to', 'route', 'user_code'}
    coll_f = {k: v for k, v in {**base_filters, 'date_from': cur_start, 'date_to': cur_end}.items() if k in COLL_KEYS}
    cw, cp = build_where(coll_f, date_col='date')
    coll_row = query_one(
        f"SELECT COALESCE(SUM(total_collection),0) AS collection "
        f"FROM rpt_route_sales_collection WHERE {cw}", cp
    )
    collection = float(coll_row["collection"]) if coll_row else 0
    # Fallback to rpt_collections
    if collection == 0:
        coll_f2 = {k: v for k, v in {**base_filters, 'date_from': cur_start, 'date_to': cur_end}.items() if k in COLL_KEYS}
        cw2, cp2 = build_where(coll_f2, date_col='receipt_date')
        coll_row2 = query_one(
            f"SELECT COALESCE(SUM(amount),0) AS collection FROM rpt_collections WHERE {cw2}", cp2
        )
        collection = float(coll_row2["collection"]) if coll_row2 else 0

    return_on_sales = {
        "total_sales": round(total_s, 2),
        "total_returns": round(total_returns, 2),
        "good_return": round(gr, 2),
        "bad_return": round(damage + expiry, 2),
        "gr": round(gr, 2),
        "damage": round(damage, 2),
        "expiry": round(expiry, 2),
        "net_sales": round(total_s - total_returns, 2),
        "collection": round(collection, 2),
        "ros_pct": round(total_returns / total_s * 100, 2) if total_s else 0,
    }

    # --- SKU counts from rpt_route_sales_by_item_customer ---
    rsic_base = {k: v for k, v in base_filters.items() if k in RSIC_KEYS}
    full_month_end = min(_month_range(cur_start.year, cur_start.month)[1], latest_data)

    # Find latest date with data (filtered by user if hierarchy selected)
    latest_f = {**rsic_base, 'date_from': cur_start, 'date_to': cur_end}
    ltw, ltp = build_where(latest_f, date_col='date')
    latest_row = query_one(
        f"SELECT MAX(date) AS latest FROM rpt_route_sales_by_item_customer WHERE {ltw}", ltp
    )
    latest_date = latest_row["latest"] if latest_row and latest_row["latest"] else cur_end

    def sku_count(d_from, d_to):
        f = {**rsic_base, 'date_from': d_from, 'date_to': d_to}
        sw, sp = build_where(f, date_col='date', prefix='r')
        # Match sp_GetSKUsSold_Formula exactly:
        #   INNER JOIN tblItem + tblCustomerDetail + UserHierarchy (role=C_PRESALES_VANSALES)
        row = query_one(
            f"SELECT COUNT(DISTINCT r.item_code) AS cnt "
            f"FROM rpt_route_sales_by_item_customer r "
            f"JOIN dim_item di ON di.code = r.item_code "
            f"JOIN dim_customer dc ON dc.code = r.customer_code "
            f"JOIN dim_user du ON du.code = r.user_code AND du.role_code = 'C_PRESALES_VANSALES' "
            f"{_org_join}WHERE {sw}", _org_params + sp
        )
        return int(row["cnt"]) if row else 0

    # SP2: Daily = specific day only, MTD = full month (day-filter independent), YTD = full year
    sku_counts = {
        "today": sku_count(latest_date, latest_date),
        "today_label": str(latest_date),
        "mtd": sku_count(cur_start, full_month_end),
        "ytd": sku_count(ytd_start, date(cur_end.year, 12, 31)),
    }

    # --- SKU table from rpt_route_sales_by_item_customer (same source as KPIs) ---
    # --- SKU table matches sp_SalesByItemOfClientDashboard ---
    # Current Month: MONTH(Date)=@Month AND YEAR(Date)=@Year (full month)
    # LY Month: MONTH(Date)=@Month AND YEAR(Date)=@Year-1 (same month last year)
    # Current Week: effective week capped to month boundaries
    ly_start = date(cur_start.year - 1, cur_start.month, 1)
    ly_end = _month_range(ly_start.year, ly_start.month)[1]

    # Current week effective (capped to month boundaries like SP)
    cw_start = max(week_start, cur_start)
    cw_end = min(today, cur_end)

    # Use full_month_end for WHERE so the query fetches all month rows;
    # current_month_sales CASE still uses cur_start/cur_end (MTD only).
    cm_sk = {k: v for k, v in {**base_filters, 'date_from': cur_start, 'date_to': full_month_end}.items() if k in RSIC_KEYS}
    cmw_s, cmp_s = build_where(cm_sk, date_col='date', prefix='r')
    ly_sk = {k: v for k, v in {**base_filters, 'date_from': ly_start, 'date_to': ly_end}.items() if k in RSIC_KEYS}
    lyw_s, lyp_s = build_where(ly_sk, date_col='date', prefix='r')

    sku_table = query(
        f"SELECT "
        f"  r.item_code, COALESCE(di.name, r.item_code) AS item_name, "
        f"  di.category_code, COALESCE(di.category_name, di.category_code) AS category_name, "
        f"  COALESCE(di.brand_name, di.brand_code) AS brand_name, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS current_month_sales, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS ly_current_month_sales, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS current_week_sales "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_item di ON r.item_code = di.code "
        f"{_org_join}"
        f"WHERE ({cmw_s} OR {lyw_s}) "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), "
        f"  di.category_code, COALESCE(di.category_name, di.category_code), "
        f"  COALESCE(di.brand_name, di.brand_code) "
        f"HAVING NOT ( "
        f"  COALESCE(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END), 0) = 0 "
        f"  AND COALESCE(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END), 0) = 0 "
        f") "
        f"ORDER BY r.item_code",
        [cur_start, full_month_end, ly_start, ly_end, cw_start, cw_end]
        + _org_params + cmp_s + lyp_s
        + [cur_start, full_month_end, ly_start, ly_end]
    )

    for row in sku_table:
        ly = float(row["ly_current_month_sales"] or 0)
        cm = float(row["current_month_sales"] or 0)
        if ly == 0 and cm == 0:
            row["growth"] = 0
        elif ly == 0:
            row["growth"] = 100.0
        else:
            row["growth"] = min(100.0, round((cm - ly) / ly * 100, 2))

    return {
        "period_label": f"{mtd_kpi_start} to {mtd_kpi_display}",
        "last_month_label": f"{lmtd_kpi_start} to {lmtd_kpi_end}",
        "mtd_sales": cur_sales,
        "lmtd_sales": last_sales,
        "return_on_sales": return_on_sales,
        "sku_counts": sku_counts,
        "sku_table": sku_table,
    }


def _empty_response():
    return {
        "period_label": "", "last_month_label": "",
        "mtd_sales": 0,
        "lmtd_sales": 0,
        "return_on_sales": {
            "good_return": 0, "bad_return": 0,
            "total_returns": 0, "total_sales": 0, "ros_pct": 0,
        },
        "sku_counts": {"today": 0, "today_label": "", "mtd": 0, "ytd": 0},
        "sku_table": [],
    }
