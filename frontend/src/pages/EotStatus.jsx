import { useState, useEffect, useRef } from 'react';
import { fetchEotStatus } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  ShoppingCart, Banknote, Wallet,
  MapPin, BarChart3, ChevronRight, Search, ChevronLeft
} from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const fmtDateTime = (dt) => {
  if (!dt) return '-';
  const [date, time] = dt.split(' ');
  if (!time) return date;
  return `${date} ${time.substring(0, 5)}`;
};
const fmtDateTimeFull = (dt) => {
  if (!dt) return '-';
  // Remove microseconds if present (e.g. .213000)
  return dt.replace(/\.\d+$/, '');
};

const PAGE_SIZE = 20;

export default function EotStatus() {
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

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    setPage(1);
    setSearch('');
    fetchEotStatus(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const kpis = data?.kpis || {};
  const callMetrics = data?.call_metrics || {};
  const users = data?.users || [];

  const q = search.toLowerCase();
  const filteredUsers = q
    ? users.filter(u =>
        u.user_name?.toLowerCase().includes(q) ||
        u.user_code?.toLowerCase().includes(q) ||
        u.route_name?.toLowerCase().includes(q) ||
        u.route_code?.toLowerCase().includes(q)
      )
    : users;
  const totalPages = Math.ceil(filteredUsers.length / PAGE_SIZE);
  const pagedUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);


  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">EOT Status</h1>
        <p className="text-sm text-gray-500 mt-1">End-of-trip journey details by salesman</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : !data || !data.users?.length ? (
        <div className="text-center py-20">
          <MapPin className="w-12 h-12 text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400 font-medium">No EOT submissions found for this period</p>
        </div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Orders" value={kpis.order_count ?? '-'} color="blue" icon={ShoppingCart} />
            <KpiCard title="Sales" value={aed(kpis.sales_amount)} color="green" icon={Banknote} />
            <KpiCard title="Collection" value={aed(kpis.collection_amount)} color="purple" icon={Wallet} />
            <KpiCard title="Strike Rate" value={callMetrics.strike_rate != null ? `${callMetrics.strike_rate}%` : '-'} color="yellow" icon={BarChart3} />
          </div>

          {/* Call Metrics Bar */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <div className="grid grid-cols-3 md:grid-cols-7 gap-3 text-center">
              {[
                { label: 'Planned', value: callMetrics.planned, color: 'blue' },
                { label: 'Visited', value: callMetrics.visited, color: 'indigo' },
                { label: 'Productive', value: callMetrics.productive, color: 'emerald' },
                { label: 'Unproductive', value: callMetrics.unproductive, color: 'amber' },
                { label: 'Missed', value: callMetrics.missed, color: 'rose' },
                { label: 'Total Calls', value: callMetrics.total_calls, color: 'violet' },
                { label: 'Strike %', value: callMetrics.strike_rate != null ? `${callMetrics.strike_rate}%` : '-', color: 'cyan' },
              ].map((m, i) => (
                <div key={i} className={`bg-${m.color}-50 rounded-xl px-3 py-2.5`}>
                  <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{m.label}</div>
                  <div className={`text-lg font-bold text-${m.color}-700 mt-0.5`}>{m.value ?? '-'}</div>
                </div>
              ))}
            </div>
          </div>

          {/* EOT Users Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-4">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">
                EOT Users ({filteredUsers.length}{filteredUsers.length !== users.length ? ` / ${users.length}` : ''})
              </h2>
              <div className="relative max-w-xs w-full">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input
                  type="text"
                  value={search}
                  onChange={e => { setSearch(e.target.value); setPage(1); }}
                  placeholder="Search name, code, route…"
                  className="w-full pl-8 pr-3 py-1.5 text-[13px] rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400"
                />
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {['EOT Date & Time', 'User Code', 'User Name', 'Route Code', 'Route Start', 'Unload Date & Time', 'EOT Status'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {pagedUsers.map((u, i) => (
                    <tr key={i} className="hover:bg-gray-50/60 transition-colors">
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap tabular-nums">{fmtDateTime(u.eot_time)}</td>
                      <td className="px-4 py-3 font-mono text-gray-500 whitespace-nowrap">{u.user_code}</td>
                      <td className="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">{u.user_name}</td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{u.route_code}</td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap tabular-nums">{fmtDateTimeFull(u.route_start_datetime)}</td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap tabular-nums">{fmtDateTimeFull(u.unload_datetime)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                          u.eot_status === 'Submitted'
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-amber-50 text-amber-700'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${u.eot_status === 'Submitted' ? 'bg-emerald-500' : 'bg-amber-400'}`} />
                          {u.eot_status || 'Submitted'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {filteredUsers.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-6 py-16 text-center text-gray-400">
                        {search ? `No users matching "${search}"` : 'No EOT data found'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between">
                <span className="text-[12px] text-gray-400">
                  Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filteredUsers.length)} of {filteredUsers.length}
                </span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const pg = totalPages <= 5 ? i + 1 : page <= 3 ? i + 1 : page >= totalPages - 2 ? totalPages - 4 + i : page - 2 + i;
                    return (
                      <button key={pg} onClick={() => setPage(pg)}
                        className={`w-7 h-7 rounded-lg text-[12px] font-medium transition-colors ${pg === page ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
                        {pg}
                      </button>
                    );
                  })}
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

    </div>
  );
}
