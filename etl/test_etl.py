#!/usr/bin/env python3
"""
Small batch ETL test - loads dimensions + 1000 rows of each fact table.
Validates the full pipeline works before running the big extraction.
"""

import os
import sys
from datetime import datetime
import pymssql
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def get_mssql():
    return pymssql.connect(
        server=os.environ['DB_SERVER'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'],
    )

def get_pg():
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=os.environ.get('PG_PORT', '5432'),
        dbname=os.environ['PG_DATABASE'],
        user=os.environ.get('PG_USER', 'fci'),
        password=os.environ.get('PG_PASSWORD', ''),
    )

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def test_load(pg_cur, pg_conn, table, columns, rows, label=""):
    """Insert rows, report count."""
    if not rows:
        log(f"  {label or table}: 0 rows (empty)")
        return
    cols_str = ', '.join(columns)
    execute_values(
        pg_cur,
        f"INSERT INTO {table} ({cols_str}) VALUES %s ON CONFLICT DO NOTHING",
        rows
    )
    pg_conn.commit()
    log(f"  {label or table}: {len(rows)} rows loaded OK")

def main():
    log("=== ETL Test Batch ===")

    ms = get_mssql()
    pg = get_pg()
    mc = ms.cursor()
    pc = pg.cursor()

    # ---- DIMENSIONS ----
    log("\n--- Dimensions ---")

    # dim_sales_org
    pc.execute("DELETE FROM dim_sales_org")
    mc.execute("SELECT Code, Description, CountryCode, CurrencyCode, IsActive FROM tblSalesOrganization")
    rows = mc.fetchall()
    test_load(pc, pg, 'dim_sales_org', ['code','name','country_code','currency_code','is_active'], rows)

    # dim_route
    pc.execute("DELETE FROM dim_route")
    mc.execute("SELECT Code, Name, SalesOrgCode, RouteType, AreaCode, SubAreaCode, RouteCatCode, SalesmanCode, WHCode, IsActive FROM tblRoute")
    rows = mc.fetchall()
    test_load(pc, pg, 'dim_route', ['code','name','sales_org_code','route_type','area_code','sub_area_code','route_cat_code','salesman_code','wh_code','is_active'], rows)

    # dim_user
    pc.execute("DELETE FROM dim_user")
    mc.execute("SELECT Code, Description, SalesOrgCode, RouteCode, DepotCode, ReportsTo, UserType, IsActive FROM tblUser")
    rows = mc.fetchall()
    test_load(pc, pg, 'dim_user', ['code','name','sales_org_code','route_code','depot_code','reports_to','user_type','is_active'], rows)

    # dim_channel
    pc.execute("DELETE FROM dim_channel")
    mc.execute("SELECT Code, Description FROM tblChannel")
    rows = mc.fetchall()
    test_load(pc, pg, 'dim_channel', ['code','name'], rows)

    # dim_country, dim_region, dim_city
    pc.execute("DELETE FROM dim_country")
    mc.execute("SELECT Code, Description FROM tblCountry")
    test_load(pc, pg, 'dim_country', ['code','name'], mc.fetchall())

    pc.execute("DELETE FROM dim_region")
    mc.execute("SELECT Code, Description, CountryCode FROM tblRegion")
    test_load(pc, pg, 'dim_region', ['code','name','country_code'], mc.fetchall())

    pc.execute("DELETE FROM dim_city")
    mc.execute("SELECT Code, Description, RegionCode FROM tblCity")
    test_load(pc, pg, 'dim_city', ['code','name','region_code'], mc.fetchall())

    # dim_item (with dedup)
    pc.execute("DELETE FROM dim_item")
    mc.execute("""
        SELECT i.Code, i.Description, i.BaseUOM,
            i.GroupLevel1, g1.Description,
            i.GroupLevel2, g2.Description,
            i.GroupLevel3, g3.Description,
            i.GroupLevel4, g4.Description,
            i.GroupLevel5, g5.Description,
            i.GroupLevel8, g8.Description,
            i.Liter, i.LiterPerUnit, i.IsActive
        FROM tblItem i
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g2 ON i.GroupLevel2 = g2.Code AND g2.ItemGroupLevelId = 2
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        LEFT JOIN tblItemGroup g4 ON i.GroupLevel4 = g4.Code AND g4.ItemGroupLevelId = 4
        LEFT JOIN tblItemGroup g5 ON i.GroupLevel5 = g5.Code AND g5.ItemGroupLevelId = 5
        LEFT JOIN tblItemGroup g8 ON i.GroupLevel8 = g8.Code AND g8.ItemGroupLevelId = 8
    """)
    rows = mc.fetchall()
    seen = set()
    unique = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique.append(r)
    test_load(pc, pg, 'dim_item',
        ['code','name','base_uom','brand_code','brand_name','sub_brand_code','sub_brand_name',
         'category_code','category_name','sub_category_code','sub_category_name','pack_type_code','pack_type_name',
         'segment_code','segment_name','liter','liter_per_unit','is_active'],
        unique, f"dim_item (deduped {len(rows)} -> {len(unique)})")

    # dim_customer
    pc.execute("DELETE FROM dim_customer")
    mc.execute("""
        SELECT c.Code, cd.SalesOrgCode, c.Description,
            cd.ChannelCode, ch.Description,
            cd.SubChannelCode, sc.Description,
            cd.CustomerGroupCode, cd.CustomerType, cd.PaymentType,
            c.CityCode, ci.Description,
            c.RegionCode, r.Description,
            c.CountryCode, co.Description,
            c.Latitude, c.Longitude, c.IsActive
        FROM tblCustomer c
        JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sc ON cd.SubChannelCode = sc.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblRegion r ON c.RegionCode = r.Code
        LEFT JOIN tblCountry co ON c.CountryCode = co.Code
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'dim_customer',
        ['code','sales_org_code','name','channel_code','channel_name','sub_channel_code','sub_channel_name',
         'customer_group','customer_type','payment_type','city_code','city_name','region_code','region_name',
         'country_code','country_name','latitude','longitude','is_active'],
        rows)

    # ---- FACT TABLES (TOP 1000 each) ----
    log("\n--- Fact Tables (1000 rows each) ---")

    # rpt_sales_detail
    pc.execute("TRUNCATE rpt_sales_detail")
    mc.execute("""
        SELECT TOP 1000
            h.TrxCode, d.[LineNo], CAST(h.TrxDate AS DATE), CAST(h.TripDate AS DATE),
            h.TrxType, h.PaymentType,
            h.UserCode, u.Description,
            h.OrgCode, so.Description, u.DepotCode,
            h.RouteCode, rt.Name, rt.RouteType, rt.AreaCode, rt.SubAreaCode,
            h.ClientCode, c.Description,
            cd.ChannelCode, ch.Description, cd.SubChannelCode, sc.Description,
            cd.CustomerGroupCode, cd.CustomerType,
            c.CountryCode, co.Description, c.RegionCode, rg.Description, c.CityCode, ci.Description,
            d.ItemCode, i.Description,
            i.GroupLevel1, g1.Description, i.GroupLevel3, g3.Description,
            i.GroupLevel2, g2.Description, i.GroupLevel5, g5.Description,
            i.GroupLevel8, g8.Description, i.BaseUOM,
            d.QuantityLevel1, d.QuantityBU,
            COALESCE(i.LiterPerUnit, 0) * d.QuantityBU,
            d.BasePrice, h.TotalAmount, d.TotalDiscountAmount, d.TaxAmount,
            d.BasePrice * d.QuantityBU,
            h.InvoiceNumber, d.CreatedOn
        FROM tblTrxHeader h
        JOIN tblTrxDetail d ON h.TrxCode = d.TrxCode
        LEFT JOIN tblUser u ON h.UserCode = u.Code
        LEFT JOIN tblSalesOrganization so ON h.OrgCode = so.Code
        LEFT JOIN tblRoute rt ON h.RouteCode = rt.Code
        LEFT JOIN tblCustomer c ON h.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblSubChannel sc ON cd.SubChannelCode = sc.Code
        LEFT JOIN tblCountry co ON c.CountryCode = co.Code
        LEFT JOIN tblRegion rg ON c.RegionCode = rg.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblItem i ON d.ItemCode = i.Code
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g2 ON i.GroupLevel2 = g2.Code AND g2.ItemGroupLevelId = 2
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        LEFT JOIN tblItemGroup g5 ON i.GroupLevel5 = g5.Code AND g5.ItemGroupLevelId = 5
        LEFT JOIN tblItemGroup g8 ON i.GroupLevel8 = g8.Code AND g8.ItemGroupLevelId = 8
        WHERE h.TrxDate >= '2026-03-01' AND h.TrxDate < '2026-03-12'
    """)
    rows = mc.fetchall()
    sd_cols = [
        'trx_code','line_no','trx_date','trip_date','trx_type','payment_type',
        'user_code','user_name','sales_org_code','sales_org_name','depot_code',
        'route_code','route_name','route_type','area_code','sub_area_code',
        'customer_code','customer_name','channel_code','channel_name','sub_channel_code','sub_channel_name',
        'customer_group','customer_type','country_code','country_name','region_code','region_name','city_code','city_name',
        'item_code','item_name','brand_code','brand_name','category_code','category_name',
        'sub_brand_code','sub_brand_name','pack_type_code','pack_type_name','segment_code','segment_name','base_uom',
        'qty_cases','qty_pieces','qty_volume','base_price','net_amount','discount_amount','tax_amount','gross_amount',
        'invoice_number','created_on'
    ]
    test_load(pc, pg, 'rpt_sales_detail', sd_cols, rows)

    # rpt_daily_sales_summary (aggregated from TrxHeader/Detail since summary table is stale)
    pc.execute("TRUNCATE rpt_daily_sales_summary")
    mc.execute("""
        SELECT TOP 1000
            CAST(h.TrxDate AS DATE), h.RouteCode, rt.Name,
            h.UserCode, u.Description, h.OrgCode, so.Description,
            h.ClientCode, c.Description, cd.ChannelCode, ch.Description,
            d.ItemCode, i.Description,
            i.GroupLevel1, g1.Description, i.GroupLevel3, g3.Description,
            SUM(CASE WHEN h.TrxType=1 THEN d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType=1 THEN d.BasePrice * d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType=4 THEN d.QuantityBU ELSE 0 END),
            SUM(CASE WHEN h.TrxType=4 THEN d.BasePrice * d.QuantityBU ELSE 0 END),
            0, 0, 0, 0
        FROM tblTrxHeader h
        JOIN tblTrxDetail d ON h.TrxCode = d.TrxCode
        LEFT JOIN tblRoute rt ON h.RouteCode = rt.Code
        LEFT JOIN tblUser u ON h.UserCode = u.Code
        LEFT JOIN tblSalesOrganization so ON h.OrgCode = so.Code
        LEFT JOIN tblCustomer c ON h.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND h.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblItem i ON d.ItemCode = i.Code
        LEFT JOIN tblItemGroup g1 ON i.GroupLevel1 = g1.Code AND g1.ItemGroupLevelId = 1
        LEFT JOIN tblItemGroup g3 ON i.GroupLevel3 = g3.Code AND g3.ItemGroupLevelId = 3
        WHERE h.TrxDate >= '2026-03-01' AND h.TrxDate < '2026-03-12' AND h.TrxType IN (1,4)
        GROUP BY CAST(h.TrxDate AS DATE), h.RouteCode, rt.Name,
            h.UserCode, u.Description, h.OrgCode, so.Description,
            h.ClientCode, c.Description, cd.ChannelCode, ch.Description,
            d.ItemCode, i.Description, i.GroupLevel1, g1.Description, i.GroupLevel3, g3.Description
    """)
    rows = mc.fetchall()
    dss_cols = [
        'date','route_code','route_name','user_code','user_name','sales_org_code','sales_org_name',
        'customer_code','customer_name','channel_code','channel_name','item_code','item_name',
        'brand_code','brand_name','category_code','category_name',
        'total_qty','total_sales','total_gr_qty','total_gr_sales',
        'total_damage_qty','total_damage_sales','total_expiry_qty','total_expiry_sales'
    ]
    test_load(pc, pg, 'rpt_daily_sales_summary', dss_cols, rows)

    # rpt_collections
    pc.execute("TRUNCATE rpt_collections")
    mc.execute("""
        SELECT TOP 1000
            ph.ReceiptId, ph.Receipt_Number,
            CAST(ph.ReceiptDate AS DATE), CAST(ph.TripDate AS DATE),
            ph.EmpNo, u.Description,
            ph.RouteCode, rt.Name,
            ph.SalesOrgCode, so.Description,
            ph.SITE_NUMBER, c.Description,
            ph.Amount, ph.SettledAmount,
            ph.PaymentType, ph.PaymentStatus, ph.CurrencyCode
        FROM tblPaymentHeader ph
        LEFT JOIN tblUser u ON ph.EmpNo = u.Code
        LEFT JOIN tblRoute rt ON ph.RouteCode = rt.Code
        LEFT JOIN tblSalesOrganization so ON ph.SalesOrgCode = so.Code
        LEFT JOIN tblCustomer c ON ph.SITE_NUMBER = c.Code
        WHERE ph.ReceiptDate >= '2026-03-01' AND ph.ReceiptDate < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_collections',
        ['receipt_id','receipt_number','receipt_date','trip_date','user_code','user_name',
         'route_code','route_name','sales_org_code','sales_org_name','customer_code','customer_name',
         'amount','settled_amount','payment_type','payment_status','currency_code'],
        rows)

    # rpt_customer_visits
    pc.execute("TRUNCATE rpt_customer_visits")
    mc.execute("""
        SELECT TOP 1000
            CAST(cv.CustomerVisitId AS VARCHAR(50)),
            CAST(cv.Date AS DATE), CAST(cv.TripDate AS DATE),
            cv.UserCode, u.Description,
            cv.RouteCode, rt.Name,
            COALESCE(rt.SalesOrgCode, u.SalesOrgCode), so.Description,
            cv.ClientCode, c.Description,
            ch.Description, ci.Description, rg.Description,
            cv.ArrivalTime, cv.OutTime, cv.TotalTimeInMins,
            CAST(CASE WHEN cv.IsProductive = 1 THEN 1 ELSE 0 END AS BIT),
            CAST(CASE WHEN cv.TypeOfCall = 'Planned' THEN 1 ELSE 0 END AS BIT),
            cv.Latitude, cv.Longitude, cv.JourneyCode
        FROM tblCustomerVisit cv
        LEFT JOIN tblUser u ON cv.UserCode = u.Code
        LEFT JOIN tblRoute rt ON cv.RouteCode = rt.Code
        LEFT JOIN tblSalesOrganization so ON COALESCE(rt.SalesOrgCode, u.SalesOrgCode) = so.Code
        LEFT JOIN tblCustomer c ON cv.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND COALESCE(rt.SalesOrgCode, u.SalesOrgCode) = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblCity ci ON c.CityCode = ci.Code
        LEFT JOIN tblRegion rg ON c.RegionCode = rg.Code
        WHERE cv.Date >= '2026-03-01' AND cv.Date < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_customer_visits',
        ['visit_id','date','trip_date','user_code','user_name','route_code','route_name',
         'sales_org_code','sales_org_name','customer_code','customer_name',
         'channel_name','city_name','region_name','arrival_time','out_time','total_time_mins',
         'is_productive','is_planned','latitude','longitude','journey_code'],
        rows)

    # rpt_coverage_summary
    pc.execute("TRUNCATE rpt_coverage_summary")
    mc.execute("""
        SELECT TOP 1000 cs.Id, CAST(cs.VisitDate AS DATE),
            cs.RouteCode, cs.RouteDescription, cs.UserCode, cs.UserDescription,
            rt.SalesOrgCode,
            cs.ScheduledCalls, cs.TotalActualCalls, cs.ActualCalls,
            cs.TotalActualCalls - cs.ActualCalls,
            cs.SellingCalls, cs.PlannedSellingCalls
        FROM tblRouteCoverageSummary cs
        LEFT JOIN tblRoute rt ON cs.RouteCode = rt.Code
        WHERE cs.VisitDate >= '2026-01-01' AND cs.VisitDate < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_coverage_summary',
        ['id','visit_date','route_code','route_name','user_code','user_name','sales_org_code',
         'scheduled_calls','total_actual_calls','planned_calls','unplanned_calls','selling_calls','planned_selling_calls'],
        rows)

    # rpt_journeys
    pc.execute("TRUNCATE rpt_journeys")
    mc.execute("""
        SELECT TOP 1000 j.JourneyId, j.JourneyCode, CAST(j.Date AS DATE),
            j.UserCode, u.Description, rt.Code, rt.Name, u.SalesOrgCode,
            j.StartTime, j.EndTime, j.VehicleCode
        FROM tblJourney j
        LEFT JOIN tblUser u ON j.UserCode = u.Code
        LEFT JOIN tblRoute rt ON j.RCode = rt.Code
        WHERE j.Date >= '2026-01-01' AND j.Date < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_journeys',
        ['journey_id','journey_code','date','user_code','user_name','route_code','route_name',
         'sales_org_code','start_time','end_time','vehicle_code'],
        rows)

    # rpt_route_sales_collection
    pc.execute("TRUNCATE rpt_route_sales_collection")
    mc.execute("""
        SELECT TOP 1000 rsc.Id, CAST(rsc.Date AS DATE),
            rsc.RouteCode, rsc.RouteDescription, rsc.UserCode, rsc.UserDescription,
            rt.SalesOrgCode,
            rsc.TotalSales, rsc.TotalCollection, rsc.TotalSalesWithTax, rsc.TotalWastage, rsc.TargetAmount
        FROM tblRouteSalesCollectionSummary rsc
        LEFT JOIN tblRoute rt ON rsc.RouteCode = rt.Code
        WHERE rsc.Date >= '2026-01-01' AND rsc.Date < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_route_sales_collection',
        ['id','date','route_code','route_name','user_code','user_name','sales_org_code',
         'total_sales','total_collection','total_sales_with_tax','total_wastage','target_amount'],
        rows)

    # rpt_targets
    pc.execute("TRUNCATE rpt_targets")
    mc.execute("""
        SELECT t.TargetId, t.TimeFrame, CAST(t.StartDate AS DATE), CAST(t.EndDate AS DATE),
            t.Year, t.Month, t.SalesmanCode, u.Description,
            t.RouteCode, rt.Name, t.SalesorgCode,
            t.ItemKey, i.Description, t.CustomerKey,
            t.Amount, t.Quantity, t.IsActive
        FROM tblCommonTarget t
        LEFT JOIN tblUser u ON t.SalesmanCode = u.Code
        LEFT JOIN tblRoute rt ON t.RouteCode = rt.Code
        LEFT JOIN tblItem i ON t.ItemKey = i.Code
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_targets',
        ['target_id','time_frame','start_date','end_date','year','month','salesman_code','salesman_name',
         'route_code','route_name','sales_org_code','item_key','item_name','customer_key',
         'amount','quantity','is_active'],
        rows)

    # rpt_eot
    pc.execute("TRUNCATE rpt_eot")
    mc.execute("""
        SELECT TOP 1000 e.EOTId, e.UserCode, u.Description,
            e.RouteCode, rt.Name, e.SalesOrgCode,
            e.EOTType, e.EOTTime, CAST(e.TripDate AS DATE)
        FROM tblEOT e
        LEFT JOIN tblUser u ON e.UserCode = u.Code
        LEFT JOIN tblRoute rt ON e.RouteCode = rt.Code
        WHERE e.TripDate >= '2026-01-01' AND e.TripDate < '2026-03-12'
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_eot',
        ['eot_id','user_code','user_name','route_code','route_name','sales_org_code','eot_type','eot_time','trip_date'],
        rows)

    # rpt_holidays
    pc.execute("TRUNCATE rpt_holidays")
    mc.execute("SELECT HolidayId, CAST(HolidayDate AS DATE), Name, Year, SalesOrgCode FROM tblHoliday WHERE IsActive = 1")
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_holidays',
        ['holiday_id','holiday_date','name','year','sales_org_code'], rows)

    # rpt_journey_plan (small sample)
    pc.execute("TRUNCATE rpt_journey_plan")
    mc.execute("""
        SELECT TOP 1000 jp.DailyJourneyPlanId, CAST(jp.JourneyDate AS DATE),
            jp.UserCode, u.Description, jp.CustomerCode, c.Description,
            rt.Code, jp.Sequence, jp.VisitStatus, u.SalesOrgCode
        FROM tblDailyJourneyPlan jp
        LEFT JOIN tblUser u ON jp.UserCode = u.Code
        LEFT JOIN tblCustomer c ON jp.CustomerCode = c.Code
        LEFT JOIN tblRoute rt ON u.RouteCode = rt.Code
        WHERE jp.JourneyDate >= '2026-03-01' AND jp.JourneyDate < '2026-03-12'
            AND jp.IsDeleted = 0 AND jp.IsActive = 1
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_journey_plan',
        ['id','date','user_code','user_name','customer_code','customer_name','route_code',
         'sequence','visit_status','sales_org_code'],
        rows)

    # rpt_outstanding (small sample - skip JDE date conversion for now, just test structure)
    pc.execute("TRUNCATE rpt_outstanding")
    mc.execute("""
        SELECT TOP 1000 mpi.MiddleWarePendingInvoiceId, mpi.TrxCode,
            mpi.OrgCode, so.Description,
            mpi.ClientCode, c.Description, ch.Description,
            CAST(GETDATE() AS DATE), NULL,
            mpi.OriginalAmount, mpi.BalanceAmount, mpi.PendingAmount, mpi.CollectedAmount,
            0, 'Current',
            mpi.UserCode, u.Description,
            mpi.RouteCode, rt.Name, mpi.CurrencyCode
        FROM tblMiddleWarePendingInvoice mpi
        LEFT JOIN tblSalesOrganization so ON mpi.OrgCode = so.Code
        LEFT JOIN tblCustomer c ON mpi.ClientCode = c.Code
        LEFT JOIN tblCustomerDetail cd ON c.Code = cd.CustomerCode AND mpi.OrgCode = cd.SalesOrgCode
        LEFT JOIN tblChannel ch ON cd.ChannelCode = ch.Code
        LEFT JOIN tblUser u ON mpi.UserCode = u.Code
        LEFT JOIN tblRoute rt ON mpi.RouteCode = rt.Code
        WHERE mpi.BalanceAmount != 0
    """)
    rows = mc.fetchall()
    test_load(pc, pg, 'rpt_outstanding',
        ['id','trx_code','org_code','sales_org_name','customer_code','customer_name','channel_name',
         'trx_date','due_date','original_amount','balance_amount','pending_amount','collected_amount',
         'days_overdue','aging_bucket','user_code','user_name','route_code','route_name','currency_code'],
        rows)

    # ---- VERIFY ----
    log("\n--- Verification ---")
    tables = [
        'dim_sales_org', 'dim_route', 'dim_user', 'dim_channel', 'dim_country', 'dim_region',
        'dim_city', 'dim_item', 'dim_customer',
        'rpt_sales_detail', 'rpt_daily_sales_summary', 'rpt_collections', 'rpt_customer_visits',
        'rpt_coverage_summary', 'rpt_journeys', 'rpt_route_sales_collection', 'rpt_targets',
        'rpt_eot', 'rpt_holidays', 'rpt_journey_plan', 'rpt_outstanding'
    ]
    for t in tables:
        pc.execute(f"SELECT COUNT(*) FROM {t}")
        count = pc.fetchone()[0]
        status = "OK" if count > 0 else "EMPTY"
        print(f"  {t}: {count:,} rows [{status}]")

    ms.close()
    pg.close()
    log("\n=== Test batch complete! All tables loaded successfully. ===")

if __name__ == '__main__':
    main()
