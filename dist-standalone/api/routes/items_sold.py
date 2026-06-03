"""Items Sold report endpoint — matches sp_GetItemSold_Common.
4 modes via 'type' parameter:
  1 = Item qty by customer/user/date
  2 = Distinct items sold per user per day
  3 = Distinct items sold per day (aggregate)
  4 = Total distinct items sold in date range
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}


@router.get("/items-sold")
def get_items_sold(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    sales_org: Optional[str] = None,
    item: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    type: int = Query(1, description="1=qty by item/cust/date, 2=items per user/day, 3=items per day, 4=total items"),
):
    # Resolve hierarchy
    _hier = {k: v for k, v in {'hos': hos, 'depot': depot, 'supervisor': supervisor, 'asm': asm}.items() if v}
    if _hier:
        resolved = resolve_user_codes(_hier)
        if resolved == "__NO_MATCH__":
            return []
        if resolved:
            if user_code:
                existing = set(user_code.split(','))
                intersected = existing & set(resolved.split(','))
                user_code = ','.join(intersected) if intersected else "__NO_MATCH__"
            else:
                user_code = resolved

    filters = {k: v for k, v in {
        'date_from': date_from, 'date_to': date_to,
        'route': route, 'user_code': user_code,
    }.items() if v is not None}

    # Item/category/brand filtering via dim_item
    item_cond = ""
    item_params = []
    if item:
        items = [v.strip() for v in item.split(',') if v.strip()]
        iph = ','.join(['%s'] * len(items))
        item_cond += f" AND r.item_code IN ({iph})"
        item_params.extend(items)
    if category:
        from api.database import query as db_query
        cats = [v.strip() for v in category.split(',') if v.strip()]
        cph = ','.join(['%s'] * len(cats))
        cat_items = db_query(f"SELECT DISTINCT code FROM dim_item WHERE category_code IN ({cph})", cats)
        if not cat_items:
            return []
        codes = [r['code'] for r in cat_items]
        ciph = ','.join(['%s'] * len(codes))
        item_cond += f" AND r.item_code IN ({ciph})"
        item_params.extend(codes)
    if brand:
        from api.database import query as db_query
        brands = [v.strip() for v in brand.split(',') if v.strip()]
        bph = ','.join(['%s'] * len(brands))
        brand_items = db_query(f"SELECT DISTINCT code FROM dim_item WHERE TRIM(brand_code) IN ({bph})", brands)
        if not brand_items:
            return []
        codes = [r['code'] for r in brand_items]
        biph = ','.join(['%s'] * len(codes))
        item_cond += f" AND r.item_code IN ({biph})"
        item_params.extend(codes)
    if customer:
        custs = [v.strip() for v in customer.split(',') if v.strip()]
        cuph = ','.join(['%s'] * len(custs))
        item_cond += f" AND r.customer_code IN ({cuph})"
        item_params.extend(custs)

    sw, sp = build_where(filters, date_col='date', prefix='r')

    if type == 1:
        # Type 1: Item qty by customer/user/date
        return query(
            f"SELECT r.item_code, COALESCE(di.name, r.item_code) AS item_name, "
            f"  r.user_code, r.customer_code, r.date AS sold_date, "
            f"  SUM(r.total_qty) AS sold_qty, SUM(r.total_sales) AS sold_amount "
            f"FROM rpt_route_sales_by_item_customer r "
            f"LEFT JOIN dim_item di ON r.item_code = di.code "
            f"WHERE {sw}{item_cond} "
            f"GROUP BY r.item_code, COALESCE(di.name, r.item_code), r.user_code, r.customer_code, r.date "
            f"ORDER BY r.date, r.item_code",
            sp + item_params
        )

    elif type == 2:
        # Type 2: Distinct items sold per user per day
        return query(
            f"SELECT r.user_code, r.date AS sold_date, "
            f"  COUNT(DISTINCT r.item_code) AS items_sold "
            f"FROM rpt_route_sales_by_item_customer r "
            f"WHERE r.total_sales >= 0 AND {sw}{item_cond} "
            f"GROUP BY r.user_code, r.date "
            f"ORDER BY r.date, r.user_code",
            sp + item_params
        )

    elif type == 3:
        # Type 3: Distinct items sold per day (aggregate)
        return query(
            f"SELECT r.date AS sold_date, "
            f"  COUNT(DISTINCT r.item_code) AS items_sold "
            f"FROM rpt_route_sales_by_item_customer r "
            f"WHERE r.total_sales >= 0 AND {sw}{item_cond} "
            f"GROUP BY r.date "
            f"ORDER BY r.date",
            sp + item_params
        )

    elif type == 4:
        # Type 4: Total distinct items sold in range
        row = query_one(
            f"SELECT COUNT(DISTINCT r.item_code) AS items_sold "
            f"FROM rpt_route_sales_by_item_customer r "
            f"WHERE r.total_sales >= 0 AND {sw}{item_cond}",
            sp + item_params
        )
        return {"items_sold": int(row["items_sold"]) if row else 0}

    return []
