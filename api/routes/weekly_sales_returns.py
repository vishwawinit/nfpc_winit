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

    # Resolve sales_org to user_codes
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(
            f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs
        )
        if not org_rows:
            return _empty()
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            existing = set(base_filters['user_code'].split(','))
            intersected = existing & org_users
            if not intersected:
                return _empty()
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

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
        f"FROM rpt_route_sales_by_item_customer r "
        f"WHERE {rw}{channel_cond}{item_cond} "
        f"GROUP BY EXTRACT(ISOYEAR FROM r.date), EXTRACT(WEEK FROM r.date) "
        f"ORDER BY year, week_number",
        rp + channel_params + item_params
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


def _empty():
    return {
        "weekly_data": [],
        "totals": {"total_sales": 0, "total_returns": 0, "net_amount": 0, "return_pct": 0},
    }
