# NFPC Reports - Complete Application Overview

## 1. What Is This Application?

NFPC Reports is an **enterprise sales reporting dashboard** for NFPC (National Food Products Company). It extracts data from a live MSSQL production database, loads it into a local PostgreSQL database via an ETL pipeline, and serves it through a FastAPI backend to a React frontend with 23 interactive report pages.

**Tech Stack:**
- **Frontend:** React 19 + Vite + Tailwind CSS + Recharts + Axios
- **Backend:** FastAPI (Python) + Uvicorn
- **Database:** PostgreSQL (reporting) ← ETL ← MSSQL (source, read-only)
- **Deployment:** Docker → Railway.app
- **Testing:** Playwright (E2E)

---

## 2. Architecture & Data Flow

```
┌──────────────────┐     ETL (extract.py)     ┌──────────────────┐
│   MSSQL Source    │ ──── READ-ONLY ────────► │   PostgreSQL     │
│  20.203.45.86     │   (chunked loads,        │  (reporting DB)  │
│  NFPCsfaV3_070326 │    15 tables)            │                  │
└──────────────────┘                           └────────┬─────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │   FastAPI API    │
                                               │   (21 routes)    │
                                               │   Port 8000      │
                                               │   5-min TTL cache│
                                               └────────┬─────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │  React Frontend  │
                                               │  (Vite, port 5173│
                                               │   in dev mode)   │
                                               │  23 report pages │
                                               └──────────────────┘
```

---

## 3. Project Structure

```
nfpc-reports-main/
├── api/                          # FastAPI backend
│   ├── main.py                   # App entry point, CORS, router includes, SPA serving
│   ├── database.py               # PostgreSQL connection pool + TTL query cache
│   ├── models.py                 # Pydantic models, WHERE clause builder, user hierarchy resolver
│   ├── warmup.py                 # Background cache warmup on startup (22 endpoints)
│   └── routes/                   # 21 route modules (one per report + filters)
│       ├── filters.py            # 10 dropdown endpoints (sales orgs, routes, users, etc.)
│       ├── dashboard.py          # Executive dashboard
│       ├── sales_performance.py  # Monthly SKU + ROS analysis
│       ├── productivity_coverage.py
│       ├── salesman_journey.py   # GPS journey trace
│       ├── time_management.py    # Working hours analysis
│       ├── top_customers.py      # Top 20 customers
│       ├── top_products.py       # Top 20 products
│       ├── daily_sales_overview.py
│       ├── market_sales.py       # YoY monthly comparison
│       ├── brand_wise_sales.py   # Brand performance + item drill-down
│       ├── monthly_sales_stock.py # Item sales by channel
│       ├── eot_status.py         # End-of-trip compliance
│       ├── mtd_attendance.py     # Salesman attendance
│       ├── mtd_sales_overview.py # Daily sales vs target
│       ├── mtd_wastage.py        # Returns/wastage analysis
│       ├── outstanding_collection.py # AR aging analysis
│       ├── revenue_dispersion.py # Invoice & SKU distribution
│       ├── journey_plan_compliance.py
│       ├── target_achievement.py # Route-level target vs actual
│       ├── endorsement.py        # Route journey with visit metrics
│       ├── weekly_sales_returns.py
│       ├── customer_attendance.py
│       └── log_report.py         # Transaction activity log
├── frontend/                     # React SPA
│   ├── package.json              # React 19, Recharts, Axios, Lucide, Tailwind
│   ├── vite.config.js            # Dev server port 5173, API proxy → localhost:8000
│   ├── index.html
│   └── src/
│       ├── main.jsx              # React bootstrap with BrowserRouter
│       ├── App.jsx               # Layout (Sidebar + Routes) with 23 route definitions
│       ├── api.js                # Axios client, 21 report fetchers + 10 filter fetchers
│       ├── components/
│       │   ├── Sidebar.jsx       # Navigation (6 sections, dark theme, Lucide icons)
│       │   ├── FilterPanel.jsx   # Dynamic multi-field filter panel with MultiSelect
│       │   ├── DataTable.jsx     # Sortable, searchable table with CSV export
│       │   ├── KpiCard.jsx       # Reusable metric card (7 color variants)
│       │   └── Loading.jsx       # Spinner + skeleton placeholders
│       └── pages/                # 23 report page components (one per report)
├── etl/                          # ETL pipeline
│   ├── extract.py                # MSSQL → PostgreSQL loader (chunked, 15 tables)
│   ├── audit.py                  # Source vs target data validation (HTML report)
│   └── test_etl.py               # Quick 1000-row validation test
├── tests/
│   └── filter-test.spec.js       # Playwright E2E tests (4 phases, 22 reports)
├── docs/sprocs/SP_Definitions/   # 50+ stored procedure definitions (reference)
├── export_30days.sh              # Export last 30 days to CSV for Railway import
├── import_railway.sh             # Import CSVs into Railway PostgreSQL
├── Dockerfile                    # Python 3.12-slim, port 8000
├── railway.toml                  # Railway deployment config with health check
├── requirements.txt              # fastapi, uvicorn, psycopg2-binary, python-dotenv
└── CLAUDE.md                     # AI assistant rules (READ-ONLY source DB)
```

