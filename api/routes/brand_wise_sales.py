"""Brand Wise Sales report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/brand-wise-sales")
def get_brand_wise_sales(
    sales_org: Optional[str] = None,
    brand: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'sales_org': sales_org, 'brand': brand, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to, 'route': route,
    }.items() if v is not None}

    # --- Actual sales by brand from rpt_sales_detail ---
    sw, sp = build_where(filters, date_col='trx_date')
    brand_rows = query(
        f"SELECT TRIM(category_code) AS brand_code, category_name AS brand_name, "
        f"  COALESCE(SUM(net_amount), 0) AS sales, "
        f"  COALESCE(SUM(qty_cases), 0) AS qty "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND TRIM(category_code) != '' AND {sw} "
        f"GROUP BY TRIM(category_code), category_name "
        f"ORDER BY sales DESC",
        sp
    )

    # --- Targets by brand ---
    target_filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code, 'route': route,
    }.items() if v is not None}
    tf = {**target_filters, 'date_from': date_from, 'date_to': date_to}
    tf = {k: v for k, v in tf.items() if v is not None}
    tw, tp = build_where(tf, date_col='start_date')
    target_rows = query(
        f"SELECT item_key AS brand_code, "
        f"  COALESCE(SUM(amount), 0) AS target "
        f"FROM rpt_targets WHERE is_active = true AND {tw} "
        f"GROUP BY item_key",
        tp
    )
    target_map = {r["brand_code"]: float(r["target"]) for r in target_rows}

    # Compute totals and brand list
    total_sales = sum(float(r["sales"]) for r in brand_rows)
    total_target = sum(target_map.values())

    brands = []
    for row in brand_rows:
        bc = row["brand_code"]
        sales = float(row["sales"])
        target = target_map.get(bc, 0)
        achieved_pct = round(sales / target * 100, 2) if target else 0
        pct_of_total = round(sales / total_sales * 100, 2) if total_sales else 0
        brands.append({
            "brand_code": bc,
            "brand_name": row["brand_name"] or bc,
            "target": target,
            "sales": sales,
            "qty": float(row["qty"]),
            "achieved_pct": achieved_pct,
            "pct_of_total": pct_of_total,
        })

    summary = {
        "total_brand_target": total_target,
        "total_brand_achieved": total_sales,
        "brand_achieved_pct": round(total_sales / total_target * 100, 2) if total_target else 0,
    }

    return {
        "summary": summary,
        "brands": brands,
    }


@router.get("/brand-wise-sales/items")
def get_brand_items(
    brand: str = Query(..., description="Brand code to drill into"),
    sales_org: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    route: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'sales_org': sales_org, 'brand': brand, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to, 'route': route,
    }.items() if v is not None}

    sw, sp = build_where(filters, date_col='trx_date')
    items = query(
        f"SELECT item_code, item_name, "
        f"  TRIM(category_code) AS brand_code, category_name AS brand_name, "
        f"  COALESCE(SUM(net_amount), 0) AS sales, "
        f"  COALESCE(SUM(qty_cases), 0) AS qty "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND {sw} "
        f"GROUP BY item_code, item_name, TRIM(category_code), category_name "
        f"ORDER BY sales DESC",
        sp
    )

    # Targets at item level
    target_filters = {k: v for k, v in {
        'sales_org': sales_org, 'user_code': user_code, 'route': route,
    }.items() if v is not None}
    tf = {**target_filters, 'date_from': date_from, 'date_to': date_to}
    tf = {k: v for k, v in tf.items() if v is not None}
    tw, tp = build_where(tf, date_col='start_date')
    item_targets = query(
        f"SELECT item_key, item_name, "
        f"  COALESCE(SUM(amount), 0) AS target, "
        f"  COALESCE(SUM(quantity), 0) AS target_qty "
        f"FROM rpt_targets WHERE is_active = true AND {tw} "
        f"GROUP BY item_key, item_name",
        tp
    )
    target_map = {r["item_key"]: r for r in item_targets}

    total_sales = sum(float(r["sales"]) for r in items)

    item_list = []
    for row in items:
        sales = float(row["sales"])
        tgt = target_map.get(row["item_code"], {})
        target = float(tgt.get("target", 0))
        item_list.append({
            "item_code": row["item_code"],
            "item_name": row["item_name"],
            "brand_code": row["brand_code"],
            "brand_name": row["brand_name"] or row["brand_code"],
            "sales": sales,
            "qty": float(row["qty"]),
            "target": target,
            "achieved_pct": round(sales / target * 100, 2) if target else 0,
            "pct_of_total": round(sales / total_sales * 100, 2) if total_sales else 0,
        })

    return {"items": item_list}
