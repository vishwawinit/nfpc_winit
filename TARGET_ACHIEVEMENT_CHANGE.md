# Target Achievement API — Before & After Change

## What Was The Problem

`rpt_route_sales_summary_by_item` (the source table for target/achievement data) stores data
**per route** — its `user_code` column is `NULL` for every row. So when the API received
`user_code=102607` (a salesman's locked filter), it passed it into `build_where` which generated
`WHERE user_code = '102607'` — matching nothing, returning empty.

---

## BEFORE (broken for salesman/user_code filter)

```python
RSSI_KEYS = {'date_from', 'date_to', 'sales_org', 'route', 'user_code'}  # user_code included
RSIC_KEYS = {'date_from', 'date_to', 'route', 'user_code'}               # user_code included

# No user_code → route mapping. user_code passed directly into build_where.
base_filters = {k: v for k, v in {
    'route': route,
    'user_code': user_code,   # <-- passed straight to SQL WHERE
}.items() if v}
```

**SQL generated (for user_code=102607):**
```sql
SELECT r.route_code, ...
FROM rpt_route_sales_summary_by_item r
WHERE r.date >= '2026-03-01'
  AND r.date <= '2026-03-31'
  AND r.user_code = '102607'   -- user_code is NULL for all rows → 0 results
GROUP BY r.route_code, ...
```

**Result:** `{ "total_target": 0, "total_achieved": 0, "route_data": [] }`  
Even though salesman 102607 had AED 73,810.36 in sales for March 2026.

---

## AFTER (fixed)

```python
RSSI_KEYS = {'date_from', 'date_to', 'sales_org', 'route'}  # user_code removed
RSIC_KEYS = {'date_from', 'date_to', 'route'}               # user_code removed

# Resolve user_code → route via dim_route.salesman_code BEFORE querying
if user_code and user_code != "__NO_MATCH__":
    codes = [c.strip() for c in user_code.split(',') if c.strip()]
    ph = ','.join(['%s'] * len(codes))
    mapped = query(f"SELECT code FROM dim_route WHERE salesman_code IN ({ph})", codes)
    mapped_routes = [r['code'] for r in mapped]
    if not mapped_routes:
        return _empty()
    if route:
        existing = set(route.split(','))
        mapped_routes = [r for r in mapped_routes if r in existing]
        if not mapped_routes:
            return _empty()
    route = ','.join(mapped_routes)   # e.g. 'E12'
    user_code = None                  # cleared — route filter used instead

base_filters = {k: v for k, v in {
    'route': route,   # only route, no user_code
}.items() if v}
```

**Lookup query run first:**
```sql
SELECT code FROM dim_route WHERE salesman_code IN ('102607')
-- Returns: [{ code: 'E12' }]
```

**Main SQL generated (for user_code=102607 → route=E12):**
```sql
SELECT r.route_code, COALESCE(dr.name, r.route_code) AS route_name,
       ROUND(COALESCE(SUM(r.total_sales), 0)::numeric, 2)    AS achieved,
       ROUND(COALESCE(SUM(r.target_amount), 0)::numeric, 2)  AS target
FROM rpt_route_sales_summary_by_item r
LEFT JOIN dim_route dr ON r.route_code = dr.code
WHERE r.date >= '2026-03-01'
  AND r.date <= '2026-03-31'
  AND r.route_code = 'E12'   -- route filter instead of user_code
GROUP BY r.route_code, COALESCE(dr.name, r.route_code)
ORDER BY achieved DESC
```

**Result:**
```json
{
  "total_target": 0.0,
  "total_achieved": 73810.36,
  "achieved_pct": 0,
  "route_data": [
    {
      "route_code": "E12",
      "route_name": "E12-MTFRSH-DXB",
      "target": 0.0,
      "achieved": 73810.36,
      "achieved_pct": 0
    }
  ]
}
```

---

## Why target = 0?

`target_amount` in `rpt_route_sales_summary_by_item` is `0.00` for route E12 in March 2026.
This is a **source data issue** — the MSSQL replication did not populate target amounts for
this route/period. The achievement figure (73,810.36) is correct; target data needs to be
loaded in the source system.

---

## Summary

| | Before | After |
|---|---|---|
| Filter method | `WHERE user_code = '102607'` on a NULL column | Lookup `dim_route.salesman_code → route`, then `WHERE route_code = 'E12'` |
| Result for salesman 102607, Mar 2026 | `achieved=0` (wrong) | `achieved=73810.36` (correct) |
| Extra query | None | 1 lightweight lookup: `SELECT code FROM dim_route WHERE salesman_code IN (...)` |
| Affects | Salesman & any user_code-based filter on target page | Fixed for all user_code filters |
