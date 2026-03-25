import { useState, useEffect, useRef, useMemo } from 'react';
import { fetchMtdAttendance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import { Search, Download, ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZES = [20, 50, 100, 200];

function exportToExcel(data, filename) {
  const header = ['Date', 'User Code', 'User Name', 'Route Code', 'Route Name', 'Sales Org'].join('\t');
  const rows = data.map(r =>
    [r.date, r.user_code, r.user_name, r.route_code, r.route_name, r.sales_org_code].join('\t')
  );
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = `${filename}.xls`; a.click();
  URL.revokeObjectURL(url);
}

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

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIdx = (safePage - 1) * pageSize;
  const paged = filtered.slice(startIdx, startIdx + pageSize);

  const columns = [
    { key: 'date',          label: 'Date' },
    { key: 'user_code',     label: 'User Code' },
    { key: 'user_name',     label: 'User Name' },
    { key: 'route_code',    label: 'Route Code' },
    { key: 'route_name',    label: 'Route Name' },
    { key: 'sales_org_code',label: 'Sales Org' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">MTD Attendance</h1>
        <p className="text-sm text-gray-500 mt-1">Journey records for the selected date range</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
          {/* Toolbar */}
          <div className="px-6 py-3 border-b border-gray-100 flex items-center justify-between gap-4">
            <div className="relative min-w-[220px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type="text" placeholder="Search user, route..."
                value={search} onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200" />
            </div>
            <button onClick={() => exportToExcel(filtered, 'mtd-attendance')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
              <Download className="w-3.5 h-3.5" /> Export
            </button>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {columns.map(col => (
                    <th key={col.key} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-left whitespace-nowrap">
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {paged.map((r, i) => (
                  <tr key={i} className={`transition-colors hover:bg-indigo-50/40 ${i % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                    <td className="px-4 py-2.5 tabular-nums text-gray-600">{r.date}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.user_code}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-800">{r.user_name}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.route_code}</td>
                    <td className="px-4 py-2.5 text-gray-600 text-xs">{r.route_name}</td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{r.sales_org_code}</td>
                  </tr>
                ))}
                {paged.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-400">No matching records</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          <div className="px-6 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
            <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none">
              {PAGE_SIZES.map(s => <option key={s} value={s}>{s} rows</option>)}
            </select>
            <span className="text-xs text-gray-400">
              {startIdx + 1}–{Math.min(startIdx + pageSize, filtered.length)} of {filtered.length}
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
      )}
    </div>
  );
}
