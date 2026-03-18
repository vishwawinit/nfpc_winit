import { useState, useEffect, useRef } from 'react';
import { fetchLogReport } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Phone, PhoneCall, PhoneOff, Target, Banknote, Receipt, Wallet, TrendingUp } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

const callIcons = {
  total_calls: Phone,
  productive_calls: PhoneCall,
  non_productive_calls: PhoneOff,
  strike_rate: Target,
};

export default function LogReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
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
    fetchLogReport(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const callSummary = data?.call_summary || {};
  const salesSummary = data?.sales_summary || {};
  const users = data?.user_data || [];

  const callColors = ['blue', 'green', 'red', 'yellow'];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Log Report</h1>
        <p className="text-sm text-gray-500 mt-1">Daily call activity and sales performance by salesman</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Call Summary */}
          {Object.keys(callSummary).length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Call Summary</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(callSummary).map(([key, val], idx) => {
                  const IconComp = callIcons[key] || Phone;
                  return (
                    <KpiCard
                      key={key}
                      title={key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      value={typeof val === 'number' ? val.toLocaleString() : val ?? '-'}
                      color={callColors[idx % callColors.length]}
                      icon={IconComp}
                      variant="light"
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Sales Summary */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales Summary</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard title="Total Sales" value={aed(salesSummary.total_sales)} color="green" icon={Banknote} variant="solid" />
              <KpiCard title="Credit Notes" value={aed(salesSummary.total_credit_notes)} color="red" icon={Receipt} variant="solid" />
              <KpiCard title="Collection Received" value={aed(salesSummary.collection_received)} color="blue" icon={Wallet} variant="solid" />
              <KpiCard title="Current Month Sales" value={aed(salesSummary.current_month_sales)} color="purple" icon={TrendingUp} variant="solid" />
            </div>
          </div>

          {/* User-Level Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Salesman Performance</h2>
            <DataTable
              columns={[
                { key: 'user_code', label: 'User Code' },
                { key: 'user_name', label: 'Salesman' },
                { key: 'sales_org_name', label: 'Sales Org' },
                { key: 'sales_amount', label: 'Sales', format: 'currency' },
                { key: 'credit_amount', label: 'Credit Notes', format: 'currency' },
                { key: 'collection_amount', label: 'Collection', format: 'currency' },
              ]}
              data={users}
              exportName="log-report"
            />
          </div>
        </>
      )}
    </div>
  );
}
