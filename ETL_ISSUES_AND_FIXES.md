# NFPC Reports — Complete ETL & API Issues Log

**Period:** 2026-03-17 to 2026-03-18
**Scope:** Full alignment of PostgreSQL API with MSSQL stored procedures across all report pages

---

## PART 1: ETL / Data Pipeline Issues

### 1. Missing ETL Table: `tblRouteSalesSummaryByItem`
- **Impact:** Dashboard total sales, targets, daily/weekly trends all wrong
- **Fix:** Added `rpt_route_sales_summary_by_item` table, ETL loader, unique index on `(route_code, item_code, date)`

### 2. Missing ETL Table: `tblRouteSalesSummaryByItemCustomer`
- **Impact:** Sales performance, SKU counts, MTD wastage, brand sales, endorsement — all used raw `rpt_sales_detail` with double-counting
- **Fix:** Added `rpt_route_sales_by_item_customer` table (24M rows), ETL loader with quarterly chunking
- **Note:** This table was stale on MSSQL since Sep 2025. Had to run `RouteSalesSummaryByIC_Insert` SP to populate Jan-Mar 2026

### 3. Missing Column: `trx_status` in `rpt_sales_detail`
- **Impact:** Could not filter by `TRXStatus=200` (confirmed transactions only), inflating invoice counts
- **Fix:** Added `trx_status INT` column, updated ETL to include `h.TRXStatus`

### 4. Duplicate Rows in `rpt_route_sales_summary_by_item`
- **Impact:** Sales values 2x actual (1.54M vs 1.32M)
- **Root cause:** No unique constraint, re-running ETL/SP created duplicates
- **Fix:** Deleted 709K dupes, added `CREATE UNIQUE INDEX idx_rssi_unique ON (route_code, item_code, date)`

### 5. MSSQL Summary Tables Not Populated
- **Tables affected:** `tblRouteSalesSummaryByItem` (max Jan 29), `tblRouteSalesCollectionSummary` (max Jan 29), `tblRouteCoverageSummary` (max Feb 25)
- **Root cause:** SQL Agent jobs stopped, INSERT statements commented out in SPs
- **Fix:** Uncommented INSERTs via `ALTER PROCEDURE`, ran populate SPs for Mar 1-8, used `autocommit=True` for pymssql

### 6. MSSQL Connection Timeouts
- **Impact:** ETL for large tables (24M rows) failed after ~60 min
- **Fix:** Chunked ETL approach — quarterly chunks for `rpt_route_sales_by_item_customer`, 2-week chunks for `rpt_sales_detail`, with proper connection cleanup between chunks

### 7. pymssql autocommit Behavior
- **Impact:** Inserts appeared successful but were silently rolled back
- **Fix:** Use `autocommit=True` for all write operations

### 8. `dim_item` Wrong GroupLevel Mapping
- **Old mapping:** GroupLevel1→Brand, GroupLevel2→SubBrand (WRONG)
- **Correct mapping:** GroupLevel1→Agency(Level 0), GroupLevel2→Brand(Level 1), GroupLevel3→SubBrand(Level 2), GroupLevel4→Category(Level 3)
- **Fix:** Rewrote ETL with correct `tblItemGroup.ItemGroupLevelId` joins, added UOM conversions from `tblItemUom`

### 9. `dim_user` Schema Mismatch
- **Impact:** ETL failed with "column email does not exist"
- **Root cause:** `dim_user` was expanded with new columns (email, username, role_code, etc.) but ETL query not updated
- **Fix:** Updated ETL to match new schema with flat join across `tblUser`, `tblUserRole`, `tblUserDetails`, `DepotMaster`

---

## PART 2: API Double-Counting Issues

### 10. `net_amount` Header-Level Duplication (CRITICAL — affected ALL pages)
- **Root cause:** `rpt_sales_detail.net_amount` = `tblTrxHeader.TotalAmount` (header-level), repeated on every detail line. `SUM(net_amount)` multiplied by number of lines per transaction
- **Pages affected:** Dashboard, Sales Performance, Daily Sales Overview, MTD Sales Overview, Brand Wise Sales, Top Customers, Top Products, Weekly Sales Returns, Revenue Dispersion, Monthly Sales Stock, Log Report, Time Management, Endorsement
- **Fix:** Switched all pages to use `rpt_route_sales_by_item_customer` (pre-aggregated, correct values) as primary source. For cash/credit breakdown that requires `rpt_sales_detail`, used `GROUP BY trx_code` to deduplicate

### 11. `discount_amount` Line-Level Duplication
- **Root cause:** `discount_amount` varies per detail line, `SELECT DISTINCT trx_code, discount_amount` doesn't collapse
- **Fix:** Used `SELECT DISTINCT trx_code, line_no, discount_amount` then SUM for discount totals

---

## PART 3: Formula / Logic Mismatches

### 12. Strike Rate Formula Wrong
- **Old:** `selling_calls / scheduled_calls * 100` (coverage metric, not strike rate)
- **MSSQL SP:** Groups by (route, date, customer), checks if `SUM(TotalAmount) > 100`, counts as strike
- **Additional sub-issue:** Even after fix, `net_amount` needed dedup by `trx_code` first
- **Fix:** Rewrote with `SELECT DISTINCT trx_code, net_amount` → GROUP BY route+date+customer → CASE WHEN total > 100

