import { useState, useEffect, useRef } from 'react';
import { fetchMtdWastage } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Trash2, Percent, Package, AlertTriangle, Banknote, BarChart3 } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function MtdWastage() {
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
    fetchMtdWastage(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const summary = data?.summary || {};
  const details = data?.details || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">MTD Wastage Summary</h1>
        <p className="text-sm text-gray-500 mt-1">Track expired and damaged inventory across customers</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Summary KPI Cards - 2x3 grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard title="Total Qty" value={summary.total_qty?.toLocaleString() ?? '-'} color="blue" icon={Package} variant="solid" />
            <KpiCard title="Wastage %" value={summary.total_pct != null ? `${Number(summary.total_pct).toFixed(1)}%` : '-'} color="red" icon={Percent} variant="light" />
            <KpiCard title="Expired Value" value={aed(summary.total_expired_value)} color="red" icon={AlertTriangle} variant="solid" />
            <KpiCard title="Damaged Value" value={aed(summary.total_damaged_value)} color="yellow" icon={Trash2} variant="light" />
            <KpiCard title="Total Wastage" value={aed(summary.total_wastage_value)} color="red" icon={Banknote} variant="solid" />
            <KpiCard title="Damaged %" value={summary.damaged_pct != null ? `${Number(summary.damaged_pct).toFixed(1)}%` : '-'} color="yellow" icon={BarChart3} variant="light" />
          </div>

          {/* Customer Details Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Customer Breakdown</h2>
            <DataTable
              columns={[
                { key: 'customer_code', label: 'Customer Code' },
                { key: 'customer_name', label: 'Customer Name' },
                { key: 'qty', label: 'Qty', format: 'number' },
                {
                  key: 'pct', label: 'Wastage %',
                  render: (v) => {
                    const num = Number(v);
                    const colorClass = num > 30 ? 'text-rose-600 bg-rose-50' : num > 20 ? 'text-amber-600 bg-amber-50' : 'text-gray-600 bg-gray-50';
                    return (
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${colorClass}`}>
                        {num != null && !isNaN(num) ? `${num.toFixed(1)}%` : '-'}
                      </span>
                    );
                  }
                },
                { key: 'expired_value', label: 'Expired Value', format: 'currency' },
                { key: 'damaged_value', label: 'Damaged Value', format: 'currency' },
              ]}
              data={details}
              exportName="mtd-wastage"
            />
          </div>
        </>
      )}
    </div>
  );
}
