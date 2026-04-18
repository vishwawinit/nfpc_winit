# MSSQL Summary Table Population — Stored Procedures

## Tables & Their Population SPs

| Table | SP that writes to it |
|---|---|
| `tblRouteSalesSummaryByItemCustomer` | `RouteSalesSummaryByIC_Insert` |
| `tblRouteSalesSummaryByItem` | `usp_Populate_tblRouteSalesSummary_DataByItem` |

> **Note:** `usp_insert_RouteSalesSummaryByItemCustomer` also targets `tblRouteSalesSummaryByItemCustomer` but is **dead** — has `RETURN` at line 3 so it never executes.

---

## tblRouteSalesSummaryByItemCustomer (RSIC)

**Populated by:** `RouteSalesSummaryByIC_Insert`

**Source tables:** `tblTrxHeader` JOIN `tblTrxDetail` WHERE `TRXStatus = 200`

**Sales formula:**
```sql
SUM(
  CASE WHEN TrxType = 4 THEN -1 ELSE 1 END
  * ABS((QuantityLevel1 * PriceUsedLevel1) - TotalDiscountAmount + ExciseDutyTaxAmount)
)
```

**Groups by:** `(CustomerCode, Date, RouteCode, ItemCode, UserCode)`

**Actual columns in table:**
```
Id, RouteCode, UserCode, CustomerCode, ItemCode, Date, MOdifiedOn,
TotalQty, TotalGRQty, TotalDamageQty, TotalExpiryQty,
TotalSales, TotalGRSales, TotalDamageSales, TotalExpirySales
```

**Missing column:** `PaymentType` — not present in this table. Cash/credit split must come from `tblTrxHeader` directly.

---

## tblRouteSalesSummaryByItem (RSSI)

**Populated by:** `usp_Populate_tblRouteSalesSummary_DataByItem`

**Source tables:** `tblTrxHeader` JOIN `tblTrxDetail`

**Formula difference vs RSIC:** Includes `Attribute17` (additional tax/levy stored as VARCHAR in `tblTrxDetail`)

**Groups by:** `(RouteCode, ItemCode, Date)` — **no customer dimension**

---

## SPs that READ from these tables

### tblRouteSalesSummaryByItemCustomer (RSIC)
| SP | Purpose |
|---|---|
| `sp_DashboardSales_New` | Dashboard KPIs |
| `sp_DashboardSales_SalesPercentage` | Sales % breakdown |
| `SP_SalesOverVieweReport_V1` | Sales overview report |
| `sp_GetMTDSalesOverviewReport_New` | MTD Sales Overview |
| `sp_GetMTDWastage` | MTD Wastage |
| `sp_GetMTDWastageHeaders` | MTD Wastage headers |
| `sp_GetMTDWastage_Count` | MTD Wastage count |
| `sp_GetMTDWastage_Export` | MTD Wastage export |
| `sp_BrandsSale_Search_Report` | Brand wise sales |
| `sp_GetSKUsSold_Formula` | SKU counts |

### tblRouteSalesSummaryByItem (RSSI)
| SP | Purpose |
|---|---|
| `sp_GetSalesmanWiseCollection_Dashboard_Reports_By_Item` | Salesman-wise collection |

---

## PostgreSQL Equivalents

| MSSQL Table | PostgreSQL Table | ETL Function |
|---|---|---|
| `tblRouteSalesSummaryByItemCustomer` | `rpt_route_sales_by_item_customer` | `load_route_sales_by_item_customer` |
| `tblRouteSalesSummaryByItem` | `rpt_route_sales_summary_by_item` | `load_route_sales_summary_by_item` |
