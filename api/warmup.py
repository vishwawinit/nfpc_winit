"""Pre-warm the query cache on server startup.

Calls every API endpoint with its default filters so that when a user
first opens the browser, the data is already cached and loads instantly.
"""
import logging
import threading
import time
from datetime import date

log = logging.getLogger("warmup")


def _today():
    return date.today()


def _month_start():
    t = date.today()
    return date(t.year, t.month, 1)


def _year_start():
    return date(date.today().year, 1, 1)


def _year():
    return date.today().year


def _month():
    return date.today().month


# Each entry: (module_name, function_name, kwargs)
WARMUP_CALLS = [
    # Dashboard
    ("dashboard", "get_dashboard", {"date_from": _month_start(), "date_to": _today()}),
    # Sales Performance
    ("sales_performance", "get_sales_performance", {"month": _month(), "year": _year()}),
    # Top Customers
    ("top_customers", "get_top_customers", {"month": _month(), "year": _year()}),
    # Top Products
    ("top_products", "get_top_products", {"month": _month(), "year": _year()}),
    # Market Sales
    ("market_sales", "get_market_sales_performance", {"year": _year()}),
    # Target vs Achievement
    ("target_achievement", "get_target_vs_achievement", {"year": _year(), "month": _month()}),
    # Daily Sales Overview
    ("daily_sales_overview", "get_daily_sales_overview", {"date_from": _month_start(), "date_to": _today()}),
    # MTD Wastage
    ("mtd_wastage", "get_mtd_wastage_summary", {"date_from": _month_start(), "date_to": _today()}),
    # Weekly Sales Returns
    ("weekly_sales_returns", "get_weekly_sales_returns", {"date_from": _year_start(), "date_to": _today()}),
    # Brand Wise Sales
    ("brand_wise_sales", "get_brand_wise_sales", {"date_from": _month_start(), "date_to": _today()}),
    # MTD Sales Overview
    ("mtd_sales_overview", "get_mtd_sales_overview", {"date_from": _month_start(), "date_to": _today()}),
    # Log Report
    ("log_report", "get_log_report", {"date_from": _month_start(), "date_to": _today()}),
    # Time Management
    ("time_management", "get_time_management", {"date_from": _month_start(), "date_to": _today()}),
    # Customer Attendance
    ("customer_attendance", "get_customer_attendance", {"date_from": _month_start(), "date_to": _today()}),
    # MTD Attendance
    ("mtd_attendance", "get_mtd_attendance", {"date_from": _month_start(), "date_to": _today()}),
    # Journey Plan Compliance
    ("journey_plan_compliance", "get_journey_plan_compliance", {"date_from": _month_start(), "date_to": _today()}),
    # EOT Status
    ("eot_status", "get_eot_status", {"date_from": _month_start(), "date_to": _today()}),
    # Productivity Coverage
    ("productivity_coverage", "get_productivity_coverage", {"date_from": _month_start(), "date_to": _today()}),
    # Salesman Journey
    ("salesman_journey", "get_salesman_journey", {"date_from": _month_start(), "date_to": _today()}),
    # Revenue Dispersion
    ("revenue_dispersion", "get_revenue_dispersion", {"date_from": _year_start(), "date_to": _today()}),
    # Monthly Sales Stock
    ("monthly_sales_stock", "get_monthly_sales_stock", {"date_from": _month_start(), "date_to": _today()}),
    # Endorsement
    ("endorsement", "get_endorsement", {"date_from": _month_start(), "date_to": _today()}),
    # Filter dropdowns
    ("filters", "get_sales_orgs", {}),
]


def run_warmup():
    """Import route modules and call each endpoint function directly."""
    import importlib

    start = time.time()
    success = 0
    failed = 0

    for module_name, func_name, kwargs in WARMUP_CALLS:
        try:
            mod = importlib.import_module(f"api.routes.{module_name}")
            fn = getattr(mod, func_name)
            fn(**kwargs)
            success += 1
            log.info(f"  Warmed: {module_name}.{func_name}")
        except Exception as e:
            failed += 1
            log.warning(f"  Skip:  {module_name}.{func_name} - {e}")

    elapsed = time.time() - start
    log.info(f"Cache warmup complete: {success} cached, {failed} skipped in {elapsed:.1f}s")


def start_warmup_thread():
    """Run warmup in a background thread so the server starts immediately."""
    log.info("Starting cache warmup in background...")
    t = threading.Thread(target=run_warmup, daemon=True, name="cache-warmup")
    t.start()