---

## 4. Database Schema

### Dimension Tables (reference data)
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `dim_sales_org` | Sales organizations | code, name, is_active |
| `dim_route` | Sales routes | code, name, sales_org_code, is_active |
| `dim_user` | Salesmen/users | code, name, sales_org_code, depot, reports_to, is_active |
| `dim_customer` | Customers | code, name, sales_org_code, channel, is_active |
| `dim_item` | Products/SKUs | code, name, category_code (brand), is_active |
| `dim_channel` | Sales channels | code, name |

### Fact Tables (transactional data)
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `rpt_sales_detail` | All sales transactions (~12M rows) | trx_type (1=sale, 3=credit note, 4=return), date, amount, qty, item_code, customer_code, user_code |
| `rpt_collections` | Payment collections | date, amount, customer_code, user_code |
| `rpt_targets` | Sales targets | start_date, target_amount, route_code, item_key |
| `rpt_coverage_summary` | Call coverage metrics | date, user_code, scheduled, actual, planned, unplanned, productive |
| `rpt_customer_visits` | Individual customer visits | date, user_code, customer_code, arrival_time, out_time, latitude, longitude, is_planned |
| `rpt_journeys` | Daily journey records | date, user_code, start_time, end_time |
| `rpt_journey_plan` | Planned journey routes | date, user_code, customer_code |
| `rpt_outstanding` | Accounts receivable | customer_code, invoice, balance_amount, aging_bucket |
| `rpt_eot` | End-of-trip records | date, user_code, start_time, end_time |
| `rpt_route_sales_collection` | Route-level aggregates | date, route_code, sales_amount, collection_amount |
| `rpt_holidays` | Holiday calendar | date |

---

## 5. Backend Implementation Details

### 5.1 Application Entry Point (`api/main.py`)
- FastAPI app with **lifespan** context manager triggering background cache warmup
- **CORS** enabled for all origins
- Includes 21 report routers under `/api` prefix
- Serves the React SPA from `frontend/dist` (catch-all route)
- Health check: `GET /api/health`

### 5.2 Database Layer (`api/database.py`)
- **Connection Pool:** `psycopg2.pool.ThreadedConnectionPool` (2–10 connections)
- **Query Cache:** In-memory with 5-minute TTL, max 500 entries, LRU eviction
- **Functions:**
  - `get_db()` — context manager for connection checkout/return
  - `query(sql, params)` — cached SELECT returning `list[dict]`
  - `query_one(sql, params)` — cached SELECT returning single `dict` or `None`
  - `cache_clear()` — manual cache invalidation
- **Config:** Reads `DATABASE_URL` or individual `PG_*` env vars

### 5.3 Shared Models & Filters (`api/models.py`)
- `StandardFilters` Pydantic model: date_from, date_to, sales_org, route, user_code, channel, customer, brand, category, item
- `build_where(filters, date_col, prefix)` — builds parameterized WHERE clauses; supports comma-separated multi-values → SQL `IN` clauses
- `resolve_user_codes(filters)` — resolves depot/supervisor hierarchy to user_code lists via `dim_user` joins

