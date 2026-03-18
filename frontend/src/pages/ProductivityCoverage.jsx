import { useState, useEffect, useRef } from 'react';
import { fetchProductivityCoverage } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { CalendarCheck, Users, Target, TrendingUp, MapPin, Navigation, Zap } from 'lucide-react';

export default function ProductivityCoverage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [tab, setTab] = useState('coverage');
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  });

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchProductivityCoverage(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const summary = data?.summary || {};
  const users = data?.users || [];

  const tabs = [
    { key: 'coverage', label: 'Coverage', icon: MapPin },
    { key: 'productivity', label: 'Productivity', icon: Zap },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Productivity & Coverage</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Scheduled vs actual visits, productive calls and coverage metrics</p>
        </div>
      </div>

      {/* Filters — always mounted */}
      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {/* Refreshing indicator */}
      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {/* Data area */}
      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (
        <>
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
            <KpiCard title="Total Scheduled" value={summary.total_scheduled?.toLocaleString() ?? '-'} icon={CalendarCheck} color="blue" variant="light" />
            <KpiCard title="Total Actual" value={summary.total_actual?.toLocaleString() ?? '-'} icon={Users} color="green" variant="light" />
            <KpiCard title="Planned" value={summary.planned?.toLocaleString() ?? '-'} icon={MapPin} color="blue" variant="light" />
            <KpiCard title="Unplanned" value={summary.unplanned?.toLocaleString() ?? '-'} icon={Navigation} color="yellow" variant="light" />
            <KpiCard title="Productive (Planned)" value={summary.productive_planned?.toLocaleString() ?? '-'} icon={Target} color="green" variant="light" />
            <KpiCard title="Productive (Unplanned)" value={summary.productive_unplanned?.toLocaleString() ?? '-'} icon={TrendingUp} color="purple" variant="light" />
            <KpiCard title="Coverage %" value={summary.coverage_pct != null ? `${Number(summary.coverage_pct).toFixed(1)}%` : '-'} icon={Zap}
              color={summary.coverage_pct >= 90 ? 'green' : summary.coverage_pct >= 70 ? 'yellow' : 'red'} variant="light" />
          </div>

          {/* Tab Toggle */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-1.5 inline-flex gap-1">
            {tabs.map(t => {
              const Icon = t.icon;
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                    active
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Per-User Table */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
              {tab === 'coverage' ? 'Coverage by Salesman' : 'Productivity by Salesman'}
            </h2>

            {tab === 'coverage' ? (
              <DataTable
                columns={[
                  { key: 'user_code', label: 'User Code' },
                  { key: 'user_name', label: 'Salesman' },
                  { key: 'scheduled', label: 'Scheduled', format: 'number' },
                  { key: 'actual', label: 'Actual', format: 'number' },
                  { key: 'coverage_pct', label: 'Coverage %', format: 'percent' },
                ]}
                data={users}
                exportName="coverage-by-user"
              />
            ) : (
              <DataTable
                columns={[
                  { key: 'user_code', label: 'User Code' },
                  { key: 'user_name', label: 'Salesman' },
                  { key: 'actual', label: 'Actual Calls', format: 'number' },
                  { key: 'productive', label: 'Productive Calls', format: 'number' },
                  { key: 'coverage_pct', label: 'Coverage %', format: 'percent' },
                ]}
                data={users}
                exportName="productivity-by-user"
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}
