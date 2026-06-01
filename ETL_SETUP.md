# NFPC Reports — Production Setup Guide

## Architecture

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│        ETL SERVER            │        │        APP SERVER            │
│                              │        │                              │
│  Source: MSSQL (READ-ONLY)   │        │  api/        (FastAPI)       │
│  etl/extract.py              │──────> │  frontend/dist/ (React SPA)  │
│  MSSQL --> PostgreSQL        │  Shared│                              │
│                              │   DB   │  URL: http://<server>:8000   │
└──────────────────────────────┘        └──────────────────────────────┘
                                               |
                                   ┌───────────────────────┐
                                   │   PostgreSQL (Shared) │
                                   │   Railway / self-host │
                                   └───────────────────────┘
```

- **ETL Server** — pulls data from MSSQL, writes to PostgreSQL. Runs `etl/extract.py`.
- **App Server** — serves the React frontend + FastAPI backend. Reads from PostgreSQL only.
- **PostgreSQL** — shared reporting database. Both servers connect to it.

---

## Part 1 — ETL Server Setup

### 1.1 Requirements

- Python 3.12+
- Network access to MSSQL at `20.203.45.86`
- Network access to the shared PostgreSQL DB

### 1.2 Install Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` includes: `fastapi`, `uvicorn`, `psycopg2-binary`, `python-dotenv`, `pymssql`

### 1.3 Configure Environment

Create `.env` in the project root:

```env
# MSSQL Source — READ-ONLY (Live Production)
DB_SERVER=20.203.45.86
DB_USER=nfpc
DB_PASSWORD=nfpc@!23
DB_NAME=NFPCsfaV3_070326

# PostgreSQL Target (Shared Reporting DB)
PG_HOST=switchback.proxy.rlwy.net
PG_PORT=31910
PG_DATABASE=railway
PG_USER=postgres
PG_PASSWORD=<pg_password>
```

> **CRITICAL:** MSSQL is a live production database. Only `SELECT` is permitted.
> Never run INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE against it.

---

### 1.4 ETL Commands

#### First-Time Full Load

Loads all 20 tables from the beginning of the year to today.
Tables are auto-created if they don't exist.

```bash
python etl/extract.py
```

#### Incremental Sync — Last N Days (Recommended for Daily Use)

`--days N` = today + previous (N−1) days. Always uses upsert — never deletes existing data.

```bash
python etl/extract.py --days 2    # yesterday + today
python etl/extract.py --days 7    # last 7 days  (6 prev + today)
python etl/extract.py --days 30   # last 30 days (29 prev + today)
```

#### Custom Date Range

```bash
python etl/extract.py --from-date 2026-01-01 --to-date 2026-05-20
```

#### Custom Date Range with Upsert (No Delete)

```bash
python etl/extract.py --from-date 2026-05-01 --to-date 2026-05-20 --upsert
```

#### Single Table Only

```bash
python etl/extract.py --table sales_detail
python etl/extract.py --table collections
python etl/extract.py --table dimensions
```

Available table names:

| Category | Names |
|---|---|
| Dimensions | `dimensions`, `holidays`, `targets` |
| Coverage | `coverage_summary`, `route_sales_collection` |
| Sales | `route_sales_summary_by_item`, `route_sales_by_item_customer`, `invoice_totals`, `sales_detail` |
| Visits | `customer_visits`, `journey_plan`, `journeys`, `eot` |
| Finance | `collections`, `outstanding` |

#### Dry Run (Preview Without Executing)

```bash
python etl/extract.py --dry-run
python etl/extract.py --days 7 --dry-run
```

#### Parallel Loading (Faster)

Dimensions load sequentially first, then fact tables load in parallel.

```bash
python etl/extract.py --parallel --workers 4
```

---

### 1.5 Daily Incremental Sync Script

Use `sync.sh` / `sync.bat` for automated daily sync:

```bash
# Linux / Mac / WSL
bash sync.sh        # syncs yesterday + today (default)
bash sync.sh 7      # syncs last 7 days
bash sync.sh 30     # syncs last 30 days

# Windows
sync.bat            # syncs yesterday + today
```

**Schedule with cron (Linux):**

```bash
# Run every day at 2:00 AM
0 2 * * * cd /path/to/nfpc_winit && bash sync.sh >> etl/logs/cron.log 2>&1
```

**Schedule with Task Scheduler (Windows):**

- Program: `python`
- Arguments: `etl\extract.py --days 2`
- Start in: `C:\path\to\nfpc_winit`
- Trigger: Daily at 02:00 AM

---

### 1.6 ETL Sync Behaviour

| Table Type | Full Load | Incremental (`--days`) |
|---|---|---|
| Dimension tables (6) | Full DELETE + reload | Full DELETE + reload (always) |
| Source-PK fact tables (9) | DELETE date window + insert | Upsert — `ON CONFLICT DO UPDATE` |
| Aggregate tables (3) | DELETE date window + insert | DELETE date window + reinsert |
| Targets / Holidays | Upsert | Upsert |

Source-PK tables (true upsert — existing rows updated, new rows inserted, nothing deleted):

| Table | Conflict Key |
|---|---|
| `rpt_sales_detail` | `(trx_code, line_no)` |
| `rpt_collections` | `receipt_id` |
| `rpt_customer_visits` | `visit_id` |
| `rpt_journeys` | `journey_id` |
| `rpt_coverage_summary` | `id` |
| `rpt_route_sales_collection` | `id` |
| `rpt_outstanding` | `id` |
| `rpt_eot` | `eot_id` |
| `rpt_journey_plan` | `id` |

---

### 1.7 ETL Logs

