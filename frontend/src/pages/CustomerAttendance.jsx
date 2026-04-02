import { useState, useEffect } from 'react';
import { fetchCustomerAttendance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Users, MapPin, Clock, CalendarDays } from 'lucide-react';

export default function CustomerAttendance() {
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
    fetchCustomerAttendance(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  const toSecs = (t) => {
    if (!t) return null;
    const s = String(t).trim();
    // Full datetime string: "YYYY-MM-DD HH:MM:SS"
    if (s.includes(' ') || s.includes('T')) {
      const d = new Date(s.replace(' ', 'T'));
      return isNaN(d.getTime()) ? null : d.getTime() / 1000;
    }
    // Time-only string: "HH:MM:SS"
    const parts = s.split(':').map(Number);
    if (parts.some(isNaN)) return null;
    return parts[0] * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
  };

  const fmtTimeSpent = (row) => {
    const s = toSecs(row.start_time);
    const e = toSecs(row.end_time);
    if (s !== null && e !== null && !isNaN(s) && !isNaN(e) && e > s) {
      const diff = Math.round(e - s);
      const m = Math.floor(diff / 60), sec = diff % 60;
      return `${m}m ${String(sec).padStart(2, '0')}s`;
    }
    // Fallback: total_time_mins from DB
    const v = row.spent_time;
    if (!v && v !== 0) return '—';
    const totalSec = Math.round(Number(v) * 60);
    if (totalSec <= 0) return '—';
    const m = Math.floor(totalSec / 60), sec = totalSec % 60;
    return `${m}m ${String(sec).padStart(2, '0')}s`;
  };

  const rows = Array.isArray(data) ? data : [];

  const uniqueCustomers = rows.length ? new Set(rows.map(r => r.customer_code)).size : 0;
  const uniqueSalesmen = rows.length ? new Set(rows.map(r => r.user_name)).size : 0;
  const uniqueDates = rows.length ? new Set(rows.map(r => r.date)).size : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Customer Attendance</h1>
        <p className="text-sm text-gray-500 mt-1">Visit log with check-in/out times and duration per customer</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'customer', 'channel']} />

      {loading ? <Loading /> : !data || rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Visits" value={rows.length.toLocaleString()} icon={MapPin} color="blue" variant="light" />
            <KpiCard title="Unique Customers" value={uniqueCustomers.toLocaleString()} icon={Users} color="green" variant="light" />
            <KpiCard title="Salesmen" value={uniqueSalesmen} icon={Clock} color="purple" variant="light" />
            <KpiCard title="Days Covered" value={uniqueDates} icon={CalendarDays} color="yellow" variant="light" />
          </div>

          {/* Data Table */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Visit Records</h2>
            <DataTable
              disableSort
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'area', label: 'Route' },
                { key: 'user_name', label: 'Salesman' },
                { key: 'customer_code', label: 'Customer Code' },
                { key: 'customer_name', label: 'Customer Name' },
                { key: 'start_time', label: 'Start Time' },
                { key: 'end_time', label: 'End Time' },
                { key: 'time_spent_str', label: 'Time Spent' },
              ]}
              data={rows.map(r => ({ ...r, time_spent_str: fmtTimeSpent(r) }))}
              exportName="customer-attendance"
            />
          </div>
        </>
      )}
    </div>
  );
}
