"""MTD Wastage Summary report endpoint.
Matches: sp_GetMTDWastageHeaders (summary) + sp_GetMTDWastage (details)

Source: rpt_route_sales_by_item_customer (has TotalGRSales, TotalDamageSales, TotalExpirySales)
"""
from fastapi import APIRouter
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


def _resolve_filters(route, date_from, date_to, sales_org, user_code, brand, category, hos, asm, depot, supervisor, customer=None):
    """Common filter resolution. Returns None when filters match nothing."""
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
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'customer': customer,
    }.items() if v is not None}

    _org_join = ""
    _org_params = []
    if sales_org and not base_filters.get('route'):
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        _org_join = f"JOIN dim_route _dr ON r.route_code = _dr.code AND _dr.sales_org_code IN ({org_ph}) "
        _org_params = orgs

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
            return None
        codes = [r['code'] for r in i_rows]
        item_cond = f" AND r.item_code IN ({','.join(['%s']*len(codes))})"
        item_params = codes

    f_rsic = {k: v for k, v in base_filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

    return base_filters, _org_join, _org_params, item_cond, item_params, rw, rp


@router.get("/mtd-wastage-summary")
def get_mtd_wastage_summary(
    route: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    hos: Optional[str] = None,
    asm: Optional[str] = None,
    depot: Optional[str] = None,
    supervisor: Optional[str] = None,
    customer: Optional[str] = None,
):
    result = _resolve_filters(route, date_from, date_to, sales_org, user_code, brand, category, hos, asm, depot, supervisor, customer)
    if result is None:
        return _empty()
    base_filters, _org_join, _org_params, item_cond, item_params, rw, rp = result

    # Summary totals
    summary_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(r.total_qty), 0) AS total_qty, "
        f"  COALESCE(SUM(r.total_sales), 0) AS total_sales, "
        f"  COALESCE(SUM(r.total_gr_qty), 0) AS total_gr_qty, "
        f"  COALESCE(SUM(r.total_gr_sales), 0) AS total_gr_sales, "
        f"  COALESCE(SUM(r.total_damage_qty), 0) AS total_damage_qty, "
        f"  COALESCE(SUM(r.total_damage_sales), 0) AS total_damage_sales, "
        f"  COALESCE(SUM(r.total_expiry_qty), 0) AS total_expiry_qty, "
        f"  COALESCE(SUM(r.total_expiry_sales), 0) AS total_expiry_sales "
        f"FROM rpt_route_sales_by_item_customer r {_org_join}WHERE {rw}{item_cond}",
        _org_params + rp + item_params
    )

    total_sales = float(summary_row["total_sales"]) if summary_row else 0
    total_gr = float(summary_row["total_gr_sales"]) if summary_row else 0
    total_damage = float(summary_row["total_damage_sales"]) if summary_row else 0
    total_expiry = float(summary_row["total_expiry_sales"]) if summary_row else 0
    gr_qty = float(summary_row["total_gr_qty"] or 0) if summary_row else 0
    damage_qty = float(summary_row["total_damage_qty"] or 0) if summary_row else 0
    expiry_qty = float(summary_row["total_expiry_qty"] or 0) if summary_row else 0
    total_returns = total_gr + total_damage + total_expiry
    total_qty = gr_qty + damage_qty + expiry_qty
    bad_returns = total_damage + total_expiry
    bad_qty = damage_qty + expiry_qty

    summary = {
        "total_sales": round(total_sales, 2),
        "total_returns_value": round(total_returns, 2),
        "total_returns_qty": round(total_qty),
        "total_returns_pct": round(total_returns / total_sales * 100, 2) if total_sales else 0,
        "gr_value": round(total_gr, 2),
        "gr_qty": round(gr_qty),
        "gr_pct": round(total_gr / total_returns * 100, 1) if total_returns else 0,
        "bad_returns_value": round(bad_returns, 2),
        "bad_returns_qty": round(bad_qty),
        "bad_returns_pct": round(bad_returns / total_returns * 100, 1) if total_returns else 0,
    }

    # Customer + date breakdown — individual columns for frontend to combine
    details = query(
        f"SELECT r.date, r.customer_code, "
        f"  COALESCE(dc.name, r.customer_code) AS customer_name, "
        f"  ROUND(COALESCE(SUM(r.total_gr_qty), 0)::numeric, 0) AS gr_qty, "
        f"  ROUND(COALESCE(SUM(r.total_gr_sales), 0)::numeric, 2) AS gr_value, "
        f"  ROUND(COALESCE(SUM(r.total_damage_qty + r.total_expiry_qty), 0)::numeric, 0) AS bad_qty, "
        f"  ROUND(COALESCE(SUM(r.total_damage_sales + r.total_expiry_sales), 0)::numeric, 2) AS bad_value "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN (SELECT DISTINCT code, name FROM dim_customer) dc ON r.customer_code = dc.code "
        f"{_org_join}"
        f"WHERE {rw}{item_cond} "
        f"GROUP BY r.date, r.customer_code, COALESCE(dc.name, r.customer_code) "
        f"HAVING SUM(r.total_gr_sales + r.total_damage_sales + r.total_expiry_sales) > 0 "
        f"ORDER BY r.date DESC, SUM(r.total_gr_sales + r.total_damage_sales + r.total_expiry_sales) DESC",
        _org_params + rp + item_params
    )

    detail_list = []
    for row in details:
        detail_list.append({
            "date": str(row["date"]) if row["date"] else None,
            "customer_code": row["customer_code"],
            "customer_name": row["customer_name"],
            "gr_qty": float(row["gr_qty"]),
            "gr_value": float(row["gr_value"]),
            "bad_qty": float(row["bad_qty"]),
            "bad_value": float(row["bad_value"]),
        })

    return {"summary": summary, "details": detail_list}


@router.get("/mtd-wastage-items")
def get_mtd_wastage_items(
    customer_code: str,
    date_val: str,
    return_type: str,  # 'gr' or 'bad'
):
    """Item-level breakdown for a specific customer, date, and return type."""
    if return_type == 'gr':
        qty_expr = "r.total_gr_qty"
        val_expr = "r.total_gr_sales"
        having = "SUM(r.total_gr_sales) > 0"
    elif return_type == 'bad':
        qty_expr = "r.total_damage_qty + r.total_expiry_qty"
        val_expr = "r.total_damage_sales + r.total_expiry_sales"
        having = "SUM(r.total_damage_sales + r.total_expiry_sales) > 0"
    else:
        return {"items": []}

    rows = query(
        f"SELECT r.item_code, "
        f"  COALESCE(di.name, r.item_code) AS item_name, "
        f"  ROUND(SUM({qty_expr})::numeric, 0) AS qty, "
        f"  ROUND(SUM({val_expr})::numeric, 2) AS amount "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN dim_item di ON r.item_code = di.code "
        f"WHERE r.customer_code = %s AND r.date = %s "
        f"GROUP BY r.item_code, COALESCE(di.name, r.item_code) "
        f"HAVING {having} "
        f"ORDER BY amount DESC",
        [customer_code, date_val]
    )

    return {
        "items": [
            {
                "item_code": r["item_code"],
                "item_name": r["item_name"],
                "qty": float(r["qty"]),
                "amount": float(r["amount"]),
            }
            for r in rows
        ]
    }


def _empty():
    return {
        "summary": {
            "total_sales": 0, "total_returns_value": 0, "total_returns_qty": 0, "total_returns_pct": 0,
            "gr_value": 0, "gr_qty": 0, "gr_pct": 0,
            "bad_returns_value": 0, "bad_returns_qty": 0, "bad_returns_pct": 0,
        },
        "details": [],
    }
