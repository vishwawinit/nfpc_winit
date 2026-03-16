import { useState, useEffect } from 'react';
import { fetchTimeManagement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Clock, Play, Square, Timer } from 'lucide-react';

export default function TimeManagement() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchTimeManagement(filters).then(setData).catch(console.error).finally(() => setLoading(false));
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
        showFields={['user_code', 'date_from', 'date_to', 'sales_org']} />

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
