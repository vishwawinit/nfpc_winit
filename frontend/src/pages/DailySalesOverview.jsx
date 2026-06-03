import { useState, useEffect } from 'react';
import { fetchDailySalesOverview } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Banknote, CreditCard, ShoppingCart, Percent, Phone, Receipt, Clock, RotateCcw } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const num = (v) => v != null ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '-';

const ITEM_COLUMNS = [
  { key: 'item_code',       label: 'Item Code' },
  { key: 'item_name',       label: 'Item Name' },
  { key: 'brand_name',      label: 'Brand' },
  { key: 'gross_sales',     label: 'Period Sales',  format: 'currency2' },
  { key: 'mtd_gross_sales', label: 'MTD Sales',     format: 'currency2' },
  { key: 'mtd_wastage',     label: 'MTD Wastage',   format: 'currency2' },
];

export default function DailySalesOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDailySalesOverview(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  const callSummary = data?.call_summary || {};
  const sales = data?.sales_details || {};
  const items = data?.item_table || [];

  const displayDailySales = (sales.cash_sales ?? 0) + (sales.credit_sales ?? 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Daily Sales Overview</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Sales breakdown, call details & brand performance</p>
        </div>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (
        <>
          {/* Call Summary */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">Call Summary</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <KpiCard title="Total Calls"   value={num(callSummary.total_calls)}   color="blue"   icon={Phone}    variant="light" />
              <KpiCard title="Prod. Minutes" value={num(sales.prod_minutes)}         color="green"  icon={Clock}    variant="light" />
              <KpiCard title="Total Inv."    value={num(callSummary.total_invoices)} color="purple" icon={Receipt}  variant="light" />
            </div>
          </div>

          {/* Sales Details */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales Details</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <KpiCard title="Cash Sales"    value={aed(sales.cash_sales)}    color="green"  icon={Banknote}    variant="solid" />
              <KpiCard title="Credit Sales"  value={aed(sales.credit_sales)}  color="indigo" icon={CreditCard}  variant="solid" />
              <KpiCard title="Daily Sales"   value={aed(displayDailySales)}   color="purple" icon={ShoppingCart} variant="solid" />
              <KpiCard title="Total Returns" value={aed(sales.total_returns)} color="red"    icon={RotateCcw}   variant="solid" />
              <KpiCard title="Discount"      value={aed(sales.discount)}      color="yellow" icon={Percent}     variant="solid" />
            </div>
          </div>

          {/* Item Performance Table */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Item Performance
              {items.length > 0 && (
                <span className="ml-2 text-[11px] font-normal text-gray-400 normal-case">({items.length} items)</span>
              )}
            </h2>
            {items.length === 0 ? (
              <div className="bg-white rounded-2xl border border-gray-100 py-16 text-center text-gray-400 font-medium">
                No item data for selected period
              </div>
            ) : (
              <DataTable
                columns={ITEM_COLUMNS}
                data={items}
                exportName="daily-sales-item-performance"
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}
