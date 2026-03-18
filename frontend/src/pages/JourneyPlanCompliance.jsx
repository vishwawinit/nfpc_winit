import { useState, useEffect, useRef, useMemo } from 'react';
import { fetchJourneyPlanCompliance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  CalendarCheck, MapPin, Navigation, Target, Eye, X, Download,
  ChevronLeft, ChevronRight, Search, User
} from 'lucide-react';

const PAGE_SIZES = [20, 50, 100];

function exportToExcel(data, columns, filename) {
  const header = columns.map(c => c.label).join('\t');
  const rows = data.map(row => columns.map(c => row[c.key] ?? '').join('\t'));
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = `${filename}.xls`; a.click();
  URL.revokeObjectURL(url);
}

const coverageColor = (pct) => {
  if (pct >= 90) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200';
  if (pct >= 70) return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200';
  return 'bg-rose-50 text-rose-700 ring-1 ring-rose-200';
};

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function JourneyPlanCompliance() {
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
  const [modalDate, setModalDate] = useState(null);
  const [drillSearch, setDrillSearch] = useState('');
  const [drillPage, setDrillPage] = useState(1);
  const [drillPageSize, setDrillPageSize] = useState(20);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchJourneyPlanCompliance(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const summary = data?.summary || [];
  const drillDown = data?.drill_down || [];

  // KPI totals
  const totScheduled = summary.reduce((s, r) => s + (Number(r.scheduled_calls) || 0), 0);
  const totPlanned = summary.reduce((s, r) => s + (Number(r.planned_calls) || 0), 0);
  const totUnplanned = summary.reduce((s, r) => s + (Number(r.unplanned) || 0), 0);
  const avgCoverage = summary.length
    ? (summary.reduce((s, r) => s + (Number(r.coverage_pct) || 0), 0) / summary.length).toFixed(1) : '-';

  // Modal drill-down data
  const drillForDate = useMemo(() => {
    if (!modalDate) return [];
    let rows = drillDown.filter(d => String(d.date).substring(0, 10) === modalDate);
    if (drillSearch) {
      const s = drillSearch.toLowerCase();
      rows = rows.filter(r =>
        r.user_code?.toLowerCase().includes(s) ||
        r.user_name?.toLowerCase().includes(s) ||
        r.route_code?.toLowerCase().includes(s)
      );
    }
    return rows;
  }, [modalDate, drillDown, drillSearch]);

  const drillTotalPages = Math.max(1, Math.ceil(drillForDate.length / drillPageSize));
  const drillSafePage = Math.min(drillPage, drillTotalPages);
  const drillStartIdx = (drillSafePage - 1) * drillPageSize;
  const drillPaged = drillForDate.slice(drillStartIdx, drillStartIdx + drillPageSize);

  useEffect(() => { setDrillPage(1); setDrillSearch(''); }, [modalDate]);

  const drillColumns = [
    { key: 'user_code', label: 'User Code' },
    { key: 'user_name', label: 'Salesman' },
    { key: 'route_code', label: 'Route' },
    { key: 'scheduled', label: 'Scheduled' },
    { key: 'actual', label: 'Actual' },
    { key: 'planned', label: 'Planned' },
    { key: 'selling', label: 'Selling' },
    { key: 'unplanned', label: 'Unplanned' },
    { key: 'coverage_pct', label: 'Coverage %' },
  ];

  const dayName = (dateStr) => {
    try { return DAY_NAMES[new Date(dateStr).getDay()]; } catch { return ''; }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Journey Plan Compliance</h1>
        <p className="text-sm text-gray-500 mt-1">Daily scheduled vs actual visits with coverage tracking</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Scheduled" value={totScheduled.toLocaleString()} icon={CalendarCheck} color="blue" variant="light" />
            <KpiCard title="Total Planned Visited" value={totPlanned.toLocaleString()} icon={MapPin} color="green" variant="light" />
            <KpiCard title="Total Unplanned" value={totUnplanned.toLocaleString()} icon={Navigation} color="yellow" variant="light" />
            <KpiCard title="Avg Coverage %" value={avgCoverage !== '-' ? `${avgCoverage}%` : '-'} icon={Target}
              color={Number(avgCoverage) >= 90 ? 'green' : Number(avgCoverage) >= 70 ? 'yellow' : 'red'} variant="light" />
          </div>

          {/* Daily Summary Table */}
          <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Daily Summary</h2>
              <button onClick={() => exportToExcel(summary,
                [{ key: 'date', label: 'Date' }, { key: 'num_users', label: 'Users' },
                 { key: 'scheduled_calls', label: 'Scheduled' }, { key: 'planned_calls', label: 'Planned' },
                 { key: 'unplanned', label: 'Unplanned' }, { key: 'coverage_pct', label: 'Coverage %' }],
                'journey-plan-compliance')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                <Download className="w-3.5 h-3.5" /> Export
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Date</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Day</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Users</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Scheduled</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Planned</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Unplanned</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Coverage</th>
                    <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {summary.map((row, i) => (
                    <tr key={i} className={`transition-colors hover:bg-indigo-50/40 ${i % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                      <td className="px-5 py-3 font-medium text-gray-800">{String(row.date).substring(0, 10)}</td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{dayName(row.date)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{row.num_users ?? '-'}</td>
                      <td className="px-4 py-3 text-right tabular-nums font-medium">{row.scheduled_calls?.toLocaleString() ?? '-'}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-emerald-700 font-medium">{row.planned_calls?.toLocaleString() ?? '-'}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-amber-600">{row.unplanned?.toLocaleString() ?? '-'}</td>
                      <td className="px-4 py-3 text-right">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${coverageColor(row.coverage_pct)}`}>
                          {row.coverage_pct != null ? `${Number(row.coverage_pct).toFixed(1)}%` : '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button onClick={() => setModalDate(String(row.date).substring(0, 10))}
                          className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors">
                          <Eye className="w-3.5 h-3.5" /> View
                        </button>
                      </td>
                    </tr>
                  ))}
                  {summary.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-12 text-center text-gray-400">No data available</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Modal - Salesman Detail for selected date */}
      {modalDate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setModalDate(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
                  <User className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">
                    Salesman Detail — {modalDate} ({dayName(modalDate)})
                  </h2>
                  <p className="text-sm text-gray-500">{drillForDate.length} salesmen</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => exportToExcel(drillForDate, drillColumns, `jp-detail-${modalDate}`)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                  <Download className="w-3.5 h-3.5" /> Export
                </button>
                <button onClick={() => setModalDate(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Search */}
            <div className="px-6 py-3 border-b border-gray-100">
              <div className="relative max-w-xs">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type="text" placeholder="Search user, route..." value={drillSearch}
                  onChange={e => { setDrillSearch(e.target.value); setDrillPage(1); }}
                  className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200" />
              </div>
            </div>

            {/* Table */}
            <div className={`flex-1 overflow-auto ${drillPaged.length > 20 ? 'max-h-[500px]' : ''}`}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">User Code</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Salesman</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Route</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Scheduled</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Planned</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Selling</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Unplanned</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Coverage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {drillPaged.map((r, i) => (
                    <tr key={i} className={`hover:bg-indigo-50/30 ${i % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.user_code}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{r.user_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{r.route_code}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{r.scheduled}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-emerald-700 font-medium">{r.planned}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-blue-600">{r.selling}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-amber-600">{r.unplanned}</td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${coverageColor(r.coverage_pct)}`}>
                          {r.coverage_pct != null ? `${Number(r.coverage_pct).toFixed(1)}%` : '-'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {drillPaged.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-12 text-center text-gray-400">No matching records</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Modal Footer - Pagination */}
            <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between bg-gray-50/50">
              <select value={drillPageSize} onChange={e => { setDrillPageSize(Number(e.target.value)); setDrillPage(1); }}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600">
                {PAGE_SIZES.map(s => <option key={s} value={s}>{s} rows</option>)}
              </select>
              <span className="text-xs text-gray-400">
                {drillStartIdx + 1}–{Math.min(drillStartIdx + drillPageSize, drillForDate.length)} of {drillForDate.length}
              </span>
              <div className="flex items-center gap-2">
                <button onClick={() => setDrillPage(p => Math.max(1, p - 1))} disabled={drillSafePage <= 1}
                  className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs text-gray-500 min-w-[70px] text-center">Page {drillSafePage}/{drillTotalPages}</span>
                <button onClick={() => setDrillPage(p => Math.min(drillTotalPages, p + 1))} disabled={drillSafePage >= drillTotalPages}
                  className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
