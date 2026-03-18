# NFPC Reports - Backend Changes

## Bug Fixes (2026-03-16)

### 1. `daily_sales_overview.py` - Payment Type Mismatch
- **File:** `api/routes/daily_sales_overview.py`
- **Issue:** `payment_type = 1` failed because `payment_type` column is `VARCHAR` in the database but was compared as `INTEGER`.
- **Error:** `operator does not exist: character varying = integer`
- **Fix:** Changed `payment_type = 1` to `payment_type::text = '1'` and `payment_type = 0` to `payment_type::text = '0'`

### 2. `mtd_sales_overview.py` - Payment Type Mismatch
- **File:** `api/routes/mtd_sales_overview.py`
- **Issue:** Same `payment_type` type mismatch as above in the daily sales query.
- **Error:** `operator does not exist: character varying = integer`
- **Fix:** Changed `payment_type = 1` to `payment_type::text = '1'` and `payment_type = 0` to `payment_type::text = '0'`

### 3. `time_management.py` - Timestamp Column Handling
- **File:** `api/routes/time_management.py`
- **Issue:** `start_time` and `end_time` are `TIMESTAMP` columns in the database, but the code treated them as `VARCHAR` — comparing with `!= ''` (empty string) and parsing with `TO_TIMESTAMP()`.
- **Error:** `invalid input syntax for type timestamp: ""`
- **Fix:** Removed string comparisons (`!= ''`) and `TO_TIMESTAMP()` parsing. Now uses direct timestamp arithmetic: `EXTRACT(EPOCH FROM (j.end_time - j.start_time))` with `IS NOT NULL` checks.

### 4. `eot_status.py` - Visit Status Mismatch
- **File:** `api/routes/eot_status.py`
- **Issue:** `visit_status = 1` failed because `visit_status` column is `VARCHAR` but was compared as `INTEGER`.
- **Error:** `operator does not exist: character varying = integer`
- **Fix:** Changed `visit_status = 1` to `visit_status::text = '1'`