| Path | Description |
|---|---|
| `etl/logs/etl_YYYYMMDD_HHMMSS.log` | Full execution log |
| `etl/logs/etl_status.json` | Live status (rows loaded, ETA, current step) |
| `etl/logs/cron.log` | Scheduled sync output |

---

### 1.8 Re-run Failed Tables

If specific tables fail, re-run them individually without re-running everything:

```bash
python etl/extract.py --table dimensions
python etl/extract.py --table sales_detail
python etl/extract.py --table collections
```

---

## Part 2 — Application Server Setup

### 2.1 Requirements

- Python 3.12+
- No Node.js required (frontend is pre-built)
- Network access to the shared PostgreSQL DB
- No MSSQL access needed

### 2.2 Get the Package

Build the application package on the dev machine:

```bash
bash build-standalone.sh
```

This creates `nfpc-reports.zip` (frontend + backend, no ETL).
Copy this zip to the application server.

### 2.3 Install Dependencies

```bash
# Unzip on the server
unzip nfpc-reports.zip -d nfpc-reports
cd nfpc-reports

# Install Python dependencies (app only — no pymssql)
pip install -r requirements.txt
```

`requirements.txt` includes: `fastapi`, `uvicorn[standard]`, `psycopg2-binary`, `python-dotenv`

### 2.4 Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — only PostgreSQL credentials needed:

```env
# PostgreSQL Shared Reporting DB
PG_HOST=switchback.proxy.rlwy.net
PG_PORT=31910
PG_DATABASE=railway
PG_USER=postgres
PG_PASSWORD=<pg_password>

# Optional
GOOGLE_MAPS_API_KEY=
```

### 2.5 Start the Application

```bash
# Linux / Mac
./start.sh

# Windows
start.bat

# Custom port
PORT=9000 ./start.sh
```

Open browser: **http://localhost:8000**

### 2.6 Docker (Alternative)

```bash
docker build -t nfpc-reports .
docker run -p 8000:8000 --env-file .env nfpc-reports
```

### 2.7 Run as a Service (Linux)

Create `/etc/systemd/system/nfpc-reports.service`:

```ini
[Unit]
Description=NFPC Reports Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/nfpc-reports
ExecStart=/usr/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/home/ubuntu/nfpc-reports/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable nfpc-reports
sudo systemctl start nfpc-reports
sudo systemctl status nfpc-reports
```

---

## Part 3 — Production Checklist

### First-Time Setup

```
ETL SERVER
[ ] pip install -r requirements.txt
[ ] Create .env with MSSQL + PostgreSQL credentials
[ ] python etl/extract.py --dry-run        (verify connections)
[ ] python etl/extract.py                  (full initial load)
[ ] Verify row counts in PostgreSQL

APP SERVER
[ ] Unzip nfpc-reports.zip
[ ] pip install -r requirements.txt
[ ] Create .env with PostgreSQL credentials only
[ ] ./start.sh
[ ] Open http://<server>:8000
[ ] Login with a valid user code
[ ] Verify all report pages load correctly
```

### Daily Operations

```
ETL SERVER (runs automatically via cron/Task Scheduler)
[ ] bash sync.sh                            (daily incremental sync)
[ ] Check etl/logs/etl_status.json for errors

APP SERVER (always running)
[ ] Verify http://<server>:8000/api/health returns {"status":"ok"}
```

---

## Part 4 — API Reference

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/auth/login?userCode=XXX` | Login by user code |
| `POST /api/cache/clear` | Clear query cache |
| `GET /api/dashboard` | Executive KPI summary |
| `GET /api/sales-performance` | SKU analysis |
| `GET /api/top-customers` | Top 20 customers |
| `GET /api/top-products` | Top 20 products |
| `GET /api/outstanding-collection` | AR aging |
| `GET /api/eot-status` | End-of-trip status |
| `GET /api/filters/*` | Filter dropdown data |

Full API docs: **http://localhost:8000/docs**

---

## Part 5 — Table Reference (20 API Tables)

| Table | Type | Sync Strategy | Approx Rows |
|---|---|---|---|
| `dim_sales_org` | Dimension | Full reload | 28 |
| `dim_route` | Dimension | Full reload | 470 |
| `dim_user` | Dimension | Full reload | 1,133 |
| `dim_customer` | Dimension | Full reload | 119,482 |
| `dim_item` | Dimension | Full reload | 4,962 |
| `dim_channel` | Dimension | Full reload | 15 |
| `rpt_sales_detail` | Fact | Upsert `(trx_code, line_no)` | ~7M |
| `rpt_collections` | Fact | Upsert `receipt_id` | ~741K |
| `rpt_customer_visits` | Fact | Upsert `visit_id` | ~799K |
| `rpt_journeys` | Fact | Upsert `journey_id` | ~19K |
| `rpt_coverage_summary` | Fact | Upsert `id` | ~18K |
| `rpt_route_sales_collection` | Summary | Upsert `id` | ~18K |
| `rpt_outstanding` | Fact | Upsert `id` | ~2.1M |
| `rpt_eot` | Fact | Upsert `eot_id` | ~48K |
| `rpt_journey_plan` | Fact | Upsert `id` | ~890K |
| `rpt_route_sales_summary_by_item` | Aggregate | Delete window + reinsert | ~919K |
| `rpt_route_sales_by_item_customer` | Aggregate | Delete window + reinsert | ~4.5M |
| `rpt_invoice_totals` | Aggregate | Delete window + reinsert | ~558K |
| `rpt_targets` | Reference | Upsert `target_id` | 162 |
| `rpt_holidays` | Reference | Upsert `holiday_id` | 58 |
