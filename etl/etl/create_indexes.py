#!/usr/bin/env python3
"""
NFPC Reports — Comprehensive Index Creation Script.
Creates all missing indexes to bring report load times under 3 seconds.
Safe to run multiple times — uses IF NOT EXISTS everywhere.

Run: python etl/etl/create_indexes.py
"""
import os, sys, time
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

conn = psycopg2.connect(
    host=os.environ['PG_HOST'], port=os.environ['PG_PORT'],
    dbname=os.environ['PG_DATABASE'], user=os.environ['PG_USER'],
    password=os.environ['PG_PASSWORD']
)
conn.autocommit = True
cur = conn.cursor()

INDEXES = [

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_route_sales_by_item_customer  (1.4 GB, 4.5M rows)
    # Most-used table — dashboard, daily_sales, top_customers, top_products,
    # brand_wise_sales, monthly_sales_stock, mtd_wastage, salesman_journey,
    # endorsement, eot_status, items_sold, weekly_sales_returns
    # ──────────────────────────────────────────────────────────────────────────

    # user + item + date — top_products, brand_wise_sales, items_sold
    ("idx_rsic_user_item_date",
     "CREATE INDEX IF NOT EXISTS idx_rsic_user_item_date "
     "ON rpt_route_sales_by_item_customer(user_code, item_code, date)"),

    # user + customer + date — top_customers, monthly_sales_stock, salesman_journey
    ("idx_rsic_user_customer_date",
     "CREATE INDEX IF NOT EXISTS idx_rsic_user_customer_date "
     "ON rpt_route_sales_by_item_customer(user_code, customer_code, date)"),

    # route + user + date — eot_status, salesman_journey, endorsement
    ("idx_rsic_route_user_date",
     "CREATE INDEX IF NOT EXISTS idx_rsic_route_user_date "
     "ON rpt_route_sales_by_item_customer(route_code, user_code, date)"),

    # Covering: user+date with key metrics — avoids heap fetch for aggregation
    ("idx_rsic_user_date_cover",
     "CREATE INDEX IF NOT EXISTS idx_rsic_user_date_cover "
     "ON rpt_route_sales_by_item_customer(user_code, date) "
     "INCLUDE (total_sales, total_gr_sales, total_damage_sales, total_expiry_sales, route_code, item_code, customer_code)"),

    # Partial: only rows with sales > 0 — items_sold, endorsement WHERE total_sales > 0
    ("idx_rsic_sales_positive",
     "CREATE INDEX IF NOT EXISTS idx_rsic_sales_positive "
     "ON rpt_route_sales_by_item_customer(user_code, date, total_sales) "
     "WHERE total_sales > 0"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_sales_detail  (4.8 GB, 7M rows)
    # dashboard fallback, daily_sales_overview, revenue_dispersion,
    # weekly_sales_returns, eot_status
    # ──────────────────────────────────────────────────────────────────────────

    # type + status + user + date — revenue_dispersion main filter
    ("idx_sd_type_status_user_date",
     "CREATE INDEX IF NOT EXISTS idx_sd_type_status_user_date "
     "ON rpt_sales_detail(trx_type, trx_status, user_code, trx_date)"),

    # org + type + status + date — daily_sales_overview by org
    ("idx_sd_org_type_date",
     "CREATE INDEX IF NOT EXISTS idx_sd_org_type_date "
     "ON rpt_sales_detail(sales_org_code, trx_type, trx_status, trx_date)"),

    # Partial covering: sales-only rows — dashboard CTE, daily_sales_overview
    ("idx_sd_sales_type1",
     "CREATE INDEX IF NOT EXISTS idx_sd_sales_type1 "
     "ON rpt_sales_detail(trx_date, user_code, route_code, customer_code, net_amount) "
     "WHERE trx_type = 1"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_customer_visits  (380 MB, 799K rows)
    # dashboard, daily_sales_overview, customer_attendance, endorsement,
    # journey_plan_compliance, mtd_sales_overview, salesman_journey
    # ──────────────────────────────────────────────────────────────────────────

    # user + date + is_productive — endorsement, mtd_sales_overview productive filter
    ("idx_rcv_user_date_prod",
     "CREATE INDEX IF NOT EXISTS idx_rcv_user_date_prod "
     "ON rpt_customer_visits(user_code, date, is_productive)"),

    # org + date + is_productive — customer_attendance by org
    ("idx_rcv_org_date_prod",
     "CREATE INDEX IF NOT EXISTS idx_rcv_org_date_prod "
     "ON rpt_customer_visits(sales_org_code, date, is_productive)"),

    # customer + date — endorsement, daily_sales_overview customer drill
    ("idx_rcv_customer_date",
     "CREATE INDEX IF NOT EXISTS idx_rcv_customer_date "
     "ON rpt_customer_visits(customer_code, date)"),

    # route + customer + date — endorsement JOIN
    ("idx_rcv_route_customer_date",
     "CREATE INDEX IF NOT EXISTS idx_rcv_route_customer_date "
     "ON rpt_customer_visits(route_code, customer_code, date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_journey_plan  (115 MB, 890K rows)
    # dashboard, endorsement, journey_plan_compliance, mtd_sales_overview
    # ──────────────────────────────────────────────────────────────────────────

    # route + date — journey_plan_compliance, endorsement
    ("idx_jp_route_date",
     "CREATE INDEX IF NOT EXISTS idx_jp_route_date "
     "ON rpt_journey_plan(route_code, date)"),

    # user + customer + date — endorsement match
    ("idx_jp_user_customer_date",
     "CREATE INDEX IF NOT EXISTS idx_jp_user_customer_date "
     "ON rpt_journey_plan(user_code, customer_code, date)"),

    # route + customer + date — dashboard coverage CTE
    ("idx_jp_route_customer_date",
     "CREATE INDEX IF NOT EXISTS idx_jp_route_customer_date "
     "ON rpt_journey_plan(route_code, customer_code, date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_outstanding  (576 MB, 2.1M rows)
    # outstanding_collection — filters WHERE balance_amount > 0
    # ──────────────────────────────────────────────────────────────────────────

    # Partial: only open invoices — outstanding_collection main query
    ("idx_out_open",
     "CREATE INDEX IF NOT EXISTS idx_out_open "
     "ON rpt_outstanding(org_code, user_code, trx_date) "
     "WHERE balance_amount > 0"),

    # org + customer — outstanding by customer drill-down
    ("idx_out_org_customer",
     "CREATE INDEX IF NOT EXISTS idx_out_org_customer "
     "ON rpt_outstanding(org_code, customer_code, balance_amount)"),

    # Covering for aging report
    ("idx_out_aging_cover",
     "CREATE INDEX IF NOT EXISTS idx_out_aging_cover "
     "ON rpt_outstanding(org_code, aging_bucket) "
     "INCLUDE (balance_amount, original_amount, pending_amount, customer_code, customer_name, days_overdue)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_route_sales_summary_by_item  (218 MB, 919K rows)
    # dashboard, market_sales, log_report, brand_wise_sales,
    # sales_performance, target_achievement, weekly_sales_returns
    # ──────────────────────────────────────────────────────────────────────────

    # brand + date — brand_wise_sales, target_achievement
    ("idx_rss_brand_date",
     "CREATE INDEX IF NOT EXISTS idx_rss_brand_date "
     "ON rpt_route_sales_summary_by_item(brand_code, date)"),

    # category + date — brand_wise_sales category filter
    ("idx_rss_category_date",
     "CREATE INDEX IF NOT EXISTS idx_rss_category_date "
     "ON rpt_route_sales_summary_by_item(category_code, date)"),

    # user + route + date — log_report, sales_performance per-user
    ("idx_rss_user_route_date",
     "CREATE INDEX IF NOT EXISTS idx_rss_user_route_date "
     "ON rpt_route_sales_summary_by_item(user_code, route_code, date)"),

    # Covering: route+item+date including all metric cols — dashboard DISTINCT ON
    ("idx_rss_route_item_date_cover",
     "CREATE INDEX IF NOT EXISTS idx_rss_route_item_date_cover "
     "ON rpt_route_sales_summary_by_item(route_code, item_code, date) "
     "INCLUDE (total_sales, total_wastage, target_amount, sales_org_code, total_sales_with_tax)"),

    # org + route + date — market_sales by org+route
    ("idx_rss_org_route_date",
     "CREATE INDEX IF NOT EXISTS idx_rss_org_route_date "
     "ON rpt_route_sales_summary_by_item(sales_org_code, route_code, date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_collections  (168 MB, 741K rows)
    # dashboard fallback, salesman_journey, log_report, sales_performance
    # ──────────────────────────────────────────────────────────────────────────

    # user + route + date — salesman_journey, log_report
    ("idx_col_user_route_date",
     "CREATE INDEX IF NOT EXISTS idx_col_user_route_date "
     "ON rpt_collections(user_code, route_code, receipt_date)"),

    # org + user + date — log_report, sales_performance
    ("idx_col_org_user_date",
     "CREATE INDEX IF NOT EXISTS idx_col_org_user_date "
     "ON rpt_collections(sales_org_code, user_code, receipt_date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_route_sales_collection  (small — used by dashboard heavily)
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_rsc_date",
     "CREATE INDEX IF NOT EXISTS idx_rsc_date "
     "ON rpt_route_sales_collection(date)"),

    ("idx_rsc_user_date",
     "CREATE INDEX IF NOT EXISTS idx_rsc_user_date "
     "ON rpt_route_sales_collection(user_code, date)"),

    ("idx_rsc_route_date",
     "CREATE INDEX IF NOT EXISTS idx_rsc_route_date "
     "ON rpt_route_sales_collection(route_code, date)"),

    ("idx_rsc_org_date",
     "CREATE INDEX IF NOT EXISTS idx_rsc_org_date "
     "ON rpt_route_sales_collection(sales_org_code, date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_coverage_summary  (18K rows — small but hit on every dashboard load)
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_cov_visit_user",
     "CREATE INDEX IF NOT EXISTS idx_cov_visit_user "
     "ON rpt_coverage_summary(visit_date, user_code)"),

    ("idx_cov_visit_route",
     "CREATE INDEX IF NOT EXISTS idx_cov_visit_route "
     "ON rpt_coverage_summary(visit_date, route_code)"),

    ("idx_cov_visit_org",
     "CREATE INDEX IF NOT EXISTS idx_cov_visit_org "
     "ON rpt_coverage_summary(visit_date, sales_org_code)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_invoice_totals  (93 MB, 558K rows)
    # dashboard fallback, daily_sales_overview
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_it_user_date",
     "CREATE INDEX IF NOT EXISTS idx_it_user_date "
     "ON rpt_invoice_totals(user_code, trx_date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_eot  (10 MB, 48K rows)
    # eot_status report
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_eot_org_date",
     "CREATE INDEX IF NOT EXISTS idx_eot_org_date "
     "ON rpt_eot(sales_org_code, trip_date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # rpt_journeys  (small — time_management, mtd_attendance, salesman_journey)
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_jour_user_date",
     "CREATE INDEX IF NOT EXISTS idx_jour_user_date "
     "ON rpt_journeys(user_code, date)"),

    ("idx_jour_org_date",
     "CREATE INDEX IF NOT EXISTS idx_jour_org_date "
     "ON rpt_journeys(sales_org_code, date)"),

    ("idx_jour_route_date",
     "CREATE INDEX IF NOT EXISTS idx_jour_route_date "
     "ON rpt_journeys(route_code, date)"),

    # ──────────────────────────────────────────────────────────────────────────
    # dim_customer  (97 MB, 155K rows)
    # EXISTS subqueries for channel filter across many reports
    # ──────────────────────────────────────────────────────────────────────────

    # Channel filter: EXISTS(SELECT 1 FROM dim_customer WHERE code=x AND channel_code IN (...))
    ("idx_dim_cust_code_channel",
     "CREATE INDEX IF NOT EXISTS idx_dim_cust_code_channel "
     "ON dim_customer(code, channel_code)"),

    ("idx_dim_cust_channel",
     "CREATE INDEX IF NOT EXISTS idx_dim_cust_channel "
     "ON dim_customer(channel_code)"),

    ("idx_dim_cust_org",
     "CREATE INDEX IF NOT EXISTS idx_dim_cust_org "
     "ON dim_customer(sales_org_code)"),

    # ──────────────────────────────────────────────────────────────────────────
    # dim_route  (small — used in JOINs by RSIC queries on every report)
    # ──────────────────────────────────────────────────────────────────────────

    # RSIC JOIN: dim_route ON route_code AND sales_org_code IN (...)
    ("idx_dim_route_org_code",
     "CREATE INDEX IF NOT EXISTS idx_dim_route_org_code "
     "ON dim_route(sales_org_code, code)"),

    # Dashboard: JOIN ON has_active_assignment = true
    ("idx_dim_route_active_assign",
     "CREATE INDEX IF NOT EXISTS idx_dim_route_active_assign "
     "ON dim_route(has_active_assignment, code)"),

    # ──────────────────────────────────────────────────────────────────────────
    # dim_item  (small — JOINed for brand/category filter)
    # ──────────────────────────────────────────────────────────────────────────

    ("idx_dim_item_brand",
     "CREATE INDEX IF NOT EXISTS idx_dim_item_brand "
     "ON dim_item(brand_code, code)"),

    ("idx_dim_item_category",
     "CREATE INDEX IF NOT EXISTS idx_dim_item_category "
     "ON dim_item(category_code, code)"),

]

# ── Run ───────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  NFPC Reports — Index Creation ({len(INDEXES)} indexes)")
print(f"{'='*60}\n")

ok = skipped = failed = 0
total_start = time.time()

for name, sql in INDEXES:
    t = time.time()
    try:
        cur.execute(sql)
        elapsed = (time.time() - t) * 1000
        # If it took <5ms it likely already existed
        status = "SKIP" if elapsed < 5 else "OK  "
        print(f"  {status}  {name:<45} {elapsed:6.0f}ms")
        if elapsed < 5:
            skipped += 1
        else:
            ok += 1
    except Exception as e:
        print(f"  FAIL  {name:<45} {e}")
        failed += 1

total = (time.time() - total_start)
print(f"\n{'='*60}")
print(f"  Created: {ok}   Already existed: {skipped}   Failed: {failed}")
print(f"  Total time: {total:.1f}s")
print(f"{'='*60}\n")

cur.close()
conn.close()
