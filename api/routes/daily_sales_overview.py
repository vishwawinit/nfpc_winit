"""Daily Sales Overview report endpoint.
Sources (matches SP_SalesOverVieweReport_Part2 + V1):
  - Cash/Credit/Total Sales: rpt_route_sales_by_item_customer + dim_customer
  - Discount/Invoices: rpt_sales_detail
  - Calls: rpt_coverage_summary
  - Prod. Minutes: rpt_customer_visits (productive only — joined to invoices)
  - Total Cash Due: rpt_outstanding (pending_amount)
  - Item table: rpt_route_sales_by_item_customer + dim_item
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}
COVERAGE_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
SALES_DETAIL_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
VISIT_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}
OUTSTANDING_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


def _empty_response():
    return {
        "call_summary": {"total_calls": 0, "total_invoices": 0},
        "sales_details": {
            "prod_minutes": 0, "cash_sales": 0, "credit_sales": 0,
            "daily_sales": 0, "total_returns": 0, "discount": 0,
            "invoice_short": 0, "total_cash_due": 0,
        },
        "item_table": [],
    }


@router.get("/daily-sales-overview")
def get_daily_sales_overview(
    area: Optional[str] = None,
    route_type: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    channel: Optional[str] = None,
    sub_channel: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy filters
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return _empty_response()
        if resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                if not intersected:
                    return _empty_response()
                user_code = ','.join(intersected)
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # Resolve sales_org to route_codes for RSIC tables (no sales_org_code column)
    _rsic_org_join = ""
    _rsic_org_params = []
    if sales_org and not filters.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _rsic_org_join = f"JOIN dim_route _dr ON {{alias}}.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _rsic_org_params = orgs

    # Channel/SubChannel filter: applied via EXISTS on dim_customer
    # rpt_route_sales_by_item_customer has customer_code but no channel_code
    channel_cond = ""
    channel_params = []
    sd_channel_cond = ""  # for rpt_sales_detail (discount/invoice queries)
    if channel or sub_channel:
        ch_conditions = []
        if channel:
            ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
            ch_ph = ','.join(['%s'] * len(ch_vals))
            ch_conditions.append(f"TRIM(dc.channel_code) IN ({ch_ph})")
            channel_params.extend(ch_vals)
        if sub_channel:
            sc_vals = [v.strip() for v in sub_channel.split(',') if v.strip()]
            sc_ph = ','.join(['%s'] * len(sc_vals))
            ch_conditions.append(f"TRIM(dc.sub_channel_code) IN ({sc_ph})")
            channel_params.extend(sc_vals)
        ch_where = " AND ".join(ch_conditions)
        channel_cond = (
            f" AND EXISTS (SELECT 1 FROM dim_customer dc "
            f"  WHERE dc.code = r.customer_code AND {ch_where})"
        )
        sd_channel_cond = (
            f" AND EXISTS (SELECT 1 FROM dim_customer dc "
            f"  WHERE dc.code = customer_code AND {ch_where})"
        )

    # Brand/Category → JOIN dim_item (avoids item-code format mismatch with RSIC table)
    # _brand_dim_join: for RSIC queries (alias _di, no existing dim_item join)
    # _brand_on_di_cond / _brand_di_params: for item_table (already uses LEFT JOIN dim_item di)
    # sd_brand_cond: for rpt_sales_detail queries (discount, invoice)
    _brand_dim_join = ""
    _brand_dim_join_params = []
    _brand_on_di_cond = ""
    _brand_di_params = []
    sd_brand_cond = ""
    sd_brand_params = []
    if brand or category:
        i_conds, i_params = [], []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            i_conds.append(f"TRIM(_di.brand_code) IN ({','.join(['%s'] * len(b_vals))})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            i_conds.append(f"_di.category_code IN ({','.join(['%s'] * len(c_vals))})")
            i_params.extend(c_vals)
        _brand_dim_join = f"JOIN dim_item _di ON _di.code = r.item_code AND {' AND '.join(i_conds)} "
        _brand_dim_join_params = i_params
        # Same conditions referencing existing 'di' alias (item_table)
        di_conds = [c.replace('_di.', 'di.') for c in i_conds]
        _brand_on_di_cond = " AND " + " AND ".join(di_conds)
        _brand_di_params = i_params[:]
        # For rpt_sales_detail queries (no r. alias, item_code is direct column)
        sd_conds = [c.replace('_di.', '_sdi.') for c in i_conds]
        sd_brand_cond = f" AND EXISTS (SELECT 1 FROM dim_item _sdi WHERE _sdi.code = item_code AND {' AND '.join(sd_conds)})"
        sd_brand_params = i_params[:]

    # org_join for queries on rpt_route_sales_by_item_customer
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')
    org_join = _rsic_org_join.replace("{alias}", "r") if _rsic_org_join else ""

    # Additional area/route_type filters
    extra_conds = []
    extra_params = []
    if area:
        extra_conds.append("area_code = %s")
        extra_params.append(area)
    if route_type:
        extra_conds.append("route_type = %s")
        extra_params.append(route_type)
    extra_where = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

    f_sd = {k: v for k, v in filters.items() if k in SALES_DETAIL_KEYS}
    sw, sp = build_where(f_sd, date_col='trx_date')

    # --- Step 1: RSIC cash/credit proportion (dim_customer.customer_type) ---
    # Used only to derive the cash vs credit split ratio — NOT the totals.
    try:
        f_rsic_cc = {k: v for k, v in filters.items() if k in RSIC_KEYS}
        ccw, ccp = build_where(f_rsic_cc, date_col='date', prefix='r')
        cc_join = _rsic_org_join.replace("{alias}", "r") if _rsic_org_join else ""
        cc_row = query_one(
            f"SELECT "
            f"  COALESCE(SUM(CASE WHEN COALESCE(dc.customer_type,'Cash') != 'Credit' THEN r.total_sales ELSE 0 END), 0) AS rsic_cash, "
            f"  COALESCE(SUM(CASE WHEN dc.customer_type = 'Credit' THEN r.total_sales ELSE 0 END), 0) AS rsic_credit "
            f"FROM rpt_route_sales_by_item_customer r "
            f"LEFT JOIN (SELECT DISTINCT ON (code) code, customer_type FROM dim_customer ORDER BY code) dc ON dc.code = r.customer_code "
            f"{cc_join}{_brand_dim_join}"
            f"WHERE {ccw}{channel_cond}",
            _rsic_org_params + _brand_dim_join_params + ccp + channel_params
        )
        rsic_cash = float(cc_row["rsic_cash"]) if cc_row else 0
        rsic_credit = float(cc_row["rsic_credit"]) if cc_row else 0
    except Exception:
        rsic_cash = 0
        rsic_credit = 0

    # --- Step 2: Total Returns from RSIC (RSSI has no returns columns) ---
    try:
        f_rsic_ret = {k: v for k, v in filters.items() if k in RSIC_KEYS}
        retw, retp = build_where(f_rsic_ret, date_col='date', prefix='r')
        ret_join = _rsic_org_join.replace("{alias}", "r") if _rsic_org_join else ""
        ret_row = query_one(
            f"SELECT COALESCE(SUM(COALESCE(r.total_gr_sales,0) + COALESCE(r.total_damage_sales,0) + COALESCE(r.total_expiry_sales,0)), 0) AS total_returns "
            f"FROM rpt_route_sales_by_item_customer r "
            f"{ret_join}{_brand_dim_join}"
            f"WHERE {retw}{channel_cond}",
            _rsic_org_params + _brand_dim_join_params + retp + channel_params
        )
        total_returns = float(ret_row["total_returns"]) if ret_row else 0
    except Exception:
        total_returns = 0

    # --- Step 3: Daily Sales total from RSSI (same source as Dashboard & Sales Performance KPI) ---
    # When channel/brand/category active: RSSI lacks those columns → fall back to RSIC sum.
    _use_rsic_total = bool(channel or sub_channel or brand or category)
    if not _use_rsic_total:
        try:
            f_rssi = {k: v for k, v in {
                'route': route, 'user_code': user_code,
                'date_from': date_from, 'date_to': date_to,
            }.items() if v is not None}
            sw_s, sp_s = build_where(f_rssi, date_col='date')
            org_cond_s = ""
            org_params_s = []
            if sales_org:
                orgs_s = [v.strip() for v in sales_org.split(',') if v.strip()]
                org_ph_s = ','.join(['%s'] * len(orgs_s))
                org_cond_s = f" AND sales_org_code IN ({org_ph_s})"
                org_params_s = orgs_s
            rssi_row = query_one(
                f"SELECT COALESCE(SUM(total_sales), 0) AS total_sales "
                f"FROM (SELECT DISTINCT ON (route_code, item_code, date) total_sales "
                f"  FROM rpt_route_sales_summary_by_item WHERE {sw_s}{org_cond_s} "
                f"  ORDER BY route_code, item_code, date) t",
                sp_s + org_params_s
            )
            total_sales = float(rssi_row["total_sales"]) if rssi_row else 0
            if total_sales == 0:
                f_it = {k: v for k, v in {
                    'route': route, 'user_code': user_code, 'sales_org': sales_org,
                    'date_from': date_from, 'date_to': date_to,
                }.items() if v is not None}
                itw, itp = build_where(f_it, date_col='trx_date')
                it_row = query_one(
                    f"SELECT COALESCE(SUM(total_sales),0) AS total_sales, "
                    f"  COALESCE(SUM(total_returns),0) AS total_returns "
                    f"FROM rpt_invoice_totals WHERE {itw}", itp
                )
                if it_row:
                    total_sales = max(0.0, float(it_row["total_sales"]) - float(it_row["total_returns"]))
        except Exception:
            total_sales = rsic_cash + rsic_credit
    else:
        total_sales = rsic_cash + rsic_credit

    # --- Step 4: Derive cash/credit from RSSI total using RSIC proportion ---
    # All three KPIs now share the same RSSI base: cash + credit = daily_sales always.
    rsic_sum = rsic_cash + rsic_credit
    if rsic_sum > 0 and total_sales > 0:
        cash_sales = round(total_sales * rsic_cash / rsic_sum, 2)
        credit_sales = round(total_sales - cash_sales, 2)
    elif total_sales > 0:
        cash_sales = round(total_sales, 2)
        credit_sales = 0.0
    else:
        cash_sales = 0.0
        credit_sales = 0.0

    # Discount: SUM of line-level discounts (dedup by trx_code+line_no to avoid ETL duplicates)
    # SUM of all detail discounts per trx = header TotalDiscountAmount
    # trx_type IN (1,4) AND trx_status=200 (matches SP)
    try:
        disc_row = query_one(
            f"SELECT COALESCE(SUM(discount_amount), 0) AS discount "
            f"FROM (SELECT DISTINCT trx_code, line_no, discount_amount FROM rpt_sales_detail "
            f"  WHERE trx_type IN (1, 4) AND trx_status = 200 AND {sw}{extra_where}{sd_channel_cond}{sd_brand_cond}) t",
            sp + extra_params + channel_params + sd_brand_params
        )
        discount = float(disc_row["discount"]) if disc_row else 0
    except Exception:
        discount = 0

    # --- Call Summary: Total Calls (rpt_coverage_summary) + Total Invoices (rpt_sales_detail) ---
    # Matches SP Part2: Call Summary section
    try:
        f_cov = {k: v for k, v in filters.items() if k in COVERAGE_KEYS}
        cw, cp = build_where(f_cov, date_col='visit_date')
        call_row = query_one(
            f"SELECT COALESCE(SUM(total_actual_calls), 0) AS total_calls "
            f"FROM rpt_coverage_summary WHERE {cw}", cp
        )
        total_calls = int(call_row["total_calls"]) if call_row else 0
    except Exception:
        total_calls = 0

    try:
        inv_row = query_one(
            f"SELECT COUNT(DISTINCT trx_code) AS total_invoices "
            f"FROM rpt_sales_detail "
            f"WHERE trx_type IN (1, 4) AND trx_status = 200 AND {sw}{extra_where}{sd_channel_cond}{sd_brand_cond}",
            sp + extra_params + channel_params + sd_brand_params
        )
        total_invoices = int(inv_row["total_invoices"]) if inv_row else 0
    except Exception:
        total_invoices = 0

    call_summary = {
        "total_calls": total_calls,
        "total_invoices": total_invoices,
    }

    # --- Prod. Minutes: SUM(total_time_mins) for productive visits ---
    # Matches SP Part2: JOIN tblCustomerVisit with DISTINCT(ClientCode,UserCode,VisitCode,TrxCode)
    # The SP uses DISTINCT TrxDate (datetime) so one visit with multiple invoices is counted N times.
    # We replicate this by joining on DISTINCT trx_code — each matching invoice counts the visit once.
    try:
        f_vis = {k: v for k, v in filters.items() if k in VISIT_KEYS}
        vw, vp = build_where(f_vis, date_col='date', prefix='cv')
        # Build matching date filter for rpt_sales_detail
        sd_date_conds = []
        sd_date_params = []
        if filters.get('date_from'):
            sd_date_conds.append("sd.trx_date::date >= %s")
            sd_date_params.append(filters['date_from'])
        if filters.get('date_to'):
            sd_date_conds.append("sd.trx_date::date <= %s")
            sd_date_params.append(filters['date_to'])
        if filters.get('user_code'):
            u_vals = [v.strip() for v in str(filters['user_code']).split(',') if v.strip()]
            sd_date_conds.append(f"sd.user_code IN ({','.join(['%s']*len(u_vals))})")
            sd_date_params.extend(u_vals)
        if filters.get('route'):
            r_vals = [v.strip() for v in str(filters['route']).split(',') if v.strip()]
            sd_date_conds.append(f"sd.route_code IN ({','.join(['%s']*len(r_vals))})")
            sd_date_params.extend(r_vals)
        if filters.get('sales_org'):
            o_vals = [v.strip() for v in str(filters['sales_org']).split(',') if v.strip()]
            sd_date_conds.append(f"sd.sales_org_code IN ({','.join(['%s']*len(o_vals))})")
            sd_date_params.extend(o_vals)
        sd_where = (" AND " + " AND ".join(sd_date_conds)) if sd_date_conds else ""
        prod_min_row = query_one(
            f"SELECT COALESCE(SUM(cv.total_time_mins), 0) AS prod_minutes "
            f"FROM rpt_customer_visits cv "
            f"JOIN ("
            f"  SELECT DISTINCT sd.visit_code, sd.user_code, sd.trx_code "
            f"  FROM rpt_sales_detail sd "
            f"  WHERE sd.trx_type IN (1, 4) AND sd.trx_status = 200 "
            f"  AND sd.visit_code IS NOT NULL AND sd.visit_code != '' "
            f"  {sd_where}"
            f") sd ON sd.visit_code = cv.visit_code AND sd.user_code = cv.user_code "
            f"WHERE {vw}",
            sd_date_params + vp
        )
        prod_minutes = float(prod_min_row["prod_minutes"]) if prod_min_row else 0
    except Exception:
        prod_minutes = 0

    # --- Total Cash Due: SUM(pending_amount) from rpt_outstanding ---
    # Matches SP Part2: tblMiddlewarePendingInvoice.PendingAmount by date range
    try:
        f_out = {k: v for k, v in filters.items() if k in OUTSTANDING_KEYS}
        ow, op = build_where(f_out, date_col='trx_date')
        cash_due_row = query_one(
            f"SELECT COALESCE(SUM(pending_amount), 0) AS total_cash_due "
            f"FROM rpt_outstanding WHERE {ow}",
            op
        )
        total_cash_due = float(cash_due_row["total_cash_due"]) if cash_due_row else 0
    except Exception:
        total_cash_due = 0

    # invoice_short: SP Part2 sets @InvoiceShort = COUNT(1) same as @TotalInvoice
    sales_details = {
        "prod_minutes": round(prod_minutes, 2),
        "cash_sales": round(cash_sales, 2),
        "credit_sales": round(credit_sales, 2),
        "daily_sales": round(total_sales, 2),
        "total_returns": round(total_returns, 2),
        "discount": round(discount, 2),
        "invoice_short": total_invoices,
        "total_cash_due": round(total_cash_due, 2),
    }

    # --- Item Table ---
    # gross_sales / mtd_gross_sales: RSSI DISTINCT ON — same source as Daily Sales KPI
    #   so summing item gross_sales == Daily Sales KPI total.
    # mtd_wastage: RSIC only (RSSI has no returns/damage/expiry columns).
    # When channel/brand/category filter active: RSSI can't filter those columns,
    #   so fall back to RSIC for all sales columns (mirrors daily_sales fallback).
    ref_date = date_from or date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    if ref_date.month == 12:
        mtd_end = date(ref_date.year, 12, 31)
    else:
        mtd_end = date(ref_date.year, ref_date.month + 1, 1) - timedelta(days=1)

    try:
        if not _use_rsic_total:
            # --- RSSI path: item sales from same source as KPI ---
            f_rssi_p = {k: v for k, v in {
                'route': route, 'user_code': user_code,
                'date_from': date_from, 'date_to': date_to,
            }.items() if v is not None}
            sw_p, sp_p = build_where(f_rssi_p, date_col='date')

            f_rssi_m = {k: v for k, v in {
                'route': route, 'user_code': user_code,
                'date_from': mtd_start, 'date_to': mtd_end,
            }.items() if v is not None}
            sw_m, sp_m = build_where(f_rssi_m, date_col='date')

            org_cond_it = ""
            org_params_it = []
            if sales_org:
                orgs_it = [v.strip() for v in sales_org.split(',') if v.strip()]
                org_ph_it = ','.join(['%s'] * len(orgs_it))
                org_cond_it = f" AND sales_org_code IN ({org_ph_it})"
                org_params_it = orgs_it

            period_rows = query(
                f"SELECT item_code, ROUND(SUM(total_sales)::numeric, 2) AS gross_sales "
                f"FROM (SELECT DISTINCT ON (route_code, item_code, date) item_code, total_sales "
                f"  FROM rpt_route_sales_summary_by_item WHERE {sw_p}{org_cond_it} "
                f"  ORDER BY route_code, item_code, date) t "
                f"GROUP BY item_code",
                sp_p + org_params_it
            )
            mtd_rows = query(
                f"SELECT item_code, ROUND(SUM(total_sales)::numeric, 2) AS mtd_gross_sales "
                f"FROM (SELECT DISTINCT ON (route_code, item_code, date) item_code, total_sales "
                f"  FROM rpt_route_sales_summary_by_item WHERE {sw_m}{org_cond_it} "
                f"  ORDER BY route_code, item_code, date) t "
                f"GROUP BY item_code",
                sp_m + org_params_it
            )

            # MTD wastage from RSIC (RSSI has no returns data)
            f_rsic_wst = {k: v for k, v in {
                'route': route, 'user_code': user_code,
                'date_from': mtd_start, 'date_to': mtd_end,
            }.items() if v is not None}
            ww, wp = build_where(f_rsic_wst, date_col='date', prefix='r')
            wst_org_join = _rsic_org_join.replace("{alias}", "r") if _rsic_org_join else ""
            wastage_rows = query(
                f"SELECT r.item_code, "
                f"  ROUND(SUM(COALESCE(r.total_gr_sales,0) + COALESCE(r.total_damage_sales,0)"
                f"    + COALESCE(r.total_expiry_sales,0))::numeric, 2) AS mtd_wastage "
                f"FROM rpt_route_sales_by_item_customer r {wst_org_join}"
                f"WHERE {ww} GROUP BY r.item_code",
                _rsic_org_params + wp
            )

            period_map = {r['item_code']: float(r['gross_sales'] or 0) for r in period_rows}
            mtd_map = {r['item_code']: float(r['mtd_gross_sales'] or 0) for r in mtd_rows}
            wastage_map = {r['item_code']: float(r['mtd_wastage'] or 0) for r in wastage_rows}

            all_codes = sorted(
                set(period_map.keys()) | set(mtd_map.keys()),
                key=lambda c: -period_map.get(c, 0)
            )

            if all_codes:
                dim_rows = query(
                    f"SELECT code, COALESCE(name, code) AS item_name, "
                    f"  TRIM(COALESCE(brand_name, brand_code, '')) AS brand_name "
                    f"FROM dim_item WHERE code IN ({','.join(['%s'] * len(all_codes))})",
                    all_codes
                )
                dim_map = {r['code']: r for r in dim_rows}
            else:
                dim_map = {}

            item_table = []
            for code in all_codes:
                gross = period_map.get(code, 0)
                mtd_gross = mtd_map.get(code, 0)
                wastage = wastage_map.get(code, 0)
                if gross == 0 and mtd_gross == 0 and wastage == 0:
                    continue
                di = dim_map.get(code, {})
                item_table.append({
                    'item_code': code,
                    'item_name': di.get('item_name') or code,
                    'brand_name': di.get('brand_name', ''),
                    'gross_sales': round(gross, 2),
                    'mtd_gross_sales': round(mtd_gross, 2),
                    'mtd_wastage': round(wastage, 2),
                })

            # RSSI returned no item rows — fall back to RSIC (mirrors daily_sales KPI fallback)
            if not item_table:
                _use_rsic_total = True

        if _use_rsic_total:
            # --- RSIC path: channel/brand/category filter active OR RSSI has no item data ---
            f_rsic2 = {k: v for k, v in filters.items() if k in RSIC_KEYS}
            rw2, rp2 = build_where(f_rsic2, date_col='date', prefix='r')
            f_rsic_mtd = {k: v for k, v in {
                **{k2: v2 for k2, v2 in filters.items() if k2 not in ('date_from', 'date_to') and k2 in RSIC_KEYS},
                'date_from': mtd_start, 'date_to': mtd_end,
            }.items() if v is not None}
            mw2, mp2 = build_where(f_rsic_mtd, date_col='date', prefix='r')
            _item_join_type = "JOIN" if _brand_on_di_cond else "LEFT JOIN"
            item_table = query(
                f"SELECT "
                f"  r.item_code, "
                f"  COALESCE(di.name, r.item_code) AS item_name, "
                f"  TRIM(COALESCE(di.brand_name, di.brand_code, '')) AS brand_name, "
                f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS gross_sales, "
                f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS mtd_gross_sales, "
                f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s "
                f"    THEN COALESCE(r.total_gr_sales,0) + COALESCE(r.total_damage_sales,0) + COALESCE(r.total_expiry_sales,0) "
                f"    ELSE 0 END)::numeric, 2) AS mtd_wastage "
                f"FROM rpt_route_sales_by_item_customer r "
                f"{_item_join_type} dim_item di ON r.item_code = di.code{_brand_on_di_cond} "
                f"{org_join}"
                f"WHERE ({rw2} OR {mw2}){channel_cond} "
                f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), "
                f"  TRIM(COALESCE(di.brand_name, di.brand_code, '')) "
                f"ORDER BY gross_sales DESC",
                [date_from, date_to, mtd_start, mtd_end, mtd_start, mtd_end]
                + _brand_di_params + _rsic_org_params + rp2 + mp2 + channel_params
            )
    except Exception:
        item_table = []

    return {
        "call_summary": call_summary,
        "sales_details": sales_details,
        "item_table": item_table,
    }
