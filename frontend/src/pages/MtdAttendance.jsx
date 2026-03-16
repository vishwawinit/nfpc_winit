import { useState, useEffect } from 'react';
import { fetchMtdAttendance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { CalendarCheck, CalendarDays, CalendarX, TrendingUp } from 'lucide-react';

export default function MtdAttendance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchMtdAttendance(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const rows = Array.isArray(data) ? data : [];

  // Compute summary KPIs
  const totalWorkingDays = rows.length
    ? Math.round(rows.reduce((s, r) => s + (Number(r.total_working_days) || 0), 0) / rows.length)
    : '-';
  const totalPresent = rows.reduce((s, r) => s + (Number(r.planned_working_days) || 0), 0);
  const totalAbsent = rows.reduce((s, r) => s + (Number(r.total_absent_days) || 0), 0);
  const avgAttendance = rows.length
    ? (rows.reduce((s, r) => s + (Number(r.attendance_pct) || 0), 0) / rows.length).toFixed(1)
    : '-';

  const attendanceColor = (pct) => {
    if (pct >= 90) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200';
    if (pct >= 75) return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200';
    return 'bg-rose-50 text-rose-700 ring-1 ring-rose-200';
  };

  const tableColumns = [
    { key: 'user_code', label: 'User Code' },
    { key: 'user_name', label: 'Salesman' },
    { key: 'sales_org_code', label: 'Sales Org' },
    { key: 'total_working_days', label: 'Working Days', format: 'number' },
    { key: 'planned_working_days', label: 'Present Days', format: 'number' },
    { key: 'total_absent_days', label: 'Absent Days', format: 'number' },
    { key: 'attendance_pct', label: 'Attendance %' },
  ];

  // Custom render for attendance % with color badges
  const renderRow = (row) => ({
    ...row,
    attendance_pct_display: row.attendance_pct,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">MTD Attendance</h1>
        <p className="text-sm text-gray-500 mt-1">Month-to-date attendance summary with present, absent and attendance percentage</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['user_code', 'date_from', 'date_to', 'sales_org']} />

      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Avg Working Days" value={totalWorkingDays} icon={CalendarDays} color="blue" variant="light" />
            <KpiCard title="Total Present" value={totalPresent.toLocaleString()} icon={CalendarCheck} color="green" variant="light" />
            <KpiCard title="Total Absent" value={totalAbsent.toLocaleString()} icon={CalendarX} color="red" variant="light" />
            <KpiCard title="Avg Attendance %" value={avgAttendance !== '-' ? `${avgAttendance}%` : '-'} icon={TrendingUp}
              color={Number(avgAttendance) >= 90 ? 'green' : Number(avgAttendance) >= 75 ? 'yellow' : 'red'} variant="light" />
          </div>

          {/* Legend */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Attendance Details</h2>
              <div className="flex gap-4 text-xs font-medium text-gray-500">
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-emerald-400"></span> &ge; 90%
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-amber-400"></span> 75 - 90%
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-rose-400"></span> &lt; 75%
                </span>
              </div>
            </div>
          </div>

          {/* Custom Table with colored attendance % */}
          <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80 border-b border-gray-100">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">User Code</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Salesman</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Sales Org</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Working Days</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Present Days</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Absent Days</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Attendance %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {rows.map((r, i) => (
                    <tr key={i} className={`transition-colors ${i % 2 === 0 ? '' : 'bg-gray-50/50'} hover:bg-indigo-50/50`}>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{r.user_code}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{r.user_name}</td>
                      <td className="px-4 py-2.5 text-gray-600">{r.sales_org_code}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{r.total_working_days ?? '-'}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{r.planned_working_days ?? '-'}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{r.total_absent_days ?? '-'}</td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${attendanceColor(r.attendance_pct)}`}>
                          {r.attendance_pct != null ? `${Number(r.attendance_pct).toFixed(1)}%` : '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
