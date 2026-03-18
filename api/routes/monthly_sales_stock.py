"""Monthly Sales & Stock report endpoint.
Item × Channel pivot with MTD and YTD amounts.

Source: rpt_route_sales_by_item_customer joined to dim_customer (for channel) and dim_item (for names).
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


@router.get("/monthly-sales-stock")
def get_monthly_sales_stock(
    sales_org: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    user_code: Optional[str] = None,
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

    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)
    ytd_start = date(ref_date.year, 1, 1)

    base_filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
    }.items() if v}

    # Resolve sales_org to user_codes
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        if not org_rows:
            return {"items": []}
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            existing = set(base_filters['user_code'].split(','))
            intersected = existing & org_users
            if not intersected:
                return {"items": []}
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

    # Brand/Category → item_codes
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
            return {"items": []}
        i_codes = [r['code'] for r in i_rows]
        i_ph = ','.join(['%s'] * len(i_codes))
        item_cond = f" AND r.item_code IN ({i_ph})"
        item_params = i_codes

    # YTD query (widest range needed)
    ytd_filters = {**base_filters, 'date_from': ytd_start, 'date_to': ref_date}
    f_rsic = {k: v for k, v in ytd_filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    # Item × Channel with MTD and YTD
    # Channel comes from dim_customer joined via customer_code + route's sales_org
    rows = query(
        f"SELECT "
        f"  r.item_code, "
        f"  COALESCE(di.name, r.item_code) AS item_name, "
        f"  COALESCE(TRIM(dc.channel_name), 'Unknown') AS channel_name, "
        f"  ROUND(COALESCE(SUM(CASE WHEN r.date BETWEEN %s AND %s THEN r.total_sales ELSE 0 END), 0)::numeric, 2) AS mtd_amount, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS ytd_amount "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_item di ON r.item_code = di.code "
        f"LEFT JOIN dim_route dr ON r.route_code = dr.code "
        f"LEFT JOIN dim_customer dc ON r.customer_code = dc.code AND dr.sales_org_code = dc.sales_org_code "
        f"WHERE {rw}{item_cond} "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), "
        f"  COALESCE(TRIM(dc.channel_name), 'Unknown') "
        f"ORDER BY COALESCE(di.name, r.item_code), channel_name",
        [mtd_start, ref_date] + rp + item_params
    )

    # Pivot: group by item, nest channels
    items_map = {}
    for r in rows:
        key = r["item_code"]
        if key not in items_map:
            items_map[key] = {
                "item_code": r["item_code"],
                "item_name": r["item_name"],
                "channels": {},
            }
        channel = r["channel_name"] or "Unknown"
        items_map[key]["channels"][channel] = {
            "mtd_amount": float(r["mtd_amount"]),
            "ytd_amount": float(r["ytd_amount"]),
        }

    return {
        "items": list(items_map.values()),
    }
