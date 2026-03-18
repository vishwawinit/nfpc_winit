"""Top Products report endpoint.
Matches: SP_tblItem_SelTopItemsByFilter

Source: rpt_route_sales_by_item_customer (single month, top N by sales)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


@router.get("/top-products")
def get_top_products(
    customer: Optional[str] = None,
    user_code: Optional[str] = None,
    sales_org: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    route: Optional[str] = None,
    channel: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    limit: int = Query(100, description="Max rows to return"),
):
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return {"data": []}
        if resolved:
            if user_code:
                intersected = set(user_code.split(',')) & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month
    cur_start = date(cur_year, cur_month, 1)
    cur_end = date(cur_year, 12, 31) if cur_month == 12 else date(cur_year, cur_month + 1, 1) - timedelta(days=1)

    base_filters = {k: v for k, v in {'route': route, 'user_code': user_code, 'customer': customer}.items() if v}

    # Resolve sales_org
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs)
        if not org_rows:
            return {"data": []}
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            intersected = set(base_filters['user_code'].split(',')) & org_users
            if not intersected:
                return {"data": []}
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

    # Channel → customer filter
    channel_cond = ""
    channel_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        cust_rows = query(
            f"SELECT DISTINCT dc.code FROM dim_customer dc "
            f"JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code "
            f"WHERE TRIM(dc.channel_code) IN ({ch_ph})", ch_vals)
        if not cust_rows:
            return {"data": []}
        c_codes = [r['code'] for r in cust_rows]
        c_ph = ','.join(['%s'] * len(c_codes))
        channel_cond = f" AND r.customer_code IN ({c_ph})"
        channel_params = c_codes

    # Brand/Category → item filter
    item_cond = ""
    item_params = []
    if brand or category:
        i_conds, i_params = [], []
        if brand:
            b_vals = [v.strip() for v in brand.split(',') if v.strip()]
            i_conds.append(f"TRIM(brand_code) IN ({','.join(['%s']*len(b_vals))})")
            i_params.extend(b_vals)
        if category:
            c_vals = [v.strip() for v in category.split(',') if v.strip()]
            i_conds.append(f"category_code IN ({','.join(['%s']*len(c_vals))})")
            i_params.extend(c_vals)
        i_rows = query(f"SELECT DISTINCT code FROM dim_item WHERE {' AND '.join(i_conds)}", i_params)
        if not i_rows:
            return {"data": []}
        codes = [r['code'] for r in i_rows]
        item_cond = f" AND r.item_code IN ({','.join(['%s']*len(codes))})"
        item_params = codes

    f_rsic = {**base_filters, 'date_from': cur_start, 'date_to': cur_end}
    f = {k: v for k, v in f_rsic.items() if k in RSIC_KEYS}
    rw, rp = build_where(f, date_col='date', prefix='r')

    rows = query(
        f"SELECT r.item_code, "
        f"  COALESCE(di.name, r.item_code) AS item_name, "
        f"  COALESCE(di.brand_name, di.brand_code) AS brand_name, "
        f"  COALESCE(di.category_name, di.category_code) AS category_name, "
        f"  ROUND(SUM(r.total_sales)::numeric, 2) AS total_sales, "
        f"  ROUND(SUM(r.total_qty)::numeric, 0) AS total_qty "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_item di ON r.item_code = di.code "
        f"WHERE {rw}{channel_cond}{item_cond} "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), "
        f"  COALESCE(di.brand_name, di.brand_code), COALESCE(di.category_name, di.category_code) "
        f"ORDER BY total_sales DESC "
        f"LIMIT %s",
        rp + channel_params + item_params + [limit]
    )

    for row in rows:
        row["growth_pct"] = 0

    return {"data": rows}
