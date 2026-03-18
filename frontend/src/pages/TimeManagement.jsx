import { useState, useEffect, useRef } from 'react';
import { fetchTimeManagement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Clock, Play, Square, Timer } from 'lucide-react';

export default function TimeManagement() {
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
    fetchTimeManagement(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const rows = Array.isArray(data) ? data : [];

  const avgWorking = rows.length
    ? (rows.reduce((s, r) => s + (Number(r.total_working_hours) || 0), 0) / rows.length).toFixed(1)
    : '-';
  const avgProductive = rows.length
    ? (rows.reduce((s, r) => s + (Number(r.productive_time) || 0), 0) / rows.length).toFixed(1)
    : '-';
  const uniqueUsers = rows.length ? new Set(rows.map(r => r.user_code)).size : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Time Management</h1>
        <p className="text-sm text-gray-500 mt-1">Track daily working hours, check-in/out times and productive time per salesman</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Records" value={rows.length.toLocaleString()} icon={Clock} color="blue" variant="light" />
            <KpiCard title="Unique Salesmen" value={uniqueUsers} icon={Play} color="green" variant="light" />
            <KpiCard title="Avg Working Hours" value={avgWorking} icon={Timer} color="purple" variant="light" />
            <KpiCard title="Avg Productive Time" value={avgProductive} icon={Square} color="yellow" variant="light" />
          </div>

          {/* Data Table */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Daily Time Records</h2>
            <DataTable
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'user_code', label: 'User Code' },
                { key: 'user_name', label: 'Salesman' },
                { key: 'eot_start_time', label: 'EOT Start' },
                { key: 'eot_end_time', label: 'EOT End' },
                { key: 'first_checkin', label: 'First Check-in' },
                { key: 'last_checkout', label: 'Last Checkout' },
                { key: 'total_working_hours', label: 'Working Hours', format: 'number' },
                { key: 'productive_time', label: 'Productive Time', format: 'number' },
              ]}
              data={rows}
              exportName="time-management"
            />
          </div>
        </>
      )}
    </div>
  );
}
