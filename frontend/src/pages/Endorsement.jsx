import { useState, useEffect, useRef } from 'react';
import { fetchEndorsement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Users, CheckCircle2, Target, TrendingUp, TrendingDown } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function Endorsement() {
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

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchEndorsement(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const h = data?.header || {};
  const customers = data?.customers || [];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Endorsement Report</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Customer visit tracking and journey plan compliance</p>
        </div>
        {customers.length > 0 && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-600">
            <Users className="w-3.5 h-3.5" />
            {customers.length} visits
          </span>
        )}
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard title="Total Visits" value={h.total_visits ?? '-'} color="blue" icon={Users} variant="solid" />
            <KpiCard title="Planned (JP)" value={h.planned_visits ?? '-'} color="indigo" icon={CheckCircle2} variant="solid"
              subtitle={h.scheduled_calls ? `${h.coverage_pct}% coverage` : undefined} />
            <KpiCard title="Unplanned" value={h.unplanned_visits ?? '-'} color="yellow" icon={Users} variant="solid" subtitle="Outside JP" />
            <KpiCard title="Productive" value={h.productive_visits ?? '-'} color="green" icon={TrendingUp} variant="solid"
              subtitle={h.total_visits ? `${((h.productive_visits / h.total_visits) * 100).toFixed(1)}% strike rate` : undefined} />
            <KpiCard title="Non-Productive" value={h.non_productive_visits ?? '-'} color="red" icon={TrendingDown} variant="solid"
              subtitle={h.total_visits ? `${((h.non_productive_visits / h.total_visits) * 100).toFixed(1)}% of visits` : undefined} />
            <KpiCard title="Coverage %" value={h.coverage_pct != null ? `${h.coverage_pct}%` : '-'} color="purple" icon={Target} variant="solid"
              subtitle={h.scheduled_calls ? `${h.planned_visits}/${h.scheduled_calls}` : undefined} />
          </div>

          {/* Customer Detail Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Customer Visits</h2>
            <DataTable
              disableSort
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'customer_code', label: 'Code' },
                { key: 'customer_name', label: 'Customer' },
                { key: 'channel_name', label: 'Channel' },
                {
                  key: 'is_planned', label: 'Planned',
                  render: (v) => {
                    const planned = v === true || v === 'Yes';
                    return (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold ${
                        planned ? 'bg-indigo-50 text-indigo-600' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {planned ? 'JP' : 'UJP'}
                      </span>
                    );
                  }
                },
                { key: 'check_in', label: 'Check In', render: (v) => v || '-' },
                { key: 'check_out', label: 'Check Out', render: (v) => v || '-' },
                {
                  key: 'check_in', label: 'Time Spent',
                  render: (v, row) => {
                    if (!row.check_in || !row.check_out) return '-';
                    const toSecs = (t) => { const [h, m, s] = t.split(':').map(Number); return h * 3600 + m * 60 + (s || 0); };
                    const diff = toSecs(row.check_out) - toSecs(row.check_in);
                    if (diff <= 0) return '-';
                    const mins = Math.floor(diff / 60), secs = diff % 60;
                    return secs > 0 ? `${mins}m ${secs}s` : `${mins} mins`;
                  }
                },
                {
                  key: 'is_productive', label: 'Productive',
                  render: (v) => {
                    const productive = v === true || v === 'Yes';
                    return (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold ${
                        productive ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-500'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${productive ? 'bg-emerald-500' : 'bg-rose-400'}`} />
                        {productive ? 'Yes' : 'No'}
                      </span>
                    );
                  }
                },
                { key: 'total_value', label: 'Sales Value', format: 'currency' },
                { key: 'total_returns', label: 'Returns', format: 'currency' },
              ]}
              data={customers.map(c => ({
                ...c,
                is_planned: c.is_planned ? 'Yes' : 'No',
                is_productive: c.is_productive ? 'Yes' : 'No',
              }))}
              exportName="endorsement-report"
            />
          </div>
        </>
      )}
    </div>
  );
}
