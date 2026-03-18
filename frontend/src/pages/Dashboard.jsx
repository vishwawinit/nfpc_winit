import { useState, useEffect, useMemo } from 'react';
import { fetchDashboard } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import { Banknote, Wallet, Phone, Target } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell, PieChart, Pie,
} from 'recharts';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const fmtDate = (d) => {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};
const fmtNum = (v) => v != null ? Number(v).toLocaleString() : '-';
const yAxisFmt = v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v;

/* ─── Distinct Color Palette ─── */
const PAL = {
  // Day-wise: Sales = royal blue, Collection = teal
  daySales:     { solid: '#4f46e5', light: '#6366f1', bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200/60' },
  dayCollection:{ solid: '#0d9488', light: '#14b8a6', bg: 'bg-teal-50',   text: 'text-teal-700',   border: 'border-teal-200/60' },
  // Route Sales: Target = orange, Sales = blue, Collection = emerald
  routeTarget:  { solid: '#ea580c', light: '#f97316', bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200/60' },
  routeSales:   { solid: '#2563eb', light: '#3b82f6', bg: 'bg-blue-50',   text: 'text-blue-700',   border: 'border-blue-200/60' },
  routeColl:    { solid: '#059669', light: '#10b981', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200/60' },
  // Route Visits: Visited = violet, Planned = sky
  visited:      { solid: '#7c3aed', light: '#8b5cf6', bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200/60' },
  planned:      { solid: '#0284c7', light: '#38bdf8', bg: 'bg-sky-50',    text: 'text-sky-700',    border: 'border-sky-200/60' },
  grid: '#f1f5f9',
};

/* ─── Gradient Definitions ─── */
function ChartGradients() {
  return (
    <defs>
      {/* Day-wise */}
      <linearGradient id="gDaySales" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.daySales.light} />
        <stop offset="100%" stopColor={PAL.daySales.solid} />
      </linearGradient>
      <linearGradient id="gDayColl" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.dayCollection.light} />
        <stop offset="100%" stopColor={PAL.dayCollection.solid} />
      </linearGradient>
      {/* Route Sales */}
      <linearGradient id="gRouteTarget" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.routeTarget.light} />
        <stop offset="100%" stopColor={PAL.routeTarget.solid} />
      </linearGradient>
      <linearGradient id="gRouteSales" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.routeSales.light} />
        <stop offset="100%" stopColor={PAL.routeSales.solid} />
      </linearGradient>
      <linearGradient id="gRouteColl" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.routeColl.light} />
        <stop offset="100%" stopColor={PAL.routeColl.solid} />
      </linearGradient>
      {/* Route Visits */}
      <linearGradient id="gVisited" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.visited.light} />
        <stop offset="100%" stopColor={PAL.visited.solid} />
      </linearGradient>
      <linearGradient id="gPlanned" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={PAL.planned.light} />
        <stop offset="100%" stopColor={PAL.planned.solid} />
      </linearGradient>
    </defs>
  );
}

