import { useState, useEffect } from 'react';
import { fetchTargetAchievement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Target, TrendingUp, Percent, BarChart3, List } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, LabelList,
} from 'recharts';

const aed = (v) => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const pct = (v) => v != null ? `${Number(v).toFixed(1)}%` : '-';
const fmt = (v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v;

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white/95 backdrop-blur-xl rounded-xl border border-gray-200/50 px-4 py-3"
      style={{ boxShadow: '0 20px 48px -12px rgba(0,0,0,0.18)' }}>
      <p className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2 pb-2 border-b border-gray-100">{label}</p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2.5 py-[3px]">
          <span className="w-3 h-3 rounded-[4px] flex-shrink-0" style={{ background: entry.color }} />
          <span className="text-[12px] text-gray-500 font-medium">{entry.name}</span>
          <span className="text-[13px] font-bold text-gray-900 ml-auto pl-5 tabular-nums">{aed(entry.value)}</span>
        </div>
      ))}
      {payload.length === 2 && payload[0].value > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100 flex items-center justify-between">
          <span className="text-[11px] text-gray-400 font-medium">Achievement</span>
          <span className={`text-[12px] font-bold tabular-nums ${(payload[1].value/payload[0].value*100) >= 100 ? 'text-emerald-600' : (payload[1].value/payload[0].value*100) >= 75 ? 'text-amber-600' : 'text-rose-600'}`}>
            {(payload[1].value / payload[0].value * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  );
}

export default function TargetAchievement() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    return { month: now.getMonth() + 1, year: now.getFullYear() };
  });
  const [view, setView] = useState('chart'); // 'chart' or 'list'

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchTargetAchievement(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
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

      {loading ? <Loading /> : !data ? (
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
        <div className="chart-container">
          <div className="chart-header">
            <div className="flex items-center gap-3 pb-4 border-b border-gray-100/60">
              <div className="w-1 h-8 rounded-full bg-gradient-to-b from-orange-500 to-emerald-500" />
              <div>
                <h2 className="text-[14px] font-bold text-gray-800 tracking-tight">Route Wise Target vs Achievement</h2>
                <p className="text-[11px] text-gray-400 mt-0.5 font-medium">Target and achieved sales per route</p>
              </div>
            </div>
          </div>
          <div className="chart-body overflow-x-auto">
            <div style={{ minWidth: Math.max(600, routeData.length * 90) }}>
              <ResponsiveContainer width="100%" height={420}>
                <BarChart data={routeData} barGap={3} barCategoryGap="18%">
                  <defs>
                    <linearGradient id="gTarget" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#fb923c" />
                      <stop offset="100%" stopColor="#ea580c" />
                    </linearGradient>
                    <linearGradient id="gAchieved" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#34d399" />
                      <stop offset="100%" stopColor="#059669" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="route_name" tick={{ fontSize: 10, fill: '#64748b' }} angle={-35} textAnchor="end" height={75} axisLine={false} tickLine={false} interval={0} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={fmt} axisLine={false} tickLine={false} width={50} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(234,88,12,0.04)', radius: 4 }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', color: '#64748b', paddingTop: '12px' }} />
                  <Bar dataKey="target" fill="url(#gTarget)" name="Target" radius={[5, 5, 0, 0]}>
                    <LabelList dataKey="target" position="top" formatter={fmt} style={{ fontSize: 9, fill: '#ea580c', fontWeight: 700 }} />
                  </Bar>
                  <Bar dataKey="achieved" fill="url(#gAchieved)" name="Achieved" radius={[5, 5, 0, 0]}>
                    <LabelList dataKey="achieved" position="top" formatter={fmt} style={{ fontSize: 9, fill: '#059669', fontWeight: 700 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
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
