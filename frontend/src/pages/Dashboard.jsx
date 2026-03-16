import { useState, useEffect } from 'react';
import { fetchDashboard } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import { Banknote, Wallet, Phone, Target } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell,
} from 'recharts';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const fmtDate = (d) => {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};
const fmtNum = (v) => v != null ? Number(v).toLocaleString() : '-';

const chartTooltipStyle = {
  borderRadius: '10px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 8px 24px -4px rgb(0 0 0 / 0.08)',
  fontSize: '13px',
  padding: '10px 14px',
  backgroundColor: '#ffffff',
};

const yAxisFmt = v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v;

/* Chart color tokens */
const COLORS = {
  sales: '#6366f1',
  collection: '#10b981',
  target: '#f59e0b',
  salesLight: '#a5b4fc',
  pending: '#e5e7eb',
  visited: '#34d399',
  grid: '#f3f4f6',
};

/* Section header component for chart cards */
function SectionHeader({ title, children }) {
  return (
    <div className="chart-header">
      <div className="flex items-center justify-between pb-4 border-b border-gray-100/80">
        <h2 className="text-[13px] font-semibold text-gray-700 uppercase tracking-wide">{title}</h2>
        {children && <div className="flex items-center gap-5 text-xs">{children}</div>}
      </div>
    </div>
  );
}

