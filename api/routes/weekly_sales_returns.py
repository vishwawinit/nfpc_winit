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

    # Resolve sales_org to route JOIN for RSIC tables
    _org_join = ""
    _org_params = []
    if sales_org and not base_filters.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _org_params = orgs

    # Channel filter
    channel_cond = ""
    channel_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        cust_rows = query(
            f"SELECT DISTINCT dc.code FROM dim_customer dc "
            f"JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code "
            f"WHERE TRIM(dc.channel_code) IN ({ch_ph})", ch_vals
        )
        if not cust_rows:
            return _empty()
        c_codes = [r['code'] for r in cust_rows]
        c_ph = ','.join(['%s'] * len(c_codes))
        channel_cond = f" AND r.customer_code IN ({c_ph})"
        channel_params = c_codes

    # Brand/Category filter
    item_cond = ""
    item_params = []
    if brand or category:
        i_conditions = []
        i_params = []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            b_ph = ','.join(['%s'] * len(b_vals))
            i_conditions.append(f"TRIM(brand_code) IN ({b_ph})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            c_ph = ','.join(['%s'] * len(c_vals))
            i_conditions.append(f"category_code IN ({c_ph})")
            i_params.extend(c_vals)
        i_where = " AND ".join(i_conditions)
        i_rows = query(f"SELECT DISTINCT code FROM dim_item WHERE {i_where}", i_params)
        if not i_rows:
            return _empty()
        i_codes = [r['code'] for r in i_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        item_cond = f" AND r.item_code IN ({i_ph})"
        item_params = i_codes

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
        f"FROM rpt_route_sales_by_item_customer r {_org_join}"
        f"WHERE {rw}{channel_cond}{item_cond} "
        f"GROUP BY EXTRACT(ISOYEAR FROM r.date), EXTRACT(WEEK FROM r.date) "
        f"ORDER BY year, week_number",
        _org_params + rp + channel_params + item_params
    )

    weekly_data = []
    for row in rows:
        sales = float(row["sales_amount"])
        returns = float(row["return_amount"])
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

    # Brand/Category — rpt_sales_detail brand_code is not reliable; resolve via dim_item
    item_cond = ""
    item_params = []
    if brand or category:
        i_conditions = []
        i_params = []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            b_ph = ','.join(['%s'] * len(b_vals))
            i_conditions.append(f"TRIM(brand_code) IN ({b_ph})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            c_ph = ','.join(['%s'] * len(c_vals))
            i_conditions.append(f"category_code IN ({c_ph})")
            i_params.extend(c_vals)
        i_rows = query(f"SELECT DISTINCT code FROM dim_item WHERE {' AND '.join(i_conditions)}", i_params)
        if not i_rows:
            return []
        i_codes = [r['code'] for r in i_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        item_cond = f" AND sd.item_code IN ({i_ph})"
        item_params = i_codes

    rows = query(
        f"SELECT "
        f"  sd.trx_code AS order_no, "
        f"  MAX(sd.user_name) AS salesman, "
        f"  TRIM(MAX(sd.customer_name)) AS customer, "
        f"  MAX(sd.trx_date) AS order_date, "
        f"  MAX(sd.route_name) AS route, "
        f"  ROUND(SUM(sd.qty_cases)::numeric, 0) AS qty_cases, "
        f"  ROUND(SUM(sd.qty_pieces)::numeric, 0) AS qty_pieces, "
        f"  ROUND(SUM(sd.gross_amount)::numeric, 2) AS gross_amount, "
        f"  ROUND(SUM(sd.discount_amount)::numeric, 2) AS discount_amount, "
        f"  ROUND(SUM(sd.gross_amount - sd.discount_amount)::numeric, 2) AS net_amount, "
        f"  CASE "
        f"    WHEN MAX(sd.trx_type) IN (1,3,5) AND MAX(sd.trx_status) = 200 THEN 'Delivered' "
        f"    WHEN MAX(sd.trx_type) IN (1,3,5) AND MAX(sd.trx_status) = 100 THEN 'Pending' "
        f"    WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 200 THEN 'Approved' "
        f"    WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 400 THEN 'Pending' "
        f"    WHEN MAX(sd.trx_type) = 4 AND MAX(sd.trx_status) = 500 THEN 'Collected' "
        f"    WHEN MAX(sd.trx_status) = -100 THEN 'Rejected' "
        f"    ELSE 'Unknown' "
        f"  END AS action "
        f"FROM (SELECT DISTINCT ON (trx_code, line_no) * FROM rpt_sales_detail) sd "
        f"WHERE {whr}{org_cond}{channel_cond}{item_cond} AND sd.trx_type IN (1,3,4,5) "
        f"GROUP BY sd.trx_code "
        f"ORDER BY MAX(sd.trx_date) DESC",
        prms + org_params + channel_params + item_params
    )

    return [
        {
            "order_no": r["order_no"],
            "salesman": r["salesman"],
            "customer": r["customer"],
            "order_date": str(r["order_date"]),
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