### 5.4 Cache Warmup (`api/warmup.py`)
- Runs in a background daemon thread on startup
- Pre-warms 22 endpoint functions with default date ranges (MTD/YTD)
- Failures logged as warnings but don't block startup

### 5.5 API Endpoints Summary

#### Filter Endpoints (`/api/filters/...`)
| Endpoint | Returns |
|----------|---------|
| `GET /filters/sales-orgs` | Active sales organizations |
| `GET /filters/routes` | Active routes (filterable by sales_org) |
| `GET /filters/users` | Active salesmen (filterable by sales_org) |
| `GET /filters/customers` | Active customers (filterable by sales_org) |
| `GET /filters/items` | Active products |
| `GET /filters/brands` | Distinct commercial brands (category_code) |
| `GET /filters/channels` | Sales channels |
| `GET /filters/categories` | Product categories |
| `GET /filters/depots` | Depots (filterable by sales_org) |
| `GET /filters/supervisors` | Supervisor hierarchy |

#### Report Endpoints (`/api/...`)
| Endpoint | Purpose | Key Tables |
|----------|---------|------------|
| `GET /dashboard` | Executive KPI summary with trends | rpt_sales_detail, rpt_collections, rpt_targets, rpt_coverage_summary, rpt_customer_visits, rpt_journey_plan |
| `GET /sales-performance` | Monthly SKU analysis & ROS | rpt_sales_detail, rpt_targets |
| `GET /productivity-coverage` | Salesman call coverage | rpt_coverage_summary |
| `GET /salesman-journey` | GPS journey trace with timeline | rpt_customer_visits |
| `GET /time-management` | Working hours analysis | rpt_journeys, rpt_eot, rpt_customer_visits |
| `GET /top-customers` | Top 20 customers with growth | rpt_sales_detail |
| `GET /top-products` | Top 20 products with growth | rpt_sales_detail |
| `GET /daily-sales-overview` | Daily sales + brand performance | rpt_sales_detail, rpt_coverage_summary, rpt_targets |
| `GET /market-sales-performance` | Year-over-year monthly comparison | rpt_sales_detail |
| `GET /brand-wise-sales` | Brand performance + item drill-down | rpt_sales_detail, rpt_targets |
| `GET /brand-wise-sales/items` | Item-level drill-down for a brand | rpt_sales_detail, rpt_targets |
| `GET /monthly-sales-stock` | Item sales pivoted by channel | rpt_sales_detail |
| `GET /eot-status` | End-of-trip compliance & KPIs | rpt_journeys, rpt_journey_plan, rpt_sales_detail, rpt_collections, rpt_coverage_summary, rpt_customer_visits |
| `GET /mtd-attendance` | Attendance tracking | rpt_journeys, rpt_holidays |
| `GET /mtd-sales-overview` | Daily sales vs target tracking | rpt_customer_visits, rpt_sales_detail, rpt_targets |
| `GET /mtd-wastage-summary` | Returns/wastage analysis | rpt_sales_detail |
| `GET /outstanding-collection` | AR aging buckets | rpt_outstanding |
| `GET /outstanding-collection/invoices` | Invoice-level detail | rpt_outstanding |
| `GET /revenue-dispersion` | Invoice & SKU distribution | rpt_sales_detail |
| `GET /journey-plan-compliance` | Journey plan adherence | rpt_coverage_summary |
| `GET /target-vs-achievement` | Route-level target vs actual | rpt_targets, rpt_route_sales_collection |
| `GET /endorsement` | Route journey with visit metrics | rpt_customer_visits, rpt_sales_detail |
| `GET /weekly-sales-returns` | Weekly sales vs returns | rpt_sales_detail |
| `GET /customer-attendance` | Customer visit log | rpt_customer_visits |
| `GET /log-report` | Transaction activity log | rpt_coverage_summary, rpt_sales_detail, rpt_collections |

---

## 6. Frontend Implementation Details