/* Summary badge for chart headers */
function SummaryBadge({ label, value, valueClass = 'text-gray-800' }) {
  return (
    <span className="text-gray-400 font-medium">
      {label}: <b className={`${valueClass} font-semibold`}>{value}</b>
    </span>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-07' });

  useEffect(() => {
    setLoading(true);
    fetchDashboard(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  if (loading) return <Loading />;
  if (!data) return <div className="text-center py-16 text-gray-400 font-medium">No data available</div>;

  const cm = data.call_metrics || {};
  const targetPct = data.total_target ? Math.min(100, (data.total_sales / data.total_target * 100)).toFixed(1) : 0;

  // Daily charts (API key: weekly_sales for backward compat)
  const salesChart = (data.weekly_sales || []).map(r => ({
    date: fmtDate(r.date),
    sales: Number(r.sales || 0),
  }));
  const collChart = (data.weekly_collection || []).map(r => ({
    date: fmtDate(r.date),
    collection: Number(r.collection || 0),
  }));

  // Weekly aggregated charts
  const weeklySalesChart = (data.week_chart_sales || []).map(r => ({
    week: r.week_label,
    sales: Number(r.sales || 0),
  }));
  const weeklyCollChart = (data.week_chart_collection || []).map(r => ({
    week: r.week_label,
    collection: Number(r.collection || 0),
  }));

  // Route data
  const routeSales = (data.route_wise_sales_vs_target || []).map(r => ({
    route: r.route_name || r.route_code,
    sales: Number(r.sales || 0),
    collection: Number(r.collection || 0),
    target: Number(r.target || 0),
  }));
  const routeVisits = (data.route_wise_visits || []).map(r => ({
    route: r.route_name || r.route_code,
    actual: Number(r.actual || 0),
    scheduled: Number(r.scheduled || 0),
    selling: Number(r.selling || 0),
    pending: Math.max(0, Number(r.scheduled || 0) - Number(r.actual || 0)),
  }));

  // Route summary KPIs
  const totalRouteSales = routeSales.reduce((s, r) => s + r.sales, 0);
  const totalRouteCollection = routeSales.reduce((s, r) => s + r.collection, 0);
  const totalRouteTarget = routeSales.reduce((s, r) => s + r.target, 0);
  const totalRouteVisitsActual = routeVisits.reduce((s, r) => s + r.actual, 0);
  const totalRouteVisitsScheduled = routeVisits.reduce((s, r) => s + r.scheduled, 0);
  const totalRouteVisitsSelling = routeVisits.reduce((s, r) => s + r.selling, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Dashboard</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Sales, collection & call performance overview</p>
        </div>
      </div>

      {/* Filters */}
      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'brand']} />

      {/* ─── Primary KPI Row ─── */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          title="Total Sales"
          value={aed(data.total_sales)}
          color="blue"
          icon={Banknote}
          variant="solid"
        />
        <KpiCard
          title="Total Collection"
          value={aed(data.total_collection)}
          color="green"
          icon={Wallet}
          variant="solid"
        />

        {/* Target vs Achievement Card */}
        <div className="kpi-card bg-white rounded-2xl shadow-sm border border-gray-100/80 p-5 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-amber-500 opacity-40 rounded-t-2xl" />
          <div className="flex items-center gap-3 mb-3.5">
            <div className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center bg-amber-50 text-amber-600 shadow-sm">
              <Target className="w-5 h-5" strokeWidth={1.75} />
            </div>
            <div className="text-[11px] font-semibold text-amber-500/80 uppercase tracking-wider">
              Target vs Achievement
            </div>
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-gray-400 font-medium">Target</span>
              <span className="font-bold text-gray-700 tabular-nums">{aed(data.total_target)}</span>
            </div>
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-gray-400 font-medium">Achieved</span>
              <span className="font-bold text-emerald-600 tabular-nums">{aed(data.total_sales)}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2 mt-1 overflow-hidden">
              <div
                className={`h-2 rounded-full animate-progress ${Number(targetPct) >= 100 ? 'bg-emerald-500' : Number(targetPct) >= 75 ? 'bg-amber-500' : 'bg-red-500'}`}
                style={{ width: `${Math.min(100, targetPct)}%` }}
              />
            </div>
            <div className="text-right text-[13px] font-bold text-gray-700 tabular-nums">{targetPct}%</div>
          </div>
        </div>

        {/* Calls / Coverage / Productivity */}
        <div className="kpi-card bg-white rounded-2xl shadow-sm border border-gray-100/80 p-5 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-violet-500 opacity-40 rounded-t-2xl" />
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center bg-violet-50 text-violet-600 shadow-sm">
              <Phone className="w-5 h-5" strokeWidth={1.75} />
            </div>
            <div className="text-[11px] font-semibold text-violet-500/80 uppercase tracking-wider">
              Calls & Coverage
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-[13px]">
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Scheduled</span>
              <span className="font-bold text-gray-700 tabular-nums">{fmtNum(cm.scheduled_calls)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Actual</span>
              <span className="font-bold text-gray-700 tabular-nums">{fmtNum(cm.actual_calls)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Planned</span>
              <span className="font-bold text-gray-700 tabular-nums">{fmtNum(cm.planned_calls)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Unplanned</span>
              <span className="font-bold text-gray-700 tabular-nums">{fmtNum(cm.unplanned_calls)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Selling</span>
              <span className="font-bold text-emerald-600 tabular-nums">{fmtNum(cm.selling_calls)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400 font-medium">Strike Rate</span>
              <span className="font-bold text-amber-600 tabular-nums">{cm.strike_rate?.toFixed(1)}%</span>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100/80 flex items-center justify-between">
            <span className="text-[13px] text-gray-400 font-medium">Coverage</span>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[13px] font-bold bg-violet-50 text-violet-700 border border-violet-100/80">
              {cm.coverage_pct?.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* ─── Week-wise Sales & Collection ─── */}
      {(weeklySalesChart.length > 0 || weeklyCollChart.length > 0) && (
        <div className="chart-container">
          <SectionHeader title="Week-wise Sales & Collection" />
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={(() => {
                const weeks = {};
                weeklySalesChart.forEach(r => { weeks[r.week] = { ...weeks[r.week], week: r.week, sales: r.sales }; });
                weeklyCollChart.forEach(r => { weeks[r.week] = { ...weeks[r.week], week: r.week, collection: r.collection }; });
                return Object.values(weeks).sort((a, b) => a.week.localeCompare(b.week));
              })()} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={{ stroke: '#f3f4f6' }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => aed(v)} contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(99, 102, 241, 0.04)' }} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', color: '#6b7280' }} />
                <Bar dataKey="sales" fill={COLORS.sales} name="Sales" radius={[6, 6, 0, 0]} />
                <Bar dataKey="collection" fill={COLORS.collection} name="Collection" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ─── Daily Charts (Side by Side) ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="chart-container">
          <SectionHeader title="Daily Sales" />
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={salesChart} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={{ stroke: '#f3f4f6' }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => aed(v)} contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(99, 102, 241, 0.04)' }} />
                <Bar dataKey="sales" fill={COLORS.sales} name="Sales" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-container">
          <SectionHeader title="Daily Collection" />
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={collChart} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={{ stroke: '#f3f4f6' }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => aed(v)} contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(16, 185, 129, 0.04)' }} />
                <Bar dataKey="collection" fill={COLORS.collection} name="Collection" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ─── Route Wise Sales vs Target vs Collection ─── */}
      {routeSales.length > 0 && (
        <div className="chart-container">
          <SectionHeader title="Route Wise Sales vs Target vs Collection">
            <SummaryBadge label="Total Sales" value={aed(totalRouteSales)} />
            <SummaryBadge label="Target" value={aed(totalRouteTarget)} />
            <SummaryBadge label="Collection" value={aed(totalRouteCollection)} />
            {totalRouteTarget > 0 && (
              <SummaryBadge
                label="Achievement"
                value={`${(totalRouteSales / totalRouteTarget * 100).toFixed(1)}%`}
                valueClass={totalRouteSales >= totalRouteTarget ? 'text-emerald-600' : 'text-amber-600'}
              />
            )}
          </SectionHeader>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, routeSales.length * 100) }}>
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={routeSales} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
                  <XAxis dataKey="route" tick={{ fontSize: 11, fill: '#6b7280', angle: -35, textAnchor: 'end' }} height={70} axisLine={{ stroke: '#f3f4f6' }} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickFormatter={yAxisFmt} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v) => aed(v)} contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(99, 102, 241, 0.04)' }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', color: '#6b7280' }} />
                  <Bar dataKey="target" fill={COLORS.target} name="Target" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="sales" fill={COLORS.salesLight} name="Sales" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="collection" fill={COLORS.collection} name="Collection" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* ─── Route Wise Visits ─── */}
      {routeVisits.length > 0 && (
        <div className="chart-container">
          <SectionHeader title="Route Wise Visits">
            <SummaryBadge label="Scheduled" value={fmtNum(totalRouteVisitsScheduled)} />
            <SummaryBadge label="Actual" value={fmtNum(totalRouteVisitsActual)} />
            <SummaryBadge label="Selling" value={fmtNum(totalRouteVisitsSelling)} valueClass="text-emerald-600" />
            {totalRouteVisitsScheduled > 0 && (
              <SummaryBadge
                label="Coverage"
                value={`${Math.min(100, (totalRouteVisitsActual / totalRouteVisitsScheduled * 100)).toFixed(1)}%`}
                valueClass={totalRouteVisitsActual >= totalRouteVisitsScheduled ? 'text-emerald-600' : 'text-amber-600'}
              />
            )}
          </SectionHeader>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, routeVisits.length * 80) }}>
              <ResponsiveContainer width="100%" height={340}>
                <BarChart data={routeVisits} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
                  <XAxis dataKey="route" tick={{ fontSize: 11, fill: '#6b7280', angle: -35, textAnchor: 'end' }} height={60} axisLine={{ stroke: '#f3f4f6' }} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(16, 185, 129, 0.04)' }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', color: '#6b7280' }} />
                  <Bar dataKey="actual" fill={COLORS.visited} name="Visited" stackId="a" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="pending" fill={COLORS.pending} name="Pending" stackId="a" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
