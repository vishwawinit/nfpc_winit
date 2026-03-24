"""Brand Wise Sales report endpoint.
Matches: sp_BrandsSale_Search_Report (brand list) + sp_tblItemDateBasedOnBrand (item drill-down)
         sp_GetBrandWiseTargetandSaleAmount (brand targets from rpt_targets via dim_item join)

Sources:
  - Brand sales: rpt_route_sales_by_item_customer joined to dim_item (brand = GroupLevel2 → Level 1)
  - Item drill: same source filtered by brand_code
  - Targets: rpt_targets joined to dim_item to resolve brand; summed by month/year in date range
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


def _resolve_filters(sales_org, user_code, route, channel, category, brand,
                     hos, asm, depot, supervisor):
    """Common filter resolution for both endpoints."""
    base = {}

    # Hierarchy
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return None
        if resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                if not intersected:
                    return None
                user_code = ','.join(intersected)
            else:
                user_code = resolved

    if route:
        base['route'] = route
    if user_code:
        base['user_code'] = user_code

    # Sales org → route JOIN
    org_join = ""
    org_params = []
    if sales_org and not base.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        org_params = orgs

    # Channel → customer codes
    extra_cond = ""
    extra_params = []
    if channel:
        ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
        ch_ph = ','.join(['%s'] * len(ch_vals))
        cust_rows = query(
            f"SELECT DISTINCT dc.code FROM dim_customer dc "
            f"JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code "
            f"WHERE TRIM(dc.channel_code) IN ({ch_ph})", ch_vals
        )
        if not cust_rows:
            return None
        c_codes = [r['code'] for r in cust_rows]
        c_ph = ','.join(['%s'] * len(c_codes))
        extra_cond += f" AND r.customer_code IN ({c_ph})"
        extra_params.extend(c_codes)

    # Brand/Category → item codes
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
            return None
        i_codes = [r['code'] for r in i_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        extra_cond += f" AND r.item_code IN ({i_ph})"
        extra_params.extend(i_codes)

    return base, extra_cond, extra_params, org_join, org_params


def _get_brand_targets(date_from, date_to, sales_org=None, user_code=None, route=None):
    """Fetch brand-level targets from rpt_targets via dim_item join.
    Mirrors sp_GetBrandWiseTargetandSaleAmount: tblCurrentTarget WHERE Month IN(...) AND Year IN(...)
    Joined to dim_item to resolve item_key → brand_code.
    Returns dict: {brand_code: target_amount}
    """
    if not date_from or not date_to:
        return {}

    # Build month/year range from date span (like SP's #Month CTE)
    from datetime import date as dt
    months = []
    y, m = date_from.year, date_from.month
    while (y, m) <= (date_to.year, date_to.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    if not months:
        return {}

    years = list(set(y for y, _ in months))
    month_nums = list(set(m for _, m in months))

    conditions = ["rt.is_active = true"]
    params = []

    y_ph = ','.join(['%s'] * len(years))
    m_ph = ','.join(['%s'] * len(month_nums))
    conditions.append(f"rt.year IN ({y_ph})")
    params.extend(years)
    conditions.append(f"rt.month IN ({m_ph})")
    params.extend(month_nums)

    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        o_ph = ','.join(['%s'] * len(orgs))
        conditions.append(f"rt.sales_org_code IN ({o_ph})")
        params.extend(orgs)

    if route:
        routes = [v.strip() for v in route.split(',') if v.strip()]
        r_ph = ','.join(['%s'] * len(routes))
        conditions.append(f"rt.route_code IN ({r_ph})")
        params.extend(routes)

    if user_code and user_code != '__NO_MATCH__':
        ucodes = [v.strip() for v in user_code.split(',') if v.strip()]
        u_ph = ','.join(['%s'] * len(ucodes))
        conditions.append(f"rt.salesman_code IN ({u_ph})")
        params.extend(ucodes)

    where = " AND ".join(conditions)
    rows = query(
        f"SELECT TRIM(di.brand_code) AS brand_code, COALESCE(SUM(rt.amount), 0) AS target "
        f"FROM rpt_targets rt "
        f"JOIN dim_item di ON di.code = rt.item_key "
        f"WHERE {where} AND di.brand_code IS NOT NULL AND TRIM(di.brand_code) != '' "
        f"GROUP BY TRIM(di.brand_code)",
        params
    )
    return {r['brand_code']: float(r['target']) for r in rows}


@router.get("/brand-wise-sales")
def get_brand_wise_sales(
    sales_org: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    channel: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    result = _resolve_filters(sales_org, user_code, route, channel, category, brand,
                              hos, asm, depot, supervisor)
    if result is None:
        return {"summary": {"total_brand_target": 0, "total_brand_achieved": 0, "brand_achieved_pct": 0}, "brands": []}

    base, extra_cond, extra_params, _org_join, _org_params = result
    filters = {**base, 'date_from': date_from, 'date_to': date_to}
    filters = {k: v for k, v in filters.items() if v is not None}

    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    brand_rows = query(
        f"SELECT TRIM(di.brand_code) AS brand_code, "
        f"  COALESCE(di.brand_name, TRIM(di.brand_code)) AS brand_name, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS sales, "
        f"  ROUND(COALESCE(SUM(r.total_qty), 0)::numeric, 0) AS qty "
        f"FROM rpt_route_sales_by_item_customer r "
        f"JOIN dim_item di ON r.item_code = di.code "
        f"{_org_join}"
        f"WHERE di.brand_code IS NOT NULL AND TRIM(di.brand_code) != '' "
        f"  AND {rw}{extra_cond} "
        f"GROUP BY TRIM(di.brand_code), COALESCE(di.brand_name, TRIM(di.brand_code)) "
        f"ORDER BY sales DESC",
        _org_params + rp + extra_params
    )

    total_sales = sum(float(r["sales"]) for r in brand_rows)

    # Fetch brand targets — mirrors sp_GetBrandWiseTargetandSaleAmount
    resolved_user = base.get('user_code')
    brand_targets = _get_brand_targets(date_from, date_to, sales_org=sales_org,
                                       user_code=resolved_user, route=route)

    brands = []
    for row in brand_rows:
        sales = float(row["sales"])
        bcode = row["brand_code"]
        target = brand_targets.get(bcode, 0)
        brands.append({
            "brand_code": bcode,
            "brand_name": row["brand_name"].strip() if row["brand_name"] else bcode,
            "target": round(target, 2),
            "sales": sales,
            "qty": float(row["qty"]),
            "achieved_pct": round(sales / target * 100, 2) if target else 0,
            "pct_of_total": round(sales / total_sales * 100, 2) if total_sales else 0,
        })

    total_target = sum(b["target"] for b in brands)
    return {
        "summary": {
            "total_brand_target": round(total_target, 2),
            "total_brand_achieved": round(total_sales, 2),
            "brand_achieved_pct": round(total_sales / total_target * 100, 2) if total_target else 0,
        },
        "brands": brands,
    }


@router.get("/brand-wise-sales/items")
def get_brand_items(
    brand: str = Query(..., description="Brand code to drill into"),
    sales_org: Optional[str] = None,
    channel: Optional[str] = None,
    category: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
):
    result = _resolve_filters(sales_org, user_code, route, channel, category, brand,
                              hos, asm, depot, supervisor)
    if result is None:
        return {"items": []}

    base, extra_cond, extra_params, _org_join, _org_params = result
    filters = {**base, 'date_from': date_from, 'date_to': date_to}
    filters = {k: v for k, v in filters.items() if v is not None}

    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    items = query(
        f"SELECT r.item_code, COALESCE(di.name, r.item_code) AS item_name, "
        f"  di.alt_name, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS sales, "
        f"  ROUND(COALESCE(SUM(r.total_qty), 0)::numeric, 0) AS qty "
        f"FROM rpt_route_sales_by_item_customer r "
        f"JOIN dim_item di ON r.item_code = di.code "
        f"{_org_join}"
        f"WHERE TRIM(di.brand_code) = %s AND {rw}{extra_cond} "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), di.alt_name "
        f"ORDER BY sales DESC",
        _org_params + [brand] + rp + extra_params
    )

    item_list = []
    for row in items:
        sales = float(row["sales"])
        item_list.append({
            "item_code": row["item_code"],
            "item_name": row["item_name"],
            "alt_name": row["alt_name"],
            "sales": sales,
            "qty": float(row["qty"]),
            "target": 0,
            "achieved_pct": 0,
        })

    return {"items": item_list}
