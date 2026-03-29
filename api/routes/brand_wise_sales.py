"""Brand Wise Sales report endpoint.
Matches: sp_BrandsSale_Search_Report (brand list) + sp_tblItemDateBasedOnBrand (item drill-down)
         sp_GetBrandWiseTargetandSaleAmount (brand targets from rpt_targets via dim_item join)

Sources:
  - No filter path: rpt_route_sales_summary_by_item DISTINCT ON (matches dashboard)
  - Filtered path:  rpt_route_sales_by_item_customer + JOIN dim_item (brand/category ON clause)
  - Channel filter: EXISTS on dim_customer (avoids row multiplication)
  - Targets: rpt_targets joined to dim_item to resolve brand
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


def _resolve_base(sales_org, user_code, route, hos, asm, depot, supervisor):
    """Resolve hierarchy → (base_filters, org_join, org_params) or None on no-match."""
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

    if user_code == "__NO_MATCH__":
        return None

    base = {}
    if route:
        base['route'] = route
    if user_code:
        base['user_code'] = user_code

    org_join = ""
    org_params = []
    if sales_org and not base.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        org_params = orgs

    return base, org_join, org_params


def _build_channel_cond(channel):
    if not channel:
        return "", []
    ch_vals = [v.strip() for v in channel.split(',') if v.strip()]
    ch_ph = ','.join(['%s'] * len(ch_vals))
    cond = (
        f" AND EXISTS (SELECT 1 FROM dim_customer _chdc "
        f"WHERE _chdc.code = r.customer_code AND TRIM(_chdc.channel_code) IN ({ch_ph}))"
    )
    return cond, ch_vals


def _build_brand_di_cond(brand, category):
    """Conditions to append to an existing JOIN dim_item di ON clause."""
    if not brand and not category:
        return "", []
    i_conds, i_params = [], []
    if brand:
        b_vals = [v.strip() for v in brand.split(',') if v.strip()]
        i_conds.append(f"TRIM(di.brand_code) IN ({','.join(['%s'] * len(b_vals))})")
        i_params.extend(b_vals)
    if category:
        c_vals = [v.strip() for v in category.split(',') if v.strip()]
        i_conds.append(f"di.category_code IN ({','.join(['%s'] * len(c_vals))})")
        i_params.extend(c_vals)
    return " AND " + " AND ".join(i_conds), i_params


def _get_brand_targets(date_from, date_to, sales_org=None, user_code=None, route=None):
    """Fetch brand-level targets from rpt_targets via dim_item join."""
    if not date_from or not date_to:
        return {}
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


def _empty_brand():
    return {"summary": {"total_brand_target": 0, "total_brand_achieved": 0, "brand_achieved_pct": 0}, "brands": []}


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
    res = _resolve_base(sales_org, user_code, route, hos, asm, depot, supervisor)
    if res is None:
        return _empty_brand()
    base, _org_join, _org_params = res

    channel_cond, channel_params = _build_channel_cond(channel)
    brand_di_cond, brand_di_params = _build_brand_di_cond(brand, category)

    filters = {**base, 'date_from': date_from, 'date_to': date_to}
    filters = {k: v for k, v in filters.items() if v is not None}
    f_rsic = {k: v for k, v in filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    # ── Total Sales KPI — summary table (matches dashboard) when no channel/brand/category ──
    # Summary table has brand_code='NFPC' only, so can't break down by brand.
    # Use it only for the KPI total; use RSIC for per-brand breakdown below.
    _use_rsic_total = bool(channel or brand or category)
    if not _use_rsic_total:
        f_rssi = {k: v for k, v in {
            'route': route, 'user_code': base.get('user_code'),
            'date_from': date_from, 'date_to': date_to,
        }.items() if v is not None}
        sw_t, sp_t = build_where(f_rssi, date_col='date')
        org_cond_t = ""
        org_params_t = []
        if sales_org:
            orgs_t = [v.strip() for v in sales_org.split(',') if v.strip()]
            org_ph_t = ','.join(['%s'] * len(orgs_t))
            org_cond_t = f" AND sales_org_code IN ({org_ph_t})"
            org_params_t = orgs_t
        kpi_row = query_one(
            f"SELECT COALESCE(SUM(total_sales), 0) AS total_sales "
            f"FROM (SELECT DISTINCT ON (route_code, item_code, date) total_sales "
            f"  FROM rpt_route_sales_summary_by_item WHERE {sw_t}{org_cond_t} "
            f"  ORDER BY route_code, item_code, date) t",
            sp_t + org_params_t
        )
        kpi_total = float(kpi_row["total_sales"]) if kpi_row else 0
    else:
        kpi_total = None  # will be set after brand_rows query

    # ── Brand Breakdown — always RSIC + JOIN dim_item (per-brand detail) ──────
    brand_rows = query(
        f"SELECT TRIM(di.brand_code) AS brand_code, "
        f"  COALESCE(di.brand_name, TRIM(di.brand_code)) AS brand_name, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS sales, "
        f"  ROUND(COALESCE(SUM(r.total_qty), 0)::numeric, 0) AS qty "
        f"FROM rpt_route_sales_by_item_customer r "
        f"JOIN dim_item di ON r.item_code = di.code{brand_di_cond} "
        f"{_org_join}"
        f"WHERE di.brand_code IS NOT NULL AND TRIM(di.brand_code) != '' "
        f"  AND {rw}{channel_cond} "
        f"GROUP BY TRIM(di.brand_code), COALESCE(di.brand_name, TRIM(di.brand_code)) "
        f"ORDER BY sales DESC",
        brand_di_params + _org_params + rp + channel_params
    )

    rsic_total = sum(float(r["sales"]) for r in brand_rows)
    if kpi_total is None:
        kpi_total = rsic_total
    total_sales = rsic_total  # used for pct_of_total so percentages add up to 100%
    brand_targets = _get_brand_targets(date_from, date_to, sales_org=sales_org,
                                       user_code=base.get('user_code'), route=route)

    brands = []
    for row in brand_rows:
        sales = float(row["sales"])
        bcode = row["brand_code"]
        target = brand_targets.get(bcode, 0)
        brands.append({
            "brand_code": bcode,
            "brand_name": (row["brand_name"] or bcode).strip(),
            "target": round(target, 2),
            "sales": sales,
            "qty": float(row.get("qty") or 0),
            "achieved_pct": round(sales / target * 100, 2) if target else 0,
            "pct_of_total": round(sales / total_sales * 100, 2) if total_sales else 0,
        })

    total_target = sum(b["target"] for b in brands)
    return {
        "summary": {
            "total_brand_target": round(total_target, 2),
            "total_brand_achieved": round(kpi_total, 2),   # dashboard-matched total
            "brand_achieved_pct": round(kpi_total / total_target * 100, 2) if total_target else 0,
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
    res = _resolve_base(sales_org, user_code, route, hos, asm, depot, supervisor)
    if res is None:
        return {"items": []}
    base, _org_join, _org_params = res

    channel_cond, channel_params = _build_channel_cond(channel)

    # Category filter on dim_item ON clause
    cat_di_cond = ""
    cat_di_params = []
    if category:
        c_vals = [v.strip() for v in category.split(',') if v.strip()]
        cat_di_cond = f" AND di.category_code IN ({','.join(['%s'] * len(c_vals))})"
        cat_di_params = c_vals

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
        f"JOIN dim_item di ON r.item_code = di.code AND TRIM(di.brand_code) = %s{cat_di_cond} "
        f"{_org_join}"
        f"WHERE {rw}{channel_cond} "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), di.alt_name "
        f"ORDER BY sales DESC",
        [brand] + cat_di_params + _org_params + rp + channel_params
    )

    return {
        "items": [
            {
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "alt_name": row["alt_name"],
                "sales": float(row["sales"]),
                "qty": float(row["qty"]),
                "target": 0,
                "achieved_pct": 0,
            }
            for row in items
        ]
    }
