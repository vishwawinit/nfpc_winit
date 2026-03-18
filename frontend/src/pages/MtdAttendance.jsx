import { useState, useEffect, useRef, useMemo } from 'react';
import { fetchMtdAttendance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import { CalendarCheck, CalendarDays, CalendarX, TrendingUp, Search, Download, ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZES = [20, 50, 100, 200];

function exportToExcel(data, filename) {
  const header = ['User Code', 'Salesman', 'Route Code', 'Route Name', 'Sales Org', 'Working Days', 'Present', 'Absent', 'Attendance %'].join('\t');
  const rows = data.map(r =>
    [r.user_code, r.user_name, r.route_code, r.route_name, r.sales_org_code, r.total_working_days, r.planned_working_days, r.total_absent_days, r.attendance_pct].join('\t')
  );
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = `${filename}.xls`; a.click();
  URL.revokeObjectURL(url);
}

const attendanceColor = (pct) => {
  if (pct >= 90) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200';
  if (pct >= 75) return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200';
  return 'bg-rose-50 text-rose-700 ring-1 ring-rose-200';
};

export default function MtdAttendance() {
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
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortCol, setSortCol] = useState('attendance_pct');
  const [sortDir, setSortDir] = useState('asc');

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchMtdAttendance(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  useEffect(() => { setPage(1); }, [search, filters, pageSize]);

  const rows = Array.isArray(data) ? data : [];

  // Search
  const filtered = useMemo(() => {
    if (!search) return rows;
    const s = search.toLowerCase();
    return rows.filter(r =>
      r.user_code?.toLowerCase().includes(s) ||
      r.user_name?.toLowerCase().includes(s) ||
      r.route_code?.toLowerCase().includes(s) ||
      r.route_name?.toLowerCase().includes(s)
    );
  }, [rows, search]);

  // Sort
  const sorted = useMemo(() => {
    if (!sortCol) return filtered;
    return [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filtered, sortCol, sortDir]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIdx = (safePage - 1) * pageSize;
  const paged = sorted.slice(startIdx, startIdx + pageSize);

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
    setPage(1);
  };

  // KPI summaries
  const totalWorkingDays = rows.length ? rows[0]?.total_working_days || '-' : '-';
  const totalPresent = rows.reduce((s, r) => s + (Number(r.planned_working_days) || 0), 0);
  const totalAbsent = rows.reduce((s, r) => s + (Number(r.total_absent_days) || 0), 0);
  const avgAttendance = rows.length
    ? (rows.reduce((s, r) => s + (Number(r.attendance_pct) || 0), 0) / rows.length).toFixed(1)
    : '-';

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span className="text-gray-300 ml-1">↕</span>;
    return <span className="text-indigo-500 ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  const columns = [
    { key: 'user_code', label: 'User Code', align: 'left' },
    { key: 'user_name', label: 'Salesman', align: 'left' },
    { key: 'route_code', label: 'Route', align: 'left' },
    { key: 'route_name', label: 'Route Name', align: 'left' },
    { key: 'sales_org_code', label: 'Sales Org', align: 'left' },
    { key: 'total_working_days', label: 'Working Days', align: 'right' },
    { key: 'planned_working_days', label: 'Present', align: 'right' },
    { key: 'total_absent_days', label: 'Absent', align: 'right' },
    { key: 'attendance_pct', label: 'Attendance %', align: 'right' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">MTD Attendance</h1>
        <p className="text-sm text-gray-500 mt-1">Month-to-date attendance with present, absent and percentage</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Working Days" value={totalWorkingDays} icon={CalendarDays} color="blue" variant="light" />
            <KpiCard title="Total Present" value={totalPresent.toLocaleString()} icon={CalendarCheck} color="green" variant="light" />
            <KpiCard title="Total Absent" value={totalAbsent.toLocaleString()} icon={CalendarX} color="red" variant="light" />
            <KpiCard title="Avg Attendance %" value={avgAttendance !== '-' ? `${avgAttendance}%` : '-'} icon={TrendingUp}
              color={Number(avgAttendance) >= 90 ? 'green' : Number(avgAttendance) >= 75 ? 'yellow' : 'red'} variant="light" />
          </div>

          {/* Attendance Table */}
          <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
            {/* Toolbar */}
            <div className="px-6 py-3 border-b border-gray-100 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input type="text" placeholder="Search user, route..."
                    value={search} onChange={e => setSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200" />
                </div>
                {/* Legend */}
                <div className="hidden md:flex gap-3 text-xs font-medium text-gray-500">
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-400" /> ≥90%</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> 75-90%</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-rose-400" /> &lt;75%</span>
                </div>
              </div>
              <button onClick={() => exportToExcel(sorted, 'mtd-attendance')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                <Download className="w-3.5 h-3.5" /> Export
              </button>
            </div>

            {/* Table */}
            <div className={`overflow-x-auto ${paged.length > 20 ? 'max-h-[600px] overflow-y-auto' : ''}`}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {columns.map(col => (
                      <th key={col.key}
                        onClick={() => handleSort(col.key)}
                        className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 select-none ${col.align === 'right' ? 'text-right' : 'text-left'}`}>
                        {col.label}<SortIcon col={col.key} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {paged.map((r, i) => (
                    <tr key={i} className={`transition-colors hover:bg-indigo-50/40 ${i % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.user_code}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{r.user_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.route_code}</td>
                      <td className="px-4 py-2.5 text-gray-600 text-xs">{r.route_name}</td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs">{r.sales_org_code}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{r.total_working_days}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-medium text-emerald-700">{r.planned_working_days}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-medium text-rose-600">{r.total_absent_days}</td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${attendanceColor(r.attendance_pct)}`}>
                          {r.attendance_pct != null ? `${Number(r.attendance_pct).toFixed(1)}%` : '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {paged.length === 0 && (
                    <tr><td colSpan={9} className="px-4 py-12 text-center text-gray-400">No matching records</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Footer: PageSize + Info + Pagination */}
            <div className="px-6 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
              <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none">
                {PAGE_SIZES.map(s => <option key={s} value={s}>{s} rows</option>)}
              </select>
              <span className="text-xs text-gray-400">
                {startIdx + 1}–{Math.min(startIdx + pageSize, sorted.length)} of {sorted.length}
                {search && ` (filtered from ${rows.length})`}
              </span>
              <div className="flex items-center gap-2">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage <= 1}
                  className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 transition-colors">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs text-gray-500 min-w-[80px] text-center">Page {safePage}/{totalPages}</span>
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}
                  className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 transition-colors">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
