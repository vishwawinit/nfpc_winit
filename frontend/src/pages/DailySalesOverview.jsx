import { useState, useEffect } from 'react';
import { fetchDailySalesOverview } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Banknote, CreditCard, ShoppingCart, Percent, Phone, Target, Receipt } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function DailySalesOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchDailySalesOverview(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const sales = data?.sales_details || {};
  const calls = data?.call_details || {};
  const items = data?.item_table || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Daily Sales Overview</h1>
        <p className="text-sm text-gray-500 mt-1">Sales breakdown, call details & brand performance</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'route', 'user_code']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Sales Details */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales Details</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard title="Cash Sales" value={aed(sales.cash_sales)} color="blue" icon={Banknote} variant="solid" />
              <KpiCard title="Credit Sales" value={aed(sales.credit_sales)} color="green" icon={CreditCard} variant="solid" />
              <KpiCard title="Total Sales" value={aed(sales.total_sales)} color="purple" icon={ShoppingCart} variant="solid" />
              <KpiCard title="Discount" value={aed(sales.discount)} color="yellow" icon={Percent} variant="solid" />
            </div>
          </div>

          {/* Call Details */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Call Details</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <KpiCard
                title="Total Calls"
                value={calls.total_calls ?? '-'}
                color="blue"
                icon={Phone}
                variant="light"
              />
              <KpiCard
                title="Selling Calls"
                value={calls.selling_calls ?? '-'}
                color="green"
                icon={Target}
                variant="light"
                subtitle={calls.total_calls ? `${((calls.selling_calls / calls.total_calls) * 100).toFixed(1)}% strike rate` : undefined}
              />
              <KpiCard
                title="Total Invoices"
                value={calls.total_invoices ?? '-'}
                color="purple"
                icon={Receipt}
                variant="light"
              />
            </div>
          </div>

          {/* Brand/Item Table */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Brand Performance</h2>
            <DataTable
              columns={[
                { key: 'brand_code', label: 'Brand Code' },
                { key: 'brand_name', label: 'Brand' },
                { key: 'gross_sales', label: 'Gross Sales', format: 'currency' },
                { key: 'target_sales', label: 'Target', format: 'currency' },
                { key: 'variance', label: 'Variance', format: 'currency' },
                { key: 'mtd_gross_sales', label: 'MTD Gross', format: 'currency' },
                { key: 'mtd_target_sales', label: 'MTD Target', format: 'currency' },
                { key: 'mtd_variance', label: 'MTD Variance', format: 'currency' },
              ]}
              data={items}
              exportName="daily-sales-overview"
            />
          </div>
        </>
      )}
    </div>
  );
}