/* ─── Tooltip ─── */
function ChartTooltip({ active, payload, label, formatter, colorMap = {} }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white/95 backdrop-blur-xl rounded-xl border border-gray-200/50 px-4 py-3"
      style={{ boxShadow: '0 20px 48px -12px rgba(0,0,0,0.18), 0 4px 16px -4px rgba(0,0,0,0.08)' }}>
      <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2 pb-2 border-b border-gray-100">{label}</p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2.5 py-[3px]">
          <span className="w-3 h-3 rounded-[4px] flex-shrink-0"
            style={{ background: colorMap[entry.name] || entry.color, boxShadow: `0 0 6px ${colorMap[entry.name] || entry.color}40` }} />
          <span className="text-[12px] text-gray-500 font-medium">{entry.name}</span>
          <span className="text-[13px] font-bold text-gray-900 ml-auto pl-5 tabular-nums">
            {formatter ? formatter(entry.value) : fmtNum(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─── Section Header ─── */
function SectionHeader({ title, subtitle, accent = 'from-indigo-500 to-purple-500', children }) {
  return (
    <div className="chart-header">
      <div className="flex items-center justify-between pb-4 border-b border-gray-100/60 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className={`w-1 h-8 rounded-full bg-gradient-to-b ${accent}`} />
          <div>
            <h2 className="text-[14px] font-bold text-gray-800 tracking-tight">{title}</h2>
            {subtitle && <p className="text-[11px] text-gray-400 mt-0.5 font-medium">{subtitle}</p>}
          </div>
        </div>
        {children && <div className="flex items-center gap-2.5 flex-wrap">{children}</div>}
      </div>
    </div>
  );
}

/* ─── Summary Pill ─── */
function Pill({ label, value, pal }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold border ${pal.bg} ${pal.text} ${pal.border}`}>
      <span className="opacity-60 font-medium">{label}</span>
      <span className="tabular-nums">{value}</span>
    </span>
  );
}

/* ─── Coverage Donut ─── */
function CoverageDonut({ pct }) {
  const color = pct >= 80 ? '#059669' : pct >= 50 ? '#d97706' : '#dc2626';
  const d = [
    { value: Math.min(100, pct), fill: color },
    { value: Math.max(0, 100 - pct), fill: '#f1f5f9' },
  ];
  return (
    <div className="relative w-14 h-14">
      <PieChart width={56} height={56}>
        <Pie data={d} cx={27} cy={27} innerRadius={18} outerRadius={26}
          dataKey="value" startAngle={90} endAngle={-270} strokeWidth={0}>
          {d.map((e, i) => <Cell key={i} fill={e.fill} />)}
        </Pie>
      </PieChart>
      <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold" style={{ color }}>
        {pct?.toFixed(0)}%
      </span>
    </div>
  );
}

/* ─── Legend with color dot ─── */
const legendStyle = { fontSize: '12px', color: '#64748b', paddingTop: '12px' };

export default function Dashboard() {
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
    fetchDashboard(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  const cm = data?.call_metrics || {};
  const targetPct = data?.total_target ? Math.min(100, (data.total_sales / data.total_target * 100)).toFixed(1) : 0;

  const salesChart = (data?.weekly_sales || []).map(r => ({ date: fmtDate(r.date), sales: Number(r.sales || 0) }));
  const collChart = (data?.weekly_collection || []).map(r => ({ date: fmtDate(r.date), collection: Number(r.collection || 0) }));

  const dailyMerged = useMemo(() => {
    const days = {};
    salesChart.forEach(r => { days[r.date] = { ...days[r.date], date: r.date, sales: r.sales }; });
    collChart.forEach(r => { days[r.date] = { ...days[r.date], date: r.date, collection: r.collection }; });
    return Object.values(days).sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  }, [salesChart, collChart]);

  const routeSales = (data?.route_wise_sales_vs_target || []).map(r => ({
    route: r.route_name || r.route_code,
    sales: Number(r.sales || 0), collection: Number(r.collection || 0), target: Number(r.target || 0),
  }));
  const routeVisits = (data?.route_wise_visits || []).map(r => ({
    route: r.route_name || r.route_code,
    actual: Number(r.actual || 0), scheduled: Number(r.scheduled || 0), selling: Number(r.selling || 0),
  }));

  const totalRouteSales = routeSales.reduce((s, r) => s + r.sales, 0);
  const totalRouteCollection = routeSales.reduce((s, r) => s + r.collection, 0);
  const totalRouteTarget = routeSales.reduce((s, r) => s + r.target, 0);
  const totalVisitsActual = routeVisits.reduce((s, r) => s + r.actual, 0);
  const totalVisitsScheduled = routeVisits.reduce((s, r) => s + r.scheduled, 0);
  const totalVisitsSelling = routeVisits.reduce((s, r) => s + r.selling, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Dashboard</h1>
        <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Sales, collection & call performance overview</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-20 text-gray-400 font-medium">No data available</div>
      ) : (<>

      {/* ═══════════ KPI Row ═══════════ */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard title="Total Sales" value={aed(data.total_sales)} color="blue" icon={Banknote} variant="solid" />
        <KpiCard title="Total Collection" value={aed(data.total_collection)} color="green" icon={Wallet} variant="solid" />

        {/* Target vs Achievement */}
        <div className="kpi-card bg-white rounded-2xl shadow-sm border border-gray-100/80 p-5 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-amber-400 via-orange-500 to-red-400 opacity-70 rounded-t-2xl" />
          <div className="flex items-center gap-3 mb-3.5">
            <div className="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center bg-gradient-to-br from-amber-50 to-orange-50 text-orange-600 shadow-sm ring-1 ring-orange-200/40">
              <Target className="w-5 h-5" strokeWidth={1.75} />
            </div>
            <div className="text-[11px] font-bold text-orange-600/80 uppercase tracking-wider">Target vs Achievement</div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-gray-400 font-medium">Target</span>
              <span className="font-bold text-gray-700 tabular-nums">{aed(data.total_target)}</span>
            </div>
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-gray-400 font-medium">Achieved</span>
              <span className="font-bold text-emerald-600 tabular-nums">{aed(data.total_sales)}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2.5 mt-1.5 overflow-hidden">
              <div
                className={`h-2.5 rounded-full transition-all duration-700 ease-out ${Number(targetPct) >= 100 ? 'bg-gradient-to-r from-emerald-400 to-emerald-600' : Number(targetPct) >= 75 ? 'bg-gradient-to-r from-amber-400 to-orange-500' : 'bg-gradient-to-r from-red-400 to-red-500'}`}
                style={{ width: `${Math.min(100, targetPct)}%` }}
              />
            </div>
            <div className="text-right text-[14px] font-bold tabular-nums" style={{ color: Number(targetPct) >= 100 ? '#059669' : Number(targetPct) >= 75 ? '#ea580c' : '#dc2626' }}>
              {targetPct}%
            </div>
          </div>
        </div>

        {/* Calls & Coverage */}
        <div className="kpi-card bg-white rounded-2xl shadow-sm border border-gray-100/80 p-5 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-violet-400 via-purple-500 to-fuchsia-500 opacity-70 rounded-t-2xl" />
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center bg-gradient-to-br from-violet-50 to-purple-50 text-purple-600 shadow-sm ring-1 ring-purple-200/40">
              <Phone className="w-5 h-5" strokeWidth={1.75} />
            </div>
            <div className="text-[11px] font-bold text-purple-600/80 uppercase tracking-wider">Calls & Coverage</div>
            <div className="ml-auto"><CoverageDonut pct={cm.coverage_pct || 0} /></div>
          </div>
          <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-[13px]">
            {[
              ['Scheduled', cm.scheduled_calls, ''],
              ['Actual', cm.actual_calls, ''],
              ['Planned', cm.planned_calls, ''],
              ['Unplanned', cm.unplanned_calls, ''],
              ['Selling', cm.selling_calls, 'text-emerald-600'],
              ['Strike Rate', `${cm.strike_rate?.toFixed(1)}%`, 'text-orange-600'],
            ].map(([lbl, val, cls]) => (
              <div key={lbl} className="flex items-center justify-between">
                <span className="text-gray-400 font-medium">{lbl}</span>
                <span className={`font-bold tabular-nums ${cls || 'text-gray-700'}`}>{typeof val === 'number' ? fmtNum(val) : val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ═══════════ Day-wise Sales & Collection ═══════════ */}
      {dailyMerged.length > 0 && (
        <div className="chart-container">
          <SectionHeader title="Day-wise Sales & Collection" subtitle="Daily comparison" accent="from-indigo-600 to-teal-500">
            <Pill label="Sales" value={aed(dailyMerged.reduce((s, r) => s + (r.sales || 0), 0))} pal={PAL.daySales} />
            <Pill label="Collection" value={aed(dailyMerged.reduce((s, r) => s + (r.collection || 0), 0))} pal={PAL.dayCollection} />
          </SectionHeader>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, dailyMerged.length * 56) }}>
              <ResponsiveContainer width="100%" height={340}>
                <BarChart data={dailyMerged} barCategoryGap="18%" barGap={3}>
                  <ChartGradients />
                  <CartesianGrid strokeDasharray="3 3" stroke={PAL.grid} vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8', angle: -35, textAnchor: 'end' }} height={50} axisLine={false} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} width={50} />
                  <Tooltip content={<ChartTooltip formatter={aed} colorMap={{ Sales: PAL.daySales.solid, Collection: PAL.dayCollection.solid }} />}
                    cursor={{ fill: 'rgba(79, 70, 229, 0.04)', radius: 4 }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
                  <Bar dataKey="sales" fill="url(#gDaySales)" name="Sales" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="collection" fill="url(#gDayColl)" name="Collection" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════ Route Wise Sales vs Target vs Collection ═══════════ */}
      {routeSales.length > 0 && (
        <div className="chart-container">
          <SectionHeader title="Route Wise Sales vs Target vs Collection" accent="from-blue-600 to-orange-500">
            <Pill label="Sales" value={aed(totalRouteSales)} pal={PAL.routeSales} />
            <Pill label="Target" value={aed(totalRouteTarget)} pal={PAL.routeTarget} />
            <Pill label="Collection" value={aed(totalRouteCollection)} pal={PAL.routeColl} />
            {totalRouteTarget > 0 && (
              <Pill label="Ach." value={`${(totalRouteSales / totalRouteTarget * 100).toFixed(1)}%`}
                pal={totalRouteSales >= totalRouteTarget ? PAL.routeColl : PAL.routeTarget} />
            )}
          </SectionHeader>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, routeSales.length * 100) }}>
              <ResponsiveContainer width="100%" height={380}>
                <BarChart data={routeSales} barCategoryGap="18%" barGap={2}>
                  <ChartGradients />
                  <CartesianGrid strokeDasharray="3 3" stroke={PAL.grid} vertical={false} />
                  <XAxis dataKey="route" tick={{ fontSize: 10, fill: '#64748b', angle: -40, textAnchor: 'end' }} height={75} axisLine={false} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} width={50} />
                  <Tooltip content={<ChartTooltip formatter={aed} colorMap={{ Target: PAL.routeTarget.solid, Sales: PAL.routeSales.solid, Collection: PAL.routeColl.solid }} />}
                    cursor={{ fill: 'rgba(37, 99, 235, 0.04)', radius: 4 }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
                  <Bar dataKey="target" fill="url(#gRouteTarget)" name="Target" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="sales" fill="url(#gRouteSales)" name="Sales" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="collection" fill="url(#gRouteColl)" name="Collection" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════ Route Wise Visits ═══════════ */}
      {routeVisits.length > 0 && (
        <div className="chart-container">
          <SectionHeader title="Route Wise Visits" accent="from-violet-600 to-sky-500">
            <Pill label="Planned" value={fmtNum(totalVisitsScheduled)} pal={PAL.planned} />
            <Pill label="Visited" value={fmtNum(totalVisitsActual)} pal={PAL.visited} />
            <Pill label="Selling" value={fmtNum(totalVisitsSelling)} pal={PAL.visited} />
            {totalVisitsScheduled > 0 && (
              <Pill label="Coverage"
                value={`${Math.min(100, (totalVisitsActual / totalVisitsScheduled * 100)).toFixed(1)}%`}
                pal={totalVisitsActual >= totalVisitsScheduled ? PAL.visited : PAL.planned} />
            )}
          </SectionHeader>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, routeVisits.length * 100) }}>
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={routeVisits} barCategoryGap="18%" barGap={4}>
                  <ChartGradients />
                  <CartesianGrid strokeDasharray="3 3" stroke={PAL.grid} vertical={false} />
                  <XAxis dataKey="route" tick={{ fontSize: 10, fill: '#64748b', angle: -40, textAnchor: 'end' }} height={65} axisLine={false} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={45} />
                  <Tooltip content={<ChartTooltip colorMap={{ Visited: PAL.visited.solid, Planned: PAL.planned.solid }} />}
                    cursor={{ fill: 'rgba(124, 58, 237, 0.04)', radius: 4 }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} />
                  <Bar dataKey="actual" fill="url(#gVisited)" name="Visited" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="scheduled" fill="url(#gPlanned)" name="Planned" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      </>)}
    </div>
  );
}