### 6.1 Technology Choices
- **React 19** with functional components and hooks (useState, useEffect)
- **React Router DOM 7** for client-side routing (23 routes)
- **Tailwind CSS 4** for styling (utility-first, responsive grids)
- **Recharts** for charts (Bar, Line, Pie, ComposedChart)
- **Axios** for API calls (proxied via Vite in dev, same-origin in prod)
- **Lucide React** for icons

### 6.2 Layout & Navigation
- Two-column layout: **Sidebar** (fixed left, dark slate) + **Main content** (scrollable)
- Sidebar organized into 6 sections with 23 navigation items:
  1. **Overview:** Dashboard
  2. **Sales (8):** Daily Sales Overview, MTD Sales Overview, Market Sales, Brand Wise Sales, Monthly Sales & Stock, Weekly Sales & Returns, Revenue Dispersion, Sales Performance
  3. **Customers & Products (4):** Top Customers, Top Products, Outstanding Collection, Customer Attendance
  4. **Targets & Productivity (4):** Target vs Achievement, Productivity & Coverage, Journey Plan Compliance, Endorsement
  5. **Attendance & Routes (4):** MTD Attendance, EOT Status, Salesman Journey, Time Management
  6. **Logs & Time (2):** Log Report, MTD Wastage

### 6.3 Shared Components

**FilterPanel** — Dynamic filter form with:
- Date range pickers (date_from, date_to)
- MultiSelect dropdowns for: Sales Org, Depot, Route, Salesman, Channel, Brand, Category, Supervisor
- Month/Year selectors
- Dependent loading (routes and users filter by selected sales_org)
- Responsive grid (1–8 columns based on field count)

**DataTable** — Feature-rich table:
- Client-side search across all columns
- Click-to-sort (ascending/descending)
- Row count display
- CSV export with formatted values
- Number formatting (AED currency, percentages)
- Alternating row colors with hover

**KpiCard** — Metric display card:
- Title, value, subtitle, icon
- 7 color variants (blue, green, red, yellow, purple, indigo, teal)
- Solid and light style variants

**Loading** — Spinner with skeleton pulse animations

### 6.4 Report Pages (23 pages)

Each page follows a consistent pattern:
1. **FilterPanel** at top with relevant filters
2. **KPI cards** row showing summary metrics
3. **Charts/Visualizations** (bar charts, line charts, gauges, combo charts)
4. **DataTable** with detailed records

| Page | Key Visualizations | Notable Features |
|------|--------------------|------------------|
| Dashboard | Bar charts (daily/weekly sales & collection), horizontal bar (route breakdown) | Most complex page; depot/supervisor hierarchy filtering |
| Sales Performance | Custom pie-based gauges (achievement %), ROS card | Color-coded ROS thresholds (green ≤2%, yellow ≤5%, red >5%) |
| Top Customers | Horizontal bar chart with 20-shade gradient | Toggle between AED and Units view |
| Top Products | Horizontal bar chart with gradient colors | Growth % labels on bars |
| Market Sales | Combo chart (bars + growth line) | YoY comparison, sticky month column |
| Brand Wise Sales | Summary + table | Drill-down modal for item details |
| Outstanding Collection | Color-coded aging bucket cards | Clickable rows → invoice detail modal |
| Revenue Dispersion | Pivot table (ranges × months) | Tab toggle (Revenue vs SKU) |
| Target Achievement | Bar chart + list toggle | Color-coded achievement badges |
| Salesman Journey | Numbered timeline with coordinates | GPS lat/long display |
| EOT Status | Journey stops list | Route compliance badges |
| MTD Attendance | Color-coded attendance table | Green ≥90%, Amber 75-90%, Red <75% |
| Monthly Sales & Stock | Dynamic channel columns pivot | Multi-row headers (MTD/YTD sub-columns) |

