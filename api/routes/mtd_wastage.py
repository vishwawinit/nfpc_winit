"""MTD Wastage Summary report endpoint.
Matches: sp_GetMTDWastageHeaders (summary) + sp_GetMTDWastage (details)

Source: rpt_route_sales_by_item_customer (has TotalGRSales, TotalDamageSales, TotalExpirySales)
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where, resolve_user_codes

router = APIRouter()

RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code', 'item', 'customer'}


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
):
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
    }.items() if v is not None}

    # Resolve sales_org
    if sales_org:
        orgs = [v.strip() for v in sales_org.split(',') if v.strip()]
        org_ph = ','.join(['%s'] * len(orgs))
        org_rows = query(f"SELECT DISTINCT code FROM dim_user WHERE is_active = true AND sales_org_code IN ({org_ph})", orgs)
        if not org_rows:
            return _empty()
        org_users = set(r['code'] for r in org_rows)
        if base_filters.get('user_code'):
            intersected = set(base_filters['user_code'].split(',')) & org_users
            if not intersected:
                return _empty()
            base_filters['user_code'] = ','.join(intersected)
        else:
            base_filters['user_code'] = ','.join(org_users)

    # Brand/Category filter
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
            return _empty()
        codes = [r['code'] for r in i_rows]
        item_cond = f" AND r.item_code IN ({','.join(['%s']*len(codes))})"
        item_params = codes

    f_rsic = {k: v for k, v in base_filters.items() if k in RSIC_KEYS}
    rw, rp = build_where(f_rsic, date_col='date', prefix='r')

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
        f"FROM rpt_route_sales_by_item_customer r WHERE {rw}{item_cond}",
        rp + item_params
    )

    total_sales = float(summary_row["total_sales"]) if summary_row else 0
    total_gr = float(summary_row["total_gr_sales"]) if summary_row else 0
    total_damage = float(summary_row["total_damage_sales"]) if summary_row else 0
    total_expiry = float(summary_row["total_expiry_sales"]) if summary_row else 0
    total_wastage = total_gr + total_damage + total_expiry
    total_wastage_qty = (float(summary_row["total_gr_qty"] or 0) +
                         float(summary_row["total_damage_qty"] or 0) +
                         float(summary_row["total_expiry_qty"] or 0)) if summary_row else 0

    summary = {
        "total_qty": round(total_wastage_qty),
        "total_pct": round(total_wastage / total_sales * 100, 2) if total_sales else 0,
        "total_expired_value": round(total_expiry, 2),
        "total_damaged_value": round(total_damage, 2),
        "total_gr_value": round(total_gr, 2),
        "total_wastage_value": round(total_wastage, 2),
        "total_sales": round(total_sales, 2),
        "damaged_pct": round(total_damage / total_wastage * 100, 2) if total_wastage else 0,
    }

    # Customer-level breakdown
    details = query(
        f"SELECT r.customer_code, "
        f"  COALESCE(dc.name, r.customer_code) AS customer_name, "
        f"  ROUND(COALESCE(SUM(r.total_gr_qty + r.total_damage_qty + r.total_expiry_qty), 0)::numeric, 0) AS qty, "
        f"  ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2) AS cust_sales, "
        f"  ROUND(COALESCE(SUM(r.total_expiry_sales), 0)::numeric, 2) AS expired_value, "
        f"  ROUND(COALESCE(SUM(r.total_damage_sales), 0)::numeric, 2) AS damaged_value, "
        f"  ROUND(COALESCE(SUM(r.total_gr_sales), 0)::numeric, 2) AS gr_value "
        f"FROM rpt_route_sales_by_item_customer r "
        f"LEFT JOIN (SELECT DISTINCT code, name FROM dim_customer) dc ON r.customer_code = dc.code "
        f"WHERE {rw}{item_cond} "
        f"GROUP BY r.customer_code, COALESCE(dc.name, r.customer_code) "
        f"HAVING SUM(r.total_gr_sales + r.total_damage_sales + r.total_expiry_sales) > 0 "
        f"ORDER BY qty DESC",
        rp + item_params
    )

    detail_list = []
    for row in details:
        cust_sales = float(row["cust_sales"])
        wastage_v = float(row["expired_value"]) + float(row["damaged_value"]) + float(row["gr_value"])
        detail_list.append({
            "customer_code": row["customer_code"],
            "customer_name": row["customer_name"],
            "qty": float(row["qty"]),
            "pct": round(wastage_v / cust_sales * 100, 2) if cust_sales else 0,
            "expired_value": float(row["expired_value"]),
            "damaged_value": float(row["damaged_value"]),
            "gr_value": float(row["gr_value"]),
        })

    return {
        "summary": summary,
        "details": detail_list,
    }


def _empty():
    return {
        "summary": {
            "total_qty": 0, "total_pct": 0, "total_expired_value": 0,
            "total_damaged_value": 0, "total_gr_value": 0, "total_wastage_value": 0,
            "total_sales": 0, "damaged_pct": 0,
        },
        "details": [],
    }
