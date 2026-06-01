"""Weekly Sales/Return History report endpoint.
Matches: SP_GetCustomerWeeklyOrderHistoryGraph_Modified / _Amount

Sources:
  - Sales/Returns: rpt_route_sales_by_item_customer (TotalSales, TotalGRSales+Damage+Expiry)
  - Grouped by ISO week
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}
# Summary table supports these filters directly (has brand_code, category_code, sales_org_code)
RSSI_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'brand', 'category'}


@router.get("/weekly-sales-returns")
def get_weekly_sales_returns(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer: Optional[str] = None,
    route: Optional[str] = None,
    channel: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    # Resolve hierarchy
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            user_code = "__NO_MATCH__"
        elif resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code, 'customer': customer,
        'date_from': date_from, 'date_to': date_to,
    }.items() if v is not None}

    # Use RSIC when channel/customer/brand/category filter active — summary table lacks
    # customer/channel columns and only has brand_code='NFPC' (not real brand codes)
    _use_rsic = bool(channel or customer or brand or category)

    if not _use_rsic:
        # ── Summary table path (matches dashboard exactly) ──────────────────
        # rpt_route_sales_summary_by_item: one row per (route, item, date)
        # DISTINCT ON removes any lingering duplicates, same as dashboard
        f_rssi = {k: v for k, v in {
            'route': route, 'user_code': user_code, 'brand': brand, 'category': category,
            'date_from': date_from, 'date_to': date_to,
        }.items() if v is not None}
        sw, sp = build_where(f_rssi, date_col='date')
        org_cond = ""
        org_params = []
        if sales_org:
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            org_cond = f" AND sales_org_code IN ({org_ph})"
            org_params = orgs

        rows = query(
            f"SELECT "
            f"  EXTRACT(ISOYEAR FROM date)::int AS year, "
            f"  EXTRACT(WEEK FROM date)::int AS week_number, "
            f"  MIN(date) AS week_start, "
            f"  MAX(date) AS week_end, "
            f"  COALESCE(SUM(total_sales), 0) AS sales_amount "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) "
            f"  date, total_sales "
            f"  FROM rpt_route_sales_summary_by_item WHERE {sw}{org_cond} "
            f"  ORDER BY route_code, item_code, date) t "
            f"GROUP BY EXTRACT(ISOYEAR FROM date), EXTRACT(WEEK FROM date) "
            f"ORDER BY year, week_number",
            sp + org_params
        )

        # Returns from RSIC (summary table total_wastage is always 0)
        f_ret = {k: v for k, v in {
            'route': route, 'user_code': user_code,
            'date_from': date_from, 'date_to': date_to,
        }.items() if v is not None}
        ret_org_join = ""
        ret_org_params = []
        if sales_org and not route:
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            ret_org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
            ret_org_params = orgs
        rw_ret, rp_ret = build_where(f_ret, date_col='date', prefix='r')
        ret_rows = query(
            f"SELECT EXTRACT(ISOYEAR FROM r.date)::int AS year, "
            f"  EXTRACT(WEEK FROM r.date)::int AS week_number, "
            f"  COALESCE(SUM(r.total_gr_sales + r.total_damage_sales + r.total_expiry_sales), 0) AS return_amount "
            f"FROM rpt_route_sales_by_item_customer r {ret_org_join}"
            f"WHERE {rw_ret} "
            f"GROUP BY EXTRACT(ISOYEAR FROM r.date), EXTRACT(WEEK FROM r.date)",
            ret_org_params + rp_ret
        )
        returns_map = {(r["year"], r["week_number"]): float(r["return_amount"]) for r in ret_rows}
    else:
        # ── RSIC path: required for channel / customer filters ───────────────
        # Resolve sales_org to route JOIN for RSIC tables
        _org_join = ""
        _org_params = []
        if sales_org and not base_filters.get('route'):
            orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph = ','.join(['%s'] * len(orgs))
            _org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
            _org_params = orgs

        # Channel filter — EXISTS on dim_customer
        channel_cond = ""
        channel_params = []
        if channel:
            ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
            ch_ph = ','.join(['%s'] * len(ch_vals))
            channel_cond = (
                f" AND EXISTS (SELECT 1 FROM dim_customer _chdc "
                f"WHERE _chdc.code = r.customer_code AND TRIM(_chdc.channel_code) IN ({ch_ph}))"
            )
            channel_params = ch_vals

        # Brand/Category — JOIN dim_item
        brand_dim_join = ""
        brand_dim_join_params = []
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
            brand_dim_join = f"JOIN dim_item _di ON _di.code = r.item_code AND {' AND '.join(i_conds)} "
            brand_dim_join_params = i_params

        f_rsic = {k: v for k, v in base_filters.items() if k in RSIC_KEYS}
        rw, rp = build_where(f_rsic, date_col='date', prefix='r')

        rows = query(
            f"SELECT "
            f"  EXTRACT(ISOYEAR FROM r.date)::int AS year, "
            f"  EXTRACT(WEEK FROM r.date)::int AS week_number, "
            f"  MIN(r.date) AS week_start, "
            f"  MAX(r.date) AS week_end, "
            f"  COALESCE(SUM(r.total_sales), 0) AS sales_amount, "
            f"  COALESCE(SUM(COALESCE(r.total_gr_sales,0) + COALESCE(r.total_damage_sales,0) "
            f"    + COALESCE(r.total_expiry_sales,0)), 0) AS return_amount "
            f"FROM rpt_route_sales_by_item_customer r {_org_join}{brand_dim_join}"
            f"WHERE {rw}{channel_cond} "
            f"GROUP BY EXTRACT(ISOYEAR FROM r.date), EXTRACT(WEEK FROM r.date) "
            f"ORDER BY year, week_number",
            _org_params + brand_dim_join_params + rp + channel_params
        )

    weekly_data = []
    for row in rows:
        sales = float(row["sales_amount"])
        returns = returns_map.get((row["year"], row["week_number"]), 0) if not _use_rsic else float(row["return_amount"])
        weekly_data.append({
            "year": row["year"],
            "week_number": row["week_number"],
            "week_start": str(row["week_start"]),
            "week_end": str(row["week_end"]),
            "sales_amount": round(sales, 2),
            "return_amount": round(returns, 2),
            "net_amount": round(sales - returns, 2),
            "return_pct": round(returns / sales * 100, 2) if sales else 0,
        })

    total_sales = sum(w["sales_amount"] for w in weekly_data)
    total_returns = sum(w["return_amount"] for w in weekly_data)

    return {
        "weekly_data": weekly_data,
        "totals": {
            "total_sales": round(total_sales, 2),
            "total_returns": round(total_returns, 2),
            "net_amount": round(total_sales - total_returns, 2),
            "return_pct": round(total_returns / total_sales * 100, 2) if total_sales else 0,
        },
    }


@router.get("/weekly-sales-returns/order-items")
def get_order_items(order_no: str):
    rows = query(
        "SELECT DISTINCT ON (sd.line_no, sd.item_code) "
        "  sd.line_no, sd.item_code, sd.item_name, "
        "  COALESCE(TRIM(di.brand_name), sd.brand_name) AS brand_name, "
        "  COALESCE(di.category_name, sd.category_name) AS category_name, "
        "  sd.qty_cases, sd.qty_pieces, sd.base_price, "
        "  sd.gross_amount, sd.discount_amount, "
        "  (sd.gross_amount - sd.discount_amount) AS net_amount "
        "FROM rpt_sales_detail sd "
        "LEFT JOIN dim_item di ON di.code = sd.item_code "
        "WHERE sd.trx_code = %s "
        "ORDER BY sd.line_no, sd.item_code",
        [order_no]
    )
    return [
        {
            "line_no": r["line_no"],
            "item_code": r["item_code"],
            "item_name": r["item_name"],
            "brand": r["brand_name"] or "",
            "category": r["category_name"] or "",
            "qty_cases": float(r["qty_cases"]) if r["qty_cases"] else 0,
            "qty_pieces": float(r["qty_pieces"]) if r["qty_pieces"] else 0,
            "base_price": float(r["base_price"]) if r["base_price"] else 0,
            "gross_amount": float(r["gross_amount"]) if r["gross_amount"] else 0,
            "discount_amount": float(r["discount_amount"]) if r["discount_amount"] else 0,
            "net_amount": float(r["net_amount"]) if r["net_amount"] else 0,
        }
        for r in rows
    ]


def _empty():
    return {
        "weekly_data": [],
        "totals": {"total_sales": 0, "total_returns": 0, "net_amount": 0, "return_pct": 0},
    }


@router.get("/weekly-sales-returns/orders")
def get_order_details(
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer: Optional[str] = None,
    route: Optional[str] = None,
    channel: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    export: bool = False,
):
    # Resolve hierarchy
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return []
        elif resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    if user_code == "__NO_MATCH__":
        return []

    today = date.today()
    d_from = date_from or date(today.year, today.month, 1)
    d_to = date_to or today

    f = {k: v for k, v in {
        'route': route, 'user_code': user_code, 'customer': customer,
        'date_from': d_from, 'date_to': d_to,
    }.items() if v is not None}

    whr, prms = build_where(f, date_col='trx_date', prefix='sd')

    org_cond = ""
    org_params = []
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_cond = f" AND sd.sales_org_code IN ({org_ph})"
        org_params = orgs

    # Channel filter — rpt_sales_detail has channel_code with trailing spaces
    channel_cond = ""
    channel_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        channel_cond = f" AND TRIM(sd.channel_code) IN ({ch_ph})"
        channel_params = ch_vals

    # Brand/Category — EXISTS on dim_item (rpt_sales_detail brand_code not reliable)
    item_cond = ""
    item_params = []
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
        item_cond = f" AND EXISTS (SELECT 1 FROM dim_item _di WHERE _di.code = sd.item_code AND {' AND '.join(i_conds)})"
        item_params = i_params

    # Build inner WHERE (no prefix) to push date/type filter inside CTE
    inner_whr, inner_prms = build_where(f, date_col='trx_date')
    inner_org_cond = org_cond.replace('sd.', '') if org_cond else ""

    rows = query(
        f"WITH deduped AS ("
        f"  SELECT trx_code, line_no, "
        f"    MAX(user_code) AS user_code, MAX(user_name) AS user_name, "
        f"    MAX(customer_code) AS customer_code, MAX(customer_name) AS customer_name, "
        f"    MAX(trx_date) AS trx_date, MAX(route_code) AS route_code, MAX(route_name) AS route_name, "
        f"    MAX(qty_cases) AS qty_cases, MAX(qty_pieces) AS qty_pieces, "
        f"    MAX(gross_amount) AS gross_amount, MAX(discount_amount) AS discount_amount, "
        f"    MAX(trx_type) AS trx_type, MAX(trx_status) AS trx_status, "
        f"    MAX(channel_code) AS channel_code, MAX(item_code) AS item_code "
        f"  FROM rpt_sales_detail "
        f"  WHERE {inner_whr} AND trx_type IN (1,3,4,5){inner_org_cond} "
        f"  GROUP BY trx_code, line_no"
        f"), _grouped AS ("
        f"  SELECT "
        f"    sd.trx_code AS order_no, "
        f"    MAX(sd.user_code) AS salesman_code, "
        f"    MAX(sd.user_name) AS salesman, "
        f"    MAX(sd.customer_code) AS customer_code, "
        f"    TRIM(MAX(sd.customer_name)) AS customer, "
        f"    MAX(sd.trx_date) AS order_date, "
        f"    MAX(sd.route_code) AS route_code, "
        f"    MAX(sd.route_name) AS route, "
        f"    ROUND(SUM(sd.qty_cases)::numeric, 0) AS qty_cases, "
        f"    ROUND(SUM(sd.qty_pieces)::numeric, 0) AS qty_pieces, "
        f"    ROUND(SUM(sd.gross_amount)::numeric, 2) AS gross_amount, "
        f"    ROUND(SUM(sd.discount_amount)::numeric, 2) AS discount_amount, "
        f"    ROUND(SUM(sd.gross_amount - sd.discount_amount)::numeric, 2) AS net_amount, "
        f"    CASE "
        f"      WHEN MAX(sd.trx_type) IN (1,3,5) AND MAX(sd.trx_status) = 200 THEN 'Delivered' "
        f"      WHEN MAX(sd.trx_type) IN (1,3,5) AND MAX(sd.trx_status) = 100 THEN 'Pending' "
        f"      WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 200 THEN 'Approved' "
        f"      WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 400 THEN 'Pending' "
        f"      WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 500 THEN 'Collected' "
        f"      WHEN MAX(sd.trx_status) = -100 THEN 'Rejected' "
        f"      ELSE 'Unknown' "
        f"    END AS action "
        f"  FROM deduped sd "
        f"  WHERE 1=1{channel_cond}{item_cond} "
        f"  GROUP BY sd.trx_code"
        f") "
        f"SELECT *, COUNT(*) OVER() AS total_count FROM _grouped "
        f"ORDER BY order_date DESC"
        + ("" if export else f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"),
        inner_prms + org_params + channel_params + item_params,
    )

    total = int(rows[0]["total_count"]) if rows else 0

    orders = [
        {
            "order_no": r["order_no"],
            "salesman_code": r["salesman_code"],
            "salesman": r["salesman"],
            "customer_code": r["customer_code"],
            "customer": r["customer"],
            "order_date": str(r["order_date"]),
            "route_code": r["route_code"],
            "route": r["route"],
            "qty_cases": int(r["qty_cases"]) if r["qty_cases"] else 0,
            "qty_pieces": int(r["qty_pieces"]) if r["qty_pieces"] else 0,
            "gross_amount": float(r["gross_amount"]) if r["gross_amount"] else 0,
            "discount_amount": float(r["discount_amount"]) if r["discount_amount"] else 0,
            "net_amount": float(r["net_amount"]) if r["net_amount"] else 0,
            "action": r["action"],
        }
        for r in rows
    ]

    if export:
        return orders
    return {"orders": orders, "total": total, "page": page, "page_size": page_size}
