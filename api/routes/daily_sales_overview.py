"""Daily Sales Overview report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


@router.get("/daily-sales-overview")
def get_daily_sales_overview(
    area: Optional[str] = None,
    route_type: Optional[str] = None,
    route: Optional[str] = None,
    user_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sales_org: Optional[str] = None,
):
    filters = {k: v for k, v in {
        'route': route, 'user_code': user_code,
        'date_from': date_from, 'date_to': date_to,
        'sales_org': sales_org,
    }.items() if v is not None}

    # --- Sales Details: cash vs credit ---
    sw, sp = build_where(filters, date_col='trx_date')

    # Additional area/route_type filters (not in standard build_where)
    extra_conds = []
    extra_params = []
    if area:
        extra_conds.append("area_code = %s")
        extra_params.append(area)
    if route_type:
        extra_conds.append("route_type = %s")
        extra_params.append(route_type)
    extra_where = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

    sales_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '1' THEN net_amount ELSE 0 END), 0) AS cash_sales, "
        f"  COALESCE(SUM(CASE WHEN payment_type::text = '0' THEN net_amount ELSE 0 END), 0) AS credit_sales, "
        f"  COALESCE(SUM(net_amount), 0) AS total_sales, "
        f"  COALESCE(SUM(discount_amount), 0) AS discount "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND {sw}{extra_where}",
        sp + extra_params
    )

    sales_details = {
        "cash_sales": float(sales_row["cash_sales"]) if sales_row else 0,
        "credit_sales": float(sales_row["credit_sales"]) if sales_row else 0,
        "total_sales": float(sales_row["total_sales"]) if sales_row else 0,
        "discount": float(sales_row["discount"]) if sales_row else 0,
    }

    # --- Call Details from coverage summary ---
    cw, cp = build_where(filters, date_col='visit_date')
    call_row = query_one(
        f"SELECT "
        f"  COALESCE(SUM(total_actual_calls), 0) AS total_calls, "
        f"  COALESCE(SUM(selling_calls), 0) AS selling_calls "
        f"FROM rpt_coverage_summary WHERE {cw}",
        cp
    )

    # Total invoices from sales detail
    inv_row = query_one(
        f"SELECT COUNT(DISTINCT trx_code) AS total_invoices "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND {sw}{extra_where}",
        sp + extra_params
    )

    call_details = {
        "total_calls": int(call_row["total_calls"]) if call_row else 0,
        "selling_calls": int(call_row["selling_calls"]) if call_row else 0,
        "total_invoices": int(inv_row["total_invoices"]) if inv_row else 0,
    }

    # --- Item Table: by category (commercial brand) with target comparison ---
    # MTD date range (first of month to date_to or today)
    ref_date = date_to or date.today()
    mtd_start = date(ref_date.year, ref_date.month, 1)

    # Actual sales by category (= commercial brand like Safa Dairy, Lacnor Fresh, etc.)
    brand_sales = query(
        f"SELECT TRIM(category_code) AS brand_code, category_name AS brand_name, "
        f"  COALESCE(SUM(net_amount), 0) AS gross_sales "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND TRIM(category_code) != '' AND {sw}{extra_where} "
        f"GROUP BY TRIM(category_code), category_name "
        f"ORDER BY gross_sales DESC",
        sp + extra_params
    )

    # MTD sales by category
    mtd_filters = {**{k: v for k, v in filters.items() if k not in ('date_from', 'date_to')},
                   'date_from': mtd_start, 'date_to': ref_date}
    mw, mp = build_where(mtd_filters, date_col='trx_date')

    mtd_extra_params = list(extra_params)
    mtd_sales = query(
        f"SELECT TRIM(category_code) AS brand_code, "
        f"  COALESCE(SUM(net_amount), 0) AS mtd_gross_sales "
        f"FROM rpt_sales_detail "
        f"WHERE trx_type = 1 AND TRIM(category_code) != '' AND {mw}{extra_where} "
        f"GROUP BY TRIM(category_code)",
        mp + mtd_extra_params
    )
    mtd_map = {r["brand_code"]: float(r["mtd_gross_sales"]) for r in mtd_sales}

    # Targets by brand (item_key used as brand aggregation)
    target_filters = {k: v for k, v in {
        'sales_org': sales_org, 'route': route, 'user_code': user_code,
    }.items() if v is not None}
    tf = {**target_filters, 'date_from': mtd_start, 'date_to': ref_date}
    tw, tp = build_where(tf, date_col='start_date')
    brand_targets = query(
        f"SELECT item_key AS brand_code, "
        f"  COALESCE(SUM(amount), 0) AS target_sales "
        f"FROM rpt_targets WHERE is_active = true AND {tw} "
        f"GROUP BY item_key",
        tp
    )
    target_map = {r["brand_code"]: float(r["target_sales"]) for r in brand_targets}

    # MTD targets
    mtd_target_sales = query(
        f"SELECT item_key AS brand_code, "
        f"  COALESCE(SUM(amount), 0) AS mtd_target "
        f"FROM rpt_targets WHERE is_active = true AND {tw} "
        f"GROUP BY item_key",
        tp
    )
    mtd_target_map = {r["brand_code"]: float(r["mtd_target"]) for r in mtd_target_sales}

    item_table = []
    for row in brand_sales:
        bc = row["brand_code"]
        gross = float(row["gross_sales"])
        target = target_map.get(bc, 0)
        mtd_gross = mtd_map.get(bc, 0)
        mtd_target = mtd_target_map.get(bc, 0)
        item_table.append({
            "brand_code": bc,
            "brand_name": row["brand_name"] or bc,
            "gross_sales": gross,
            "target_sales": target,
            "variance": gross - target,
            "mtd_gross_sales": mtd_gross,
            "mtd_target_sales": mtd_target,
            "mtd_variance": mtd_gross - mtd_target,
        })

    return {
        "sales_details": sales_details,
        "call_details": call_details,
        "item_table": item_table,
    }
