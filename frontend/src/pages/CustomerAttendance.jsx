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
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchCustomerAttendance(filters).then(setData).catch(console.error).finally(() => setLoading(false));
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
        showFields={['user_code', 'customer', 'date_from', 'date_to', 'sales_org']} />

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
