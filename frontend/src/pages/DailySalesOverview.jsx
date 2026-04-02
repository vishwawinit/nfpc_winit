import { useState, useEffect, useRef } from 'react';
import { fetchDailySalesOverview } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Banknote, CreditCard, ShoppingCart, Percent, Phone, Receipt, Clock } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function DailySalesOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const prevDailySales = useRef(null);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  });

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchDailySalesOverview(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const callSummary = data?.call_summary || {};
  const sales = data?.sales_details || {};
  const items = data?.item_table || [];

  const cashCredit = (sales.cash_sales ?? 0) + (sales.credit_sales ?? 0);
  // Use backend daily_sales (matches dashboard) on first load or when it changes with filters.
  // If daily_sales didn't change after a filter update, the source table didn't reflect the filter
  // (e.g. channel/brand not supported by RSSI) — fall back to cash + credit.
  const isFirstLoad = prevDailySales.current === null;
  const dailySalesChanged = sales.daily_sales !== prevDailySales.current;
  const displayDailySales = (isFirstLoad || dailySalesChanged) ? (sales.daily_sales ?? cashCredit) : cashCredit;
  if (data) prevDailySales.current = sales.daily_sales ?? null;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Daily Sales Overview</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Sales breakdown, call details & brand performance</p>
        </div>
      </div>

      {/* Filters — always mounted */}
      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {/* Refreshing indicator */}
      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {/* Data area — full loading only on first load */}
      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (
        <>
          {/* Call Summary */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">Call Summary</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <KpiCard title="Total Calls" value={callSummary.total_calls ?? '-'} color="blue" icon={Phone} variant="light" />
              <KpiCard title="Prod. Minutes" value={sales.prod_minutes != null ? Number(sales.prod_minutes).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '-'} color="green" icon={Clock} variant="light" />
              <KpiCard title="Total Inv." value={callSummary.total_invoices ?? '-'} color="purple" icon={Receipt} variant="light" />
            </div>
          </div>

          {/* Sales Details */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales Details</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard title="Cash Sales" value={aed(sales.cash_sales)} color="green" icon={Banknote} variant="solid" />
              <KpiCard title="Credit Sales" value={aed(sales.credit_sales)} color="indigo" icon={CreditCard} variant="solid" />
              <KpiCard title="Daily Sales" value={aed(displayDailySales)} color="purple" icon={ShoppingCart} variant="solid" />
              <KpiCard title="Discount" value={aed(sales.discount)} color="yellow" icon={Percent} variant="solid" />
            </div>
          </div>

          {/* Item Performance Table */}
          {items.length > 0 && (
            <div>
              <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">Item Performance</h2>
              <DataTable
                columns={[
                  { key: 'item_code', label: 'Item Code' },
                  { key: 'item_name', label: 'Item Name' },
                  { key: 'brand_name', label: 'Brand' },
                  { key: 'gross_sales', label: 'Gross Sales', format: 'currency2' },
                  { key: 'target_sales', label: 'Target', format: 'currency2' },
                  { key: 'variance', label: 'Variance', format: 'currency2' },
                  { key: 'mtd_gross_sales', label: 'MTD Gross', format: 'currency2' },
                  { key: 'mtd_target_sales', label: 'MTD Target', format: 'currency2' },
                  { key: 'mtd_wastage', label: 'MTD Wastage', format: 'currency2' },
                ]}
                data={items}
                exportName="daily-sales-overview"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
