"""Sales Performance report endpoint."""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, timedelta
from api.database import query, query_one
from api.models import build_where

router = APIRouter()


def _month_range(year: int, month: int):
    """Return (first_day, last_day) for a given year/month."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


@router.get("/sales-performance")
def get_sales_performance(
    route: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    sales_org: Optional[str] = None,
):
    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month

    # Current & last month ranges
    cur_start, cur_end = _month_range(cur_year, cur_month)
    if cur_month == 1:
        last_start, last_end = _month_range(cur_year - 1, 12)
    else:
        last_start, last_end = _month_range(cur_year, cur_month - 1)

    base_filters = {k: v for k, v in {'route': route, 'sales_org': sales_org}.items() if v}

    # --- Targets for current & last month ---
    def get_target(m_start, m_end):
        f = {**base_filters, 'date_from': m_start, 'date_to': m_end}
        tw, tp = build_where(f, date_col='start_date')
        row = query_one(
            f"SELECT COALESCE(SUM(amount),0) AS target "
            f"FROM rpt_targets WHERE is_active = true AND {tw}", tp
        )
        return float(row["target"]) if row else 0

    # --- Actual sales for a period (from rpt_sales_detail, trx_type=1) ---
    def get_sales(m_start, m_end):
        f = {**base_filters, 'date_from': m_start, 'date_to': m_end}
        sw, sp = build_where(f, date_col='trx_date')
        row = query_one(
            f"SELECT COALESCE(SUM(net_amount),0) AS sales "
            f"FROM rpt_sales_detail WHERE trx_type = 1 AND {sw}", sp
        )
        return float(row["sales"]) if row else 0

    cur_target = get_target(cur_start, cur_end)
    last_target = get_target(last_start, last_end)
    cur_sales = get_sales(cur_start, cur_end)
    last_sales = get_sales(last_start, last_end)

    cur_achievement = round(cur_sales / cur_target * 100, 2) if cur_target else 0
    last_achievement = round(last_sales / last_target * 100, 2) if last_target else 0

    # --- Return on Sales breakdown (from rpt_sales_detail, trx_type=4 for returns) ---
    ros_filters = {**base_filters, 'date_from': cur_start, 'date_to': cur_end}
    rw, rp = build_where(ros_filters, date_col='trx_date')

    # Total sales for the period
    sales_row = query_one(
        f"SELECT COALESCE(SUM(net_amount),0) AS total_sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND {rw}", rp
    )
    total_s = float(sales_row["total_sales"]) if sales_row else 0

    # Total returns for the period (trx_type=4, values are positive)
    returns_row = query_one(
        f"SELECT COALESCE(SUM(net_amount),0) AS total_returns "
        f"FROM rpt_sales_detail WHERE trx_type = 4 AND {rw}", rp
    )
    total_returns = float(returns_row["total_returns"]) if returns_row else 0

    return_on_sales = {
        "gr": 0,
        "expiry": 0,
        "damage": 0,
        "near_expiry": 0,
        "total_returns": total_returns,
        "total_sales": total_s,
        "ros_pct": round(total_returns / total_s * 100, 2) if total_s else 0,
    }

    # --- SKU counts (today, MTD, YTD) from rpt_sales_detail ---
    ytd_start = date(cur_year, 1, 1)

    def sku_count(d_from, d_to):
        f = {**base_filters, 'date_from': d_from, 'date_to': d_to}
        sw, sp = build_where(f, date_col='trx_date')
        row = query_one(
            f"SELECT COUNT(DISTINCT item_code) AS cnt "
            f"FROM rpt_sales_detail WHERE trx_type = 1 AND net_amount > 0 AND {sw}", sp
        )
        return int(row["cnt"]) if row else 0

    sku_counts = {
        "today": sku_count(today, today),
        "mtd": sku_count(cur_start, cur_end),
        "ytd": sku_count(ytd_start, cur_end),
    }

    # --- SKU table: items with last month / current month sales, grouped by category ---
    # Current month item sales
    cm_f = {**base_filters, 'date_from': cur_start, 'date_to': cur_end}
    cmw, cmp = build_where(cm_f, date_col='trx_date')

    # Last month item sales
    lm_f = {**base_filters, 'date_from': last_start, 'date_to': last_end}
    lmw, lmp = build_where(lm_f, date_col='trx_date')

    # Current week
    week_start = today - timedelta(days=today.weekday())  # Monday
    cw_f = {**base_filters, 'date_from': week_start, 'date_to': today}
    cww, cwp = build_where(cw_f, date_col='trx_date')

    sku_table = query(
        f"SELECT "
        f"  item_code, item_name, category_code, category_name, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END) AS last_month_sales, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END) AS current_month_sales, "
        f"  SUM(CASE WHEN trx_date BETWEEN %s AND %s THEN net_amount ELSE 0 END) AS current_week_sales "
        f"FROM rpt_sales_detail WHERE trx_type = 1 AND ({cmw} OR {lmw} OR {cww}) "
        f"GROUP BY item_code, item_name, category_code, category_name "
        f"ORDER BY category_name, current_month_sales DESC",
        [last_start, last_end, cur_start, cur_end, week_start, today] + cmp + lmp + cwp
    )

    # Compute growth for each row
    for row in sku_table:
        lm = float(row["last_month_sales"] or 0)
        cm = float(row["current_month_sales"] or 0)
        row["growth"] = round((cm - lm) / lm * 100, 2) if lm else 0

    return {
        "last_month_achievement_pct": last_achievement,
        "current_month_achievement_pct": cur_achievement,
        "return_on_sales": return_on_sales,
        "sku_counts": sku_counts,
        "sku_table": sku_table,
    }