### 13. Coverage Call Metrics — Multiple Issues

#### 13a. Scheduled Calls Source
- **Was:** `rpt_coverage_summary.scheduled_calls`
- **Should be:** Depends on context — stored value or `COUNT(*) FROM rpt_journey_plan`

#### 13b. Unplanned Formula
- **Was:** `total_actual - actual_calls`
- **Should be:** `scheduled - actual_calls` (matching MSSQL `ScheduledCalls - ActualCalls`)

#### 13c. `is_planned` Column Unreliable
- `rpt_customer_visits.is_planned` always `false` (MSSQL `TypeOfCall` not populated)
- **Fix:** Planned detection via matching visits against `rpt_journey_plan` entries (same user+date+customer)

#### 13d. Productive Detection
- `is_productive` also unreliable
- **Fix:** Productive = visit has matching sale in `rpt_route_sales_by_item_customer` (same route+customer+date with `total_sales > 0`)

### 14. Brand Filter Mapped to Wrong Column
- **Was:** `brand` filter → `TRIM(category_code)`
- **Should be:** `brand` filter → `TRIM(brand_code)` (GroupLevel2)
- **Fix:** Updated `models.py`

### 15. Growth Percentage Uncapped
- Growth could exceed 1000% when previous period was very small
- **Fix:** Capped at `min(100.0, calculated_growth)` across all pages

### 16. Channel Filter Trailing Spaces
- `dim_customer.channel_code` has trailing spaces (`'02 '` not `'02'`)
- **Fix:** Used `TRIM(channel_code)` in all channel filter queries

### 17. Channel Filter Missing SalesOrg Join
- `rpt_route_sales_by_item_customer` has no `channel_code` — must resolve via `dim_customer` joined through `dim_route.sales_org_code`
- **Fix:** `EXISTS (SELECT 1 FROM dim_customer dc JOIN dim_route dr ON dr.sales_org_code = dc.sales_org_code WHERE dc.code = r.customer_code AND dr.code = r.route_code AND TRIM(dc.channel_code) IN (...))`

### 18. Sales Performance — Full Month Scope
- MSSQL SPs use `MONTH(Date)=M AND YEAR(Date)=Y` (full month), API was using exact `date_from/date_to`
- **Fix:** Added `month_start`/`month_end` for sales, returns, collection, SKU MTD to use full month

### 19. SKU Count Filter
- **Was:** `WHERE total_sales > 0` (excluded return-only items)
- **Should be:** `WHERE total_sales >= 0` (includes zero-sales items, matches MSSQL SP)
- Final: User requested `>= 0` specifically

### 20. SKU YTD End Date
- **Was:** Capped to `cur_end` (the selected date)
- **Should be:** Full year `date(cur_end.year, 12, 31)` (matches MSSQL `YEAR(Date)=Y`)

### 21. Sales Performance — `good_return`/`bad_return` Key Mismatch
- API returned `gr`/`damage`/`expiry` but UI expected `good_return`/`bad_return`
- **Fix:** Added both key sets to response

### 22. Endorsement — Sales Double-Counting on Repeat Visits
- Same customer visited multiple times → sales value repeated per visit row
- **Fix:** Track `seen_customers` set, only assign sales on first visit

---

## PART 4: Missing Features / Endpoints

### 23. Route Categories Filter
- Added `/filters/route-categories` and `/filters/routes-by-category`

### 24. Cities/Regions Filters
- Added `/filters/cities` and `/filters/regions`

### 25. Items Sold Endpoint
- Added `/api/items-sold?type=1|2|3|4` matching `sp_GetItemSold_Common` (4 modes)

### 26. LIMIT Clauses Removed
- Removed hardcoded LIMITs from: endorsement (500), top_products (20), top_customers (20), outstanding_collection (100/200), time_management (500)
- Kept: eot_status LIMIT 1 (single record lookup)

---

## PART 5: Performance Issues

### 27. Revenue Dispersion — 27s → 3.5s
- **Was:** Scanning `rpt_sales_detail` (11M rows) with GROUP BY per invoice
- **Fix:** Switched to `rpt_route_sales_by_item_customer` (pre-aggregated), 8x faster

### 28. Top Customers/Products Timeout
- **Was:** Joining current + previous month across 18M rows with `dim_customer`
- **Fix:** Single month query with LIMIT, removed previous period comparison from main query

### 29. EOT Status — Productive Detection Timeout
- **Was:** `EXISTS` subquery per visit row (11K visits)
- **Fix:** Pre-compute `productive_set` in Python (single query), O(1) lookup per visit

### 30. Salesman Journey — Correlated Subquery Timeout
- **Was:** Correlated subqueries per user for sales/SKU counts
- **Fix:** Pre-aggregate in subqueries, LEFT JOIN (0.8s for 321 users)

### 31. Missing Indexes
- Added: `idx_sd_trxcode`, `idx_sd_status_type_date`, `idx_cv_user_route_date`, `idx_jp_user_route_date`, `idx_rsic_date_cust_sales`

