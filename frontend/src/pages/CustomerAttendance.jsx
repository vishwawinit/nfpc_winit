import { useState, useEffect, useRef } from 'react';
import { fetchCustomerAttendance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Users, MapPin, Clock, CalendarDays } from 'lucide-react';

export default function CustomerAttendance() {
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
    fetchCustomerAttendance(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

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
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {loading ? <Loading /> : rows.length === 0 ? (
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
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'area', label: 'Area' },
                { key: 'user_name', label: 'Salesman' },
                { key: 'customer_code', label: 'Customer Code' },
                { key: 'customer_name', label: 'Customer Name' },
                { key: 'start_time', label: 'Start Time' },
                { key: 'end_time', label: 'End Time' },
                { key: 'spent_time', label: 'Time Spent' },
              ]}
              data={rows}
              exportName="customer-attendance"
            />
          </div>
        </>
      )}
    </div>
  );
}
