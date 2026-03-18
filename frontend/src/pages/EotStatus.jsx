import { useState, useEffect, useRef } from 'react';
import { fetchEotStatus } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  ShoppingCart, Banknote, Wallet, CheckCircle2, XCircle,
  Eye, X, MapPin, Clock, Phone, BarChart3, User, ChevronRight, Download
} from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

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
  const [modalUser, setModalUser] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchEotStatus(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const kpis = data?.kpis || {};
  const callMetrics = data?.call_metrics || {};
  const users = data?.users || [];

  const exportStops = (user) => {
    const header = ['#', 'Customer Code', 'Customer Name', 'Arrival', 'Departure', 'Duration (min)', 'Productive'].join('\t');
    const rows = user.stops.map(s =>
      [s.sequence, s.customer_code, s.customer_name, s.arrival_time || '', s.departure_time || '', s.duration_mins || 0, s.productive ? 'Yes' : 'No'].join('\t')
    );
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `journey-stops-${user.user_code}.xls`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">EOT Status</h1>
        <p className="text-sm text-gray-500 mt-1">End-of-trip journey details by salesman</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-20">
          <MapPin className="w-12 h-12 text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400 font-medium">No data available</p>
        </div>
      ) : (
        <>
          {/* Compliance + KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className={`rounded-2xl border p-4 flex items-center gap-3 ${data.route_plan_followed ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}>
              {data.route_plan_followed ? <CheckCircle2 className="w-6 h-6 text-emerald-500" /> : <XCircle className="w-6 h-6 text-rose-500" />}
              <div>
                <div className="text-xs text-gray-500 uppercase font-medium">Route Plan</div>
                <div className={`text-lg font-bold ${data.route_plan_followed ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {data.route_plan_followed ? 'Followed' : 'Not Followed'}
                </div>
              </div>
            </div>
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

          {/* Users List */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
                Journey Stops by Salesman ({users.length} users)
              </h2>
            </div>
            <div className="divide-y divide-gray-50">
              {users.map((u, i) => {
                const prodPct = u.total_visits ? Math.round(u.productive_visits / u.total_visits * 100) : 0;
                return (
                  <div key={i} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50/50 transition-colors">
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
                        {(u.user_name || '?')[0].toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold text-gray-900 truncate">{u.user_name}</div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {u.route_name} &bull; {u.user_code}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="text-center hidden md:block">
                        <div className="text-xs text-gray-400 uppercase">Visits</div>
                        <div className="text-sm font-bold text-gray-800">{u.total_visits}</div>
                      </div>
                      <div className="text-center hidden md:block">
                        <div className="text-xs text-gray-400 uppercase">Productive</div>
                        <div className="text-sm font-bold text-emerald-600">{u.productive_visits}</div>
                      </div>
                      <div className="text-center hidden md:block">
                        <div className="text-xs text-gray-400 uppercase">Time</div>
                        <div className="text-sm font-bold text-gray-600">{u.total_time_mins}m</div>
                      </div>
                      <div className="text-center hidden lg:block w-16">
                        <div className="text-xs text-gray-400 uppercase">Prod %</div>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                          prodPct >= 80 ? 'bg-emerald-50 text-emerald-700' :
                          prodPct >= 50 ? 'bg-amber-50 text-amber-700' :
                          'bg-rose-50 text-rose-700'
                        }`}>{prodPct}%</span>
                      </div>
                      <button
                        onClick={() => setModalUser(u)}
                        className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-xl transition-colors"
                      >
                        <Eye className="w-4 h-4" /> View
                      </button>
                    </div>
                  </div>
                );
              })}
              {users.length === 0 && (
                <div className="px-6 py-16 text-center text-gray-400">No journey data found</div>
              )}
            </div>
          </div>
        </>
      )}

      {/* Modal - Journey Stops */}
      {modalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setModalUser(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 text-white flex items-center justify-center text-sm font-bold">
                  {(modalUser.user_name || '?')[0].toUpperCase()}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">{modalUser.user_name}</h2>
                  <p className="text-sm text-gray-500">
                    {modalUser.route_name} &bull; {modalUser.total_visits} stops &bull; {modalUser.productive_visits} productive
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => exportStops(modalUser)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                  <Download className="w-3.5 h-3.5" /> Export
                </button>
                <button onClick={() => setModalUser(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body - Timeline */}
            <div className="flex-1 overflow-auto px-6 py-4">
              <div className="relative">
                {/* Timeline line */}
                <div className="absolute left-[18px] top-0 bottom-0 w-0.5 bg-gray-200" />

                {modalUser.stops.map((stop, i) => (
                  <div key={i} className="relative flex gap-4 pb-4 last:pb-0">
                    {/* Timeline dot */}
                    <div className={`relative z-10 flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shadow-sm ${
                      stop.productive
                        ? 'bg-emerald-500 text-white'
                        : 'bg-gray-300 text-white'
                    }`}>
                      {stop.sequence}
                    </div>

                    {/* Stop card */}
                    <div className={`flex-1 rounded-xl border p-3 ${
                      stop.productive ? 'bg-emerald-50/30 border-emerald-100' : 'bg-gray-50/50 border-gray-100'
                    }`}>
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="font-semibold text-gray-900 text-sm">{stop.customer_name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">{stop.customer_code}</div>
                        </div>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          stop.productive ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'
                        }`}>
                          {stop.productive ? 'Productive' : 'Non-Productive'}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        {stop.arrival_time && (
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {stop.arrival_time.split(' ')[1]?.substring(0, 5) || stop.arrival_time}
                          </span>
                        )}
                        {stop.departure_time && (
                          <span className="flex items-center gap-1">
                            <ChevronRight className="w-3 h-3" />
                            {stop.departure_time.split(' ')[1]?.substring(0, 5) || stop.departure_time}
                          </span>
                        )}
                        {stop.duration_mins != null && (
                          <span className="font-medium text-gray-700">{stop.duration_mins} min</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
