import { useState, useEffect, useRef } from 'react';
import { fetchTargetAchievement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Target, TrendingUp, Percent, BarChart3, List } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';

const aed = (v) => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const pct = (v) => v != null ? `${Number(v).toFixed(1)}%` : '-';

const chartTooltipStyle = {
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
};

export default function TargetAchievement() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    return { month: now.getMonth() + 1, year: now.getFullYear() };
  });
  const [view, setView] = useState('chart'); // 'chart' or 'list'

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchTargetAchievement(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const routeData = data?.route_data || [];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Target vs Achievement</h1>
        <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Route-wise target tracking and achievement analysis</p>
      </div>

      <FilterPanel
        filters={filters}
        onChange={setFilters}
        showFields={['month', 'year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']}
      />

      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (<>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard
          title="Total Target"
          value={aed(data.total_target)}
          color="blue"
          icon={Target}
          variant="solid"
        />
        <KpiCard
          title="Total Achieved"
          value={aed(data.total_achieved)}
          color="green"
          icon={TrendingUp}
          variant="solid"
        />
        <KpiCard
          title="Achievement %"
          value={pct(data.achieved_pct)}
          color="purple"
          icon={Percent}
          variant="solid"
        />
      </div>

      {/* Toggle */}
      <div className="inline-flex items-center bg-gray-100 rounded-xl p-1 gap-1">
        <button
          onClick={() => setView('chart')}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            view === 'chart'
              ? 'bg-white text-indigo-700 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          Chart View
        </button>
        <button
          onClick={() => setView('list')}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            view === 'list'
              ? 'bg-white text-indigo-700 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <List className="w-4 h-4" />
          List View
        </button>
      </div>

      {view === 'chart' ? (
        /* Bar Chart */
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Route Wise Target vs Achievement</h2>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={routeData} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="route_name"
                tick={{ fontSize: 11 }}
                angle={-30}
                textAnchor="end"
                height={70}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v}
              />
              <Tooltip formatter={(v) => aed(v)} contentStyle={chartTooltipStyle} />
              <Legend />
              <Bar dataKey="target" fill="#6ee7b7" name="Target" radius={[6, 6, 0, 0]} />
              <Bar dataKey="achieved" fill="#fcd34d" name="Achieved" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        /* List View as DataTable */
        <DataTable
          columns={[
            { key: 'route_name', label: 'Route' },
            { key: 'target', label: 'Target', format: 'currency' },
            { key: 'achieved', label: 'Achieved', format: 'currency' },
            {
              key: 'achieved_pct',
              label: 'Achievement %',
              format: 'percent',
              render: (val) => (
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                  val >= 100 ? 'bg-emerald-50 text-emerald-700' :
                  val >= 75  ? 'bg-amber-50 text-amber-700' :
                  'bg-rose-50 text-rose-700'
                }`}>
                  {pct(val)}
                </span>
              ),
            },
          ]}
          data={routeData}
          exportName="target-achievement"
        />
      )}

      </>)}
    </div>
  );
}