---

## PART 6: UI / Frontend Issues

### 32. Brand Wise Sales — Modal Not Working
- Drill-down was inline (hidden below table), not a proper modal
- **Fix:** Rewrote with modal dialog, search, pagination, Export Excel

### 33. Monthly Sales Stock — No Pagination
- All items rendered at once, slow for large datasets
- **Fix:** Added search, pagination (20/50/100/200), page size selector, Export Excel, internal scrollbar for 50+ rows

### 34. MTD Attendance — Missing Columns
- No route_code/route_name columns, no sorting, no search
- **Fix:** Added all columns, column sorting, search, pagination, color-coded attendance badges, Export

### 35. EOT Status — Flat Visit List
- Was a flat list of all visits, no user grouping
- **Fix:** User-first accordion design — click user to expand journey timeline with productive badges

### 36. Salesman Journey — Required User Selection
- Page was blank until user selected from filter
- **Fix:** Shows all salesmen with summary KPIs on first load, accordion expand for detail

### 37. Journey Plan Compliance — No Modal
- Drill-down was inline below the daily table
- **Fix:** View button per date, opens modal with search, pagination, Export

### 38. Working Days Calculation
- **Was:** Mon-Fri (5-day week)
- **Should be:** Mon-Sat (6-day week) minus holidays, matching MSSQL SP
- **Additional:** Attendance exceeding 100% fixed by excluding Sunday journeys from present count

---

## PART 7: MSSQL Date Boundary Issue (Systemic)

### 39. MSSQL `datetime` vs PostgreSQL `date` Comparison
- MSSQL: `TrxDate <= '2026-03-05'` treats as `<= 2026-03-05 00:00:00` (excludes Mar 5 transactions after midnight)
- PostgreSQL: `trx_date <= '2026-03-05'` includes all of Mar 5
- **Impact:** Per-day values match exactly, but date-range totals differ by 1 day
- **Resolution:** Accepted as systemic difference — PG behavior is actually more correct

---

## Final Validation Results (March 1, 2026)

| KPI | MSSQL | PG API | Match |
|-----|-------|--------|-------|
| Total Sales | 1,321,627 | 1,321,627 | YES |
| Total Collection | 945,723 | 945,723 | YES |
| Scheduled Calls | 8,427 | 8,427 | YES |
| Total Actual Calls | 6,961 | 6,961 | YES |
| Actual Calls (planned) | 5,083 | 5,083 | YES |
| Selling Calls | 6,098 | 6,098 | YES |
| Planned Selling Calls | 4,322 | 4,322 | YES |
| Unplanned | 3,344 | 3,344 | YES |
| Strike Rate | 59.32% | 59.32% | YES |
| Coverage % | 82.60% | 82.60% | YES |

## Pages Implemented / Fixed

| Page | Source Table | Status |
|------|-------------|--------|
| Dashboard | rpt_route_sales_summary_by_item + rpt_coverage_summary | Validated |
| Sales Performance | rpt_route_sales_by_item_customer | Validated |
| Daily Sales Overview | rpt_route_sales_by_item_customer + rpt_sales_detail | Validated |
| MTD Sales Overview | rpt_route_sales_by_item_customer + rpt_sales_detail | Validated |
| MTD Wastage | rpt_route_sales_by_item_customer | Validated |
| Weekly Sales & Returns | rpt_route_sales_by_item_customer | Validated |
| Brand Wise Sales | rpt_route_sales_by_item_customer + dim_item | Validated |
| Market Sales Performance | rpt_route_sales_by_item_customer (2025+2026) | Validated |
| Revenue Dispersion | rpt_route_sales_by_item_customer | Validated |
| Top Customers | rpt_route_sales_by_item_customer | Validated |
| Top Products | rpt_route_sales_by_item_customer + dim_item | Validated |
| Monthly Sales & Stock | rpt_route_sales_by_item_customer + dim_customer | Validated |
| Target vs Achievement | rpt_route_sales_by_item_customer + rpt_route_sales_summary_by_item | Fixed |
| MTD Attendance | rpt_journeys + rpt_holidays | Validated |
| Journey Plan Compliance | rpt_coverage_summary (fallback: raw tables) | Validated |
| EOT Status | rpt_customer_visits + rpt_route_sales_by_item_customer | Validated |
| Salesman Journey | rpt_customer_visits + rpt_route_sales_by_item_customer | Validated |
| Endorsement | rpt_customer_visits + rpt_journey_plan + rpt_route_sales_by_item_customer | Validated |
| Log Report | rpt_coverage_summary + rpt_route_sales_by_item_customer + rpt_collections | Validated |
| Time Management | rpt_journeys + rpt_customer_visits | Validated |
| Productivity & Coverage | rpt_coverage_summary | Working |
| Customer Attendance | rpt_customer_visits | Working |
| Items Sold | rpt_route_sales_by_item_customer | New |
| Outstanding Collection | rpt_outstanding | Working |
| Filters (all) | dim_user + dim_route + dim_customer + dim_item | Validated |