### 6.5 Color Scheme
- **Primary:** Indigo (#4f46e5, #6366f1)
- **Success:** Emerald/Green
- **Warning:** Amber/Yellow
- **Danger:** Rose/Red
- **Background:** Light gray (#f0f2f5)
- **Sidebar:** Dark slate with indigo gradient header

---

## 7. ETL Pipeline

### 7.1 Extraction (`etl/extract.py`)
- Connects to **MSSQL** source (read-only) at `20.203.45.86`
- Loads **15 tables** (7 dimensions + 8 fact tables)
- **Chunked processing** to prevent MSSQL tempdb overflow:
  - `rpt_sales_detail`: 2-week chunks (~12M rows total)
  - Summary tables: monthly chunks
- Configurable date range (default: 2025-10-01 to 2026-03-31)
- CLI arguments: `--table` (single table), `--dry-run`, `--from`/`--to` (date range)
- Progress tracking via JSON status file + detailed logging

### 7.2 Audit (`etl/audit.py`)
- Compares MSSQL source vs PostgreSQL target across 9 check categories:
  1. Row counts
  2. Monthly sales totals
  3. Distinct value counts
  4. NULL checks
  5. Date ranges
  6. Collections
  7. Coverage
  8. Spot samples (random transaction verification)
  9. Table sizes
- Generates color-coded HTML report (`etl/logs/audit_report.html`)
- Variance thresholds: 0.1% pass, 5% warning, >5% fail

### 7.3 Test ETL (`etl/test_etl.py`)
- Quick validation: loads all dimensions + 1000-row samples of fact tables
- Verifies schema compatibility and data transformations before full load

---

## 8. Deployment

### 8.1 Docker
```dockerfile
FROM python:3.12-slim
# Installs requirements, copies API code + pre-built frontend
# Exposes port 8000 (configurable via PORT env var)
# Runs: uvicorn api.main:app
```

### 8.2 Railway.app
- Configured via `railway.toml`
- Health check: `GET /api/health` (60s timeout)
- Restart policy: ON_FAILURE (max 3 retries)
- Production URL: `https://nfpc-app-production.up.railway.app`

### 8.3 Data Migration Scripts
- `export_30days.sh` — exports last 30 days of PostgreSQL data to CSV files in `/tmp/nfpc_export/`
- `import_railway.sh` — imports those CSVs into Railway's PostgreSQL instance

### 8.4 Environment Variables
| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (or use individual PG_* vars) |
| `PG_HOST` | PostgreSQL host |
| `PG_PORT` | PostgreSQL port |
| `PG_DATABASE` | PostgreSQL database name |
| `PG_USER` | PostgreSQL username |
| `PG_PASSWORD` | PostgreSQL password |
| `PORT` | Server port (default 8000) |

---

## 9. Testing

### Playwright E2E Tests (`tests/filter-test.spec.js`)
Four-phase test strategy covering all 22 reporting APIs:
1. **Phase 1:** API filter combinations across all reports
2. **Phase 2:** Cross-filter consistency (sum of orgs = total, subsets, date logic)
3. **Phase 3:** UI vs API data comparison (numbers match, filter changes work, pages load)
4. **Phase 4:** Filter dropdown population tests

Configuration: Chromium only, 60s timeout, 1 retry, screenshots on failure.

---

## 10. Key Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **Parameterized SQL** | All queries use `%s` placeholders — no SQL injection risk |
| **Query caching** | 5-min TTL, 500-entry LRU cache in `database.py` |
| **Cache warmup** | Background thread pre-populates cache for 22 endpoints at startup |
| **Multi-value filters** | Comma-separated values → SQL `IN` clauses |
| **Hierarchy resolution** | Depot/supervisor → user_codes via `dim_user` joins |
| **Chunked ETL** | Prevents MSSQL tempdb overflow on large tables |
| **SPA serving** | FastAPI serves pre-built React from `frontend/dist` |
| **Responsive UI** | Tailwind CSS responsive grids (1/2/3/4/5/8 columns) |
| **CSV export** | Client-side export from DataTable component |
| **Color-coded thresholds** | Achievement %, attendance %, wastage % — visual indicators |

---

## 11. Transaction Type Reference

The `rpt_sales_detail.trx_type` field drives most report logic:

| trx_type | Meaning | Used In |
|----------|---------|---------|
| 1 | **Sales** (invoices) | All sales reports, top customers/products, brand analysis |
| 3 | **Credit Notes** | Log report (credit_amount) |
| 4 | **Returns** (wastage) | ROS calculation, wastage analysis, weekly returns |
