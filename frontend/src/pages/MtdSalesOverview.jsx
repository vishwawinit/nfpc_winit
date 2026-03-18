import { useState, useEffect, useRef } from 'react';
import { fetchMtdSalesOverview } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Target, TrendingUp, Award, Banknote, MapPin, User, Clock, Phone } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function MtdSalesOverview() {
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
    fetchMtdSalesOverview(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const h = data?.header || {};
  const daily = data?.daily_data || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">MTD Sales Overview</h1>
        <p className="text-sm text-gray-500 mt-1">Month-to-date sales performance with daily breakdown</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Route & Salesman Info */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Route & Salesman</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-6">
              {[
                { icon: MapPin, label: 'Depot', value: h.depot },
                { icon: User, label: 'User Code', value: h.user_code },
                { icon: User, label: 'Salesman', value: h.salesman },
                { icon: MapPin, label: 'Route Code', value: h.route_code },
                { icon: MapPin, label: 'Route Name', value: h.route_name },
                { icon: Clock, label: 'Avg Productive Mins', value: h.avg_productive_mins != null ? `${h.avg_productive_mins} min` : null },
                { icon: Phone, label: 'Avg Daily Calls', value: h.avg_daily_calls },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center">
                    <item.icon className="w-4 h-4 text-indigo-500" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">{item.label}</div>
                    <div className="font-semibold text-gray-900 mt-0.5 truncate">{item.value || '-'}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Target & Achievement KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Monthly Target" value={aed(data.monthly_target)} icon={Target} color="blue" />
            <KpiCard title="Daily Target" value={aed(data.daily_target)} icon={Banknote} color="purple" />
            <KpiCard title="Total Achieved" value={aed(data.total_achieved)} icon={TrendingUp} color="green" />
            <KpiCard title="Achievement %" value={data.achievement_pct != null ? `${Number(data.achievement_pct).toFixed(1)}%` : '-'}
              icon={Award}
              color={data.achievement_pct >= 100 ? 'green' : data.achievement_pct >= 80 ? 'yellow' : 'red'} />
          </div>

          {/* Daily Sales Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Daily Sales Data</h2>
            </div>
            <DataTable
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'day_name', label: 'Day' },
                { key: 'cash_sales', label: 'Cash Sales', format: 'currency' },
                { key: 'credit_sales', label: 'Credit Sales', format: 'currency' },
                { key: 'total_sales', label: 'Total Sales', format: 'currency' },
                { key: 'target', label: 'Target', format: 'currency' },
                { key: 'daily_var', label: 'Daily Var', format: 'currency' },
                { key: 'daily_var_pct', label: 'Var %', format: 'percent' },
                { key: 'cumulative_sales', label: 'Cum. Sales', format: 'currency' },
                { key: 'cumulative_target', label: 'Cum. Target', format: 'currency' },
              ]}
              data={daily}
              exportName="mtd-sales-overview"
            />
          </div>
        </>
      )}
    </div>
  );
}
