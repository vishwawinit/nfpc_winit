import { useState, useEffect, useRef, useMemo } from 'react';
import { fetchSalesmanJourney, fetchSalesmanJourneyDetail } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  MapPin, Clock, Navigation, ChevronDown, ChevronRight, Route,
  Banknote, Wallet, Users, Package, Search, Download
} from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function SalesmanJourney() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const today = `${y}-${m}-${d}`;
    return { date_from: today, date_to: today };
  });
  const [expandedUser, setExpandedUser] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchSalesmanJourney(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const handleExpand = (user) => {
    if (expandedUser === user.user_code) {
      setExpandedUser(null);
      setDetail(null);
      return;
    }
    setExpandedUser(user.user_code);
    setDetailLoading(true);
    setDetail(null);
    fetchSalesmanJourneyDetail({ ...filters, user_code: user.user_code })
      .then(setDetail)
      .catch(console.error)
      .finally(() => setDetailLoading(false));
  };

  const users = data?.users || [];
  const filtered = useMemo(() => {
    if (!search) return users;
    const s = search.toLowerCase();
    return users.filter(u =>
      u.user_code?.toLowerCase().includes(s) ||
      u.user_name?.toLowerCase().includes(s) ||
      u.route_code?.toLowerCase().includes(s) ||
      u.route_name?.toLowerCase().includes(s)
    );
  }, [users, search]);

  // Summary KPIs
  const totalSales = users.reduce((s, u) => s + (Number(u.total_sales) || 0), 0);
  const totalCustomers = users.reduce((s, u) => s + (Number(u.customer_count) || 0), 0);
  const totalSku = users.reduce((s, u) => s + (Number(u.sku_count) || 0), 0);

  const exportUsers = () => {
    const header = ['User Code', 'Salesman', 'Route', 'Route Name', 'Sales', 'Customers', 'SKUs', 'Days'].join('\t');
    const rows = filtered.map(u => [u.user_code, u.user_name, u.route_code, u.route_name, u.total_sales, u.customer_count, u.sku_count, u.active_days].join('\t'));
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'salesman-journey.xls'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Salesman Journey</h1>
        <p className="text-sm text-gray-500 mt-1">Track salesmen routes, visits and performance. Click to expand journey details.</p>
      </div>

      <FilterPanel filters={filters} onChange={(f) => {
        // Enforce single day: sync date_to with date_from
        if (f.date_from && f.date_from !== filters.date_from) {
          f.date_to = f.date_from;
        }
        setFilters(f);
      }}
        showFields={['date_from', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : users.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <KpiCard title="Salesmen" value={users.length} icon={Users} color="blue" variant="light" />
            <KpiCard title="Total Sales" value={aed(totalSales)} icon={Banknote} color="green" variant="solid" />
            <KpiCard title="Total Customers" value={totalCustomers.toLocaleString()} icon={MapPin} color="purple" variant="light" />
            <KpiCard title="Total SKUs" value={totalSku.toLocaleString()} icon={Package} color="indigo" variant="light" />
          </div>

          {/* User Accordion List */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            {/* Toolbar */}
            <div className="px-6 py-3 border-b border-gray-100 flex items-center justify-between gap-4">
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type="text" placeholder="Search salesman, route..." value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200" />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">{filtered.length} salesmen</span>
                <button onClick={exportUsers}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg">
                  <Download className="w-3.5 h-3.5" /> Export
                </button>
              </div>
            </div>

            {/* Accordion */}
            <div className="divide-y divide-gray-50 max-h-[700px] overflow-y-auto">
              {filtered.map((u, i) => {
                const isOpen = expandedUser === u.user_code;
                return (
                  <div key={i}>
                    {/* User Row */}
                    <div
                      onClick={() => handleExpand(u)}
                      className={`px-6 py-4 flex items-center justify-between cursor-pointer transition-colors ${
                        isOpen ? 'bg-indigo-50/60' : 'hover:bg-gray-50/70'
                      }`}
                    >
                      <div className="flex items-center gap-4 flex-1 min-w-0">
                        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
                          {(u.user_name || '?')[0].toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="font-semibold text-gray-900 truncate">{u.user_name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">
                            {u.route_code} &bull; {u.route_name} &bull; {u.user_code}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-6">
                        <div className="text-center hidden md:block">
                          <div className="text-[10px] text-gray-400 uppercase">Sales</div>
                          <div className="text-sm font-bold text-gray-800">{aed(u.total_sales)}</div>
                        </div>
                        <div className="text-center hidden md:block">
                          <div className="text-[10px] text-gray-400 uppercase">Customers</div>
                          <div className="text-sm font-bold text-gray-700">{u.customer_count}</div>
                        </div>
                        <div className="text-center hidden lg:block">
                          <div className="text-[10px] text-gray-400 uppercase">SKUs</div>
                          <div className="text-sm font-bold text-gray-700">{u.sku_count}</div>
                        </div>
                        <div className="text-center hidden lg:block">
                          <div className="text-[10px] text-gray-400 uppercase">Days</div>
                          <div className="text-sm font-bold text-gray-700">{u.active_days}</div>
                        </div>
                        <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                      </div>
                    </div>

                    {/* Expanded Detail */}
                    {isOpen && (
                      <div className="bg-gray-50/50 border-t border-gray-100">
                        {detailLoading ? (
                          <div className="p-8 text-center"><Loading /></div>
                        ) : detail ? (
                          <div className="p-5 space-y-4">
                            {/* Detail KPIs */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                              <div className="bg-white rounded-xl border border-gray-100 p-3 text-center">
                                <div className="text-[10px] text-gray-400 uppercase font-semibold">Sales</div>
                                <div className="text-lg font-bold text-emerald-700">{aed(detail.kpis?.total_sales)}</div>
                              </div>
                              <div className="bg-white rounded-xl border border-gray-100 p-3 text-center">
                                <div className="text-[10px] text-gray-400 uppercase font-semibold">Collection</div>
                                <div className="text-lg font-bold text-purple-700">{aed(detail.kpis?.collection)}</div>
                              </div>
                              <div className="bg-white rounded-xl border border-gray-100 p-3 text-center">
                                <div className="text-[10px] text-gray-400 uppercase font-semibold">Start</div>
                                <div className="text-sm font-bold text-gray-700">
                                  {detail.journey_info?.journey_start?.substring(11, 16) || '-'}
                                </div>
                              </div>
                              <div className="bg-white rounded-xl border border-gray-100 p-3 text-center">
                                <div className="text-[10px] text-gray-400 uppercase font-semibold">End</div>
                                <div className="text-sm font-bold text-gray-700">
                                  {detail.journey_info?.journey_end?.substring(11, 16) || '-'}
                                </div>
                              </div>
                            </div>

                            {/* Visits Timeline */}
                            <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
                              <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                                <span className="text-xs font-semibold text-gray-500 uppercase">
                                  {detail.visits?.length || 0} Stops &bull; {detail.visits?.filter(v => v.productive).length || 0} Productive
                                </span>
                              </div>
                              <div className={`p-4 ${(detail.visits?.length || 0) > 10 ? 'max-h-[400px] overflow-y-auto' : ''}`}>
                                <div className="relative">
                                  <div className="absolute left-[14px] top-0 bottom-0 w-0.5 bg-gray-200" />
                                  {(detail.visits || []).map((v, vi) => (
                                    <div key={vi} className="relative flex gap-3 pb-2 last:pb-0">
                                      <div className={`relative z-10 flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${
                                        v.productive ? 'bg-emerald-500 text-white' : 'bg-gray-300 text-white'
                                      }`}>{v.sequence}</div>
                                      <div className={`flex-1 rounded-lg border px-3 py-2 text-xs ${
                                        v.productive ? 'bg-emerald-50/40 border-emerald-100' : 'bg-white border-gray-100'
                                      }`}>
                                        <div className="flex items-center justify-between">
                                          <span className="font-medium text-gray-800">{v.customer_name}</span>
                                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                                            v.productive ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'
                                          }`}>{v.productive ? 'P' : 'NP'}</span>
                                        </div>
                                        <div className="flex gap-3 mt-1 text-gray-400">
                                          {v.arrival_time && <span><Clock className="w-3 h-3 inline mr-0.5" />{v.arrival_time.split(' ')[1]?.substring(0, 5)}</span>}
                                          {v.duration_mins != null && <span>{v.duration_mins}min</span>}
                                          <span className="text-gray-300">{v.customer_code}</span>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="p-8 text-center text-gray-400">No detail available</div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div className="px-6 py-16 text-center text-gray-400">No matching salesmen</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
