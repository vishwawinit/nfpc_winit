"""Daily Sales Overview report endpoint.
Sources:
  - Sales: rpt_route_sales_by_item_customer (TotalSales, returns breakdown)
  - Cash/Credit: rpt_sales_detail (deduplicated by trx_code for header-level amounts)
  - Calls: rpt_coverage_summary
  - Invoices: rpt_sales_detail (COUNT DISTINCT trx_code)
  - Brand table: rpt_route_sales_by_item_customer joined to dim_item
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


def _empty_response():
    return {
        "sales_details": {"cash_sales": 0, "credit_sales": 0, "total_sales": 0, "discount": 0},
        "call_details": {"total_calls": 0, "selling_calls": 0, "total_invoices": 0},
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

    # Resolve sales_org to user_codes for tables without sales_org_code column
    if sales_org and not filters.get('user_code'):
        from api.database import query as db_query
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = db_query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        if not org_rows:
            return _empty_response()
        filters['user_code'] = ','.join(r['code'] for r in org_rows)
    elif sales_org and filters.get('user_code'):
        from api.database import query as db_query
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = db_query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        org_users = set(r['code'] for r in org_rows)
        existing = set(filters['user_code'].split(','))
        intersected = existing & org_users
        if not intersected:
            return _empty_response()
        filters['user_code'] = ','.join(intersected)

    # Channel filter: resolve to customer_codes via dim_customer
    # rpt_route_sales_by_item_customer has customer_code but no channel_code
    # Channel/SubChannel filter: applied via EXISTS on dim_customer
    # Must match customer_code + sales_org (through route) like MSSQL does
    channel_cond = ""
    channel_params = []
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
            f"  JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code "
            f"  WHERE dc.code = r.customer_code AND dr.code = r.route_code "
            f"  AND {ch_where})"
        )

    # Brand/Category filter: resolve to item_codes via dim_item
    item_filter_cond = ""
    item_filter_params = []
    if brand or category:
        from api.database import query as db_query
        item_conditions = []
        item_params = []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            b_ph = ','.join(['%s'] * len(b_vals))
            item_conditions.append(f"TRIM(brand_code) IN ({b_ph})")
            item_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            c_ph = ','.join(['%s'] * len(c_vals))
            item_conditions.append(f"category_code IN ({c_ph})")
            item_params.extend(c_vals)
        i_where = " AND ".join(item_conditions)
        item_rows = db_query(f"SELECT DISTINCT code FROM dim_item WHERE {i_where}", item_params)
        if not item_rows:
            return _empty_response()
        i_codes = [r['code'] for r in item_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        item_filter_cond = f" AND r.item_code IN ({i_ph})"
        item_filter_params = i_codes

    # --- Total Sales from rpt_route_sales_by_item_customer ---
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date')
    sales_total_row = query_one(
        f"SELECT COALESCE(SUM(r.total_sales),0) AS total_sales "
        f"FROM rpt_route_sales_by_item_customer r WHERE {rw}{channel_cond}{item_filter_cond}",
        rp + channel_params + item_filter_params
    )
    total_sales = float(sales_total_row["total_sales"]) if sales_total_row else 0

    # --- Cash/Credit/Discount from rpt_sales_detail ---
    # Deduplicate by trx_code (net_amount is header-level, repeated per detail line)
    # Only count invoices that have matching entries in rpt_route_sales_by_item_customer (TRXStatus=200)
    f_sd = {k: v for k, v in filters.items() if k in SALES_DETAIL_KEYS}
    sw, sp = build_where(f_sd, date_col='trx_date')

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

    # net_amount = header-level (same for all lines in a trx, dedup by trx_code)
    # discount_amount = line-level (varies per line, dedup by trx_code+line_no then SUM)
    cash_credit_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '1' THEN net_amount ELSE 0 END), 0) AS cash_sales, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '0' THEN net_amount ELSE 0 END), 0) AS credit_sales "
        f"FROM (SELECT sd.trx_code, MIN(sd.payment_type) AS payment_type, MIN(sd.net_amount) AS net_amount "
        f"  FROM rpt_sales_detail sd "
        f"  WHERE sd.trx_type = 1 AND sd.trx_status = 200 AND {sw}{extra_where} "
        f"  GROUP BY sd.trx_code "
        f") t",
        sp + extra_params
    )
    cash_sales = float(cash_credit_row["cash_sales"]) if cash_credit_row else 0
    credit_sales = float(cash_credit_row["credit_sales"]) if cash_credit_row else 0

    # Discount: SUM of per-line discounts (dedup by trx_code+line_no first)
    disc_row = query_one(
        f"SELECT COALESCE(SUM(discount_amount), 0) AS discount "
        f"FROM (SELECT DISTINCT trx_code, line_no, discount_amount "
        f"  FROM rpt_sales_detail "
        f"  WHERE trx_type = 1 AND trx_status = 200 AND {sw}{extra_where}) t",
        sp + extra_params
    )
    discount = float(disc_row["discount"]) if disc_row else 0

    sales_details = {
        "cash_sales": cash_sales,
        "credit_sales": credit_sales,
        "total_sales": total_sales,
        "discount": discount,
    }

    # --- Call Details from rpt_coverage_summary ---
    f_cov = {k: v for k, v in filters.items() if k in COVERAGE_KEYS}
    cw, cp = build_where(f_cov, date_col='visit_date')
    call_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(total_actual_calls), 0) AS total_calls, "
        f"  COALESCE(SUM(selling_calls), 0) AS selling_calls "
        f"FROM rpt_coverage_summary WHERE {cw}", cp
    )

    # Total invoices (TrxType=1, TRXStatus=200)
    inv_row = query_one(
        f"SELECT COUNT(DISTINCT trx_code) AS total_invoices "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND trx_status = 200 AND {sw}{extra_where}",
        sp + extra_params
    )

    call_details = {
        "total_calls": int(call_row["total_calls"]) if call_row else 0,
        "selling_calls": int(call_row["selling_calls"]) if call_row else 0,
        "total_invoices": int(inv_row["total_invoices"]) if inv_row else 0,
    }

    # --- Item Table from rpt_route_sales_by_item_customer + dim_item ---
    # Matches: SP_SalesOverVieweReport_V1
    # Returns item-level: ItemCode, ItemName, GrossSales (selected period),
    #   MTD_GrossSales, MTD_Wastage (GR+Damage+Expiry)
    # MTD = full month (matches MSSQL SP: MONTH(Date)=M AND YEAR(Date)=Y)
    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    if ref_date.month == 12:
        mtd_end = date(ref_date.year, 12, 31)
    else:
        mtd_end = date(ref_date.year, ref_date.month + 1, 1) - timedelta(days=1)

    f_rsic2 = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw2, rp2 = build_where(f_rsic2, date_col='date', prefix='r')
    f_mtd = {k: v for k, v in {**{k2: v2 for k2, v2 in filters.items() if k2 not in ('date_from', 'date_to')},
              'date_from': mtd_start, 'date_to': mtd_end}.items() if k in RSIC_KEYS}
    mw, mp = build_where(f_mtd, date_col='date', prefix='r')

    item_table = query(
        f"SELECT "
        f"  r.item_code, "
        f"  COALESCE(di.name, r.item_code) AS item_name, "
        f"  TRIM(di.brand_code) AS brand_code, "
        f"  COALESCE(di.brand_name, di.brand_code) AS brand_name, "
        f"  di.category_code, "
        f"  COALESCE(di.category_name, di.category_code) AS category_name, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS gross_sales, "
        f"  0 AS target_sales, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END)::numeric, 2) AS mtd_gross_sales, "
        f"  0 AS mtd_target_sales, "
        f"  ROUND(SUM(CASE WHEN r.date BETWEEN %s AND %s "
        f"    THEN COALESCE(r.total_gr_sales,0) + COALESCE(r.total_damage_sales,0) + COALESCE(r.total_expiry_sales,0) "
        f"    ELSE 0 END)::numeric, 2) AS mtd_wastage "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_item di ON r.item_code = di.code "
        f"WHERE ({rw2} OR {mw}){channel_cond}{item_filter_cond} "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), "
        f"  TRIM(di.brand_code), COALESCE(di.brand_name, di.brand_code), "
        f"  di.category_code, COALESCE(di.category_name, di.category_code) "
        f"ORDER BY gross_sales DESC",
        [date_from, date_to, mtd_start, mtd_end, mtd_start, mtd_end] + rp2 + mp + channel_params + item_filter_params
    )

    for row in item_table:
        row["variance"] = float(row["gross_sales"])
        row["mtd_variance"] = float(row["mtd_gross_sales"])

    return {
        "sales_details": sales_details,
        "call_details": call_details,
        "item_table": item_table,
    }
