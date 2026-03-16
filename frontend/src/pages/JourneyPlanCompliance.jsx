import { useState, useEffect } from 'react';
import { fetchJourneyPlanCompliance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { CalendarCheck, MapPin, Navigation, Target, ChevronRight } from 'lucide-react';

export default function JourneyPlanCompliance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });
  const [expandedDate, setExpandedDate] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetchJourneyPlanCompliance(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const summary = data?.summary || [];
  const drillDown = data?.drill_down || [];

  const drillForDate = expandedDate
    ? drillDown.filter(d => d.date === expandedDate)
    : [];

  // Aggregate KPIs from summary
  const totScheduled = summary.reduce((s, r) => s + (Number(r.scheduled_calls) || 0), 0);
  const totPlanned = summary.reduce((s, r) => s + (Number(r.planned_calls) || 0), 0);
  const totUnplanned = summary.reduce((s, r) => s + (Number(r.unplanned) || 0), 0);
  const avgCoverage = summary.length
    ? (summary.reduce((s, r) => s + (Number(r.coverage_pct) || 0), 0) / summary.length).toFixed(1)
    : '-';

  const coverageColor = (pct) => {
    if (pct >= 90) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200';
    if (pct >= 70) return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200';
    return 'bg-rose-50 text-rose-700 ring-1 ring-rose-200';
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Journey Plan Compliance</h1>
        <p className="text-sm text-gray-500 mt-1">Daily scheduled vs actual visits with planned/unplanned breakdown and coverage</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['user_code', 'date_from', 'date_to', 'sales_org']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Scheduled" value={totScheduled.toLocaleString()} icon={CalendarCheck} color="blue" variant="light" />
            <KpiCard title="Total Planned" value={totPlanned.toLocaleString()} icon={MapPin} color="green" variant="light" />
            <KpiCard title="Total Unplanned" value={totUnplanned.toLocaleString()} icon={Navigation} color="yellow" variant="light" />
            <KpiCard title="Avg Coverage %" value={avgCoverage !== '-' ? `${avgCoverage}%` : '-'} icon={Target}
              color={Number(avgCoverage) >= 90 ? 'green' : Number(avgCoverage) >= 70 ? 'yellow' : 'red'} variant="light" />
          </div>

          {/* Daily Summary Table */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Daily Summary</h2>
            <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-xs text-gray-400">Click a row to view salesman-level details</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-100">
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-8"></th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider"># Users</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Scheduled</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Planned</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Unplanned</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Coverage %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {summary.map((row, i) => (
                      <tr key={i}
                        onClick={() => setExpandedDate(expandedDate === row.date ? null : row.date)}
                        className={`cursor-pointer transition-colors hover:bg-indigo-50/50 ${
                          expandedDate === row.date ? 'bg-indigo-50/70' : i % 2 === 0 ? '' : 'bg-gray-50/50'
                        }`}>
                        <td className="px-4 py-2.5">
                          <ChevronRight className={`w-4 h-4 text-gray-400 transition-transform ${expandedDate === row.date ? 'rotate-90' : ''}`} />
                        </td>
                        <td className="px-4 py-2.5 font-medium text-gray-800">{row.date}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{row.num_users ?? '-'}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{row.scheduled_calls ?? '-'}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{row.planned_calls ?? '-'}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{row.unplanned ?? '-'}</td>
                        <td className="px-4 py-2.5 text-right">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${coverageColor(row.coverage_pct)}`}>
                            {row.coverage_pct != null ? `${Number(row.coverage_pct).toFixed(1)}%` : '-'}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {summary.length === 0 && (
                      <tr><td colSpan={7} className="px-4 py-12 text-center text-gray-400">No data available</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Drill-down for selected date */}
          {expandedDate && (
            <div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Salesman Detail &mdash; {expandedDate}
              </h2>
              <DataTable
                columns={[
                  { key: 'date', label: 'Date' },
                  { key: 'user_code', label: 'User Code' },
                  { key: 'user_name', label: 'Salesman' },
                  { key: 'scheduled', label: 'Scheduled', format: 'number' },
                  { key: 'planned', label: 'Planned', format: 'number' },
                  { key: 'unplanned', label: 'Unplanned', format: 'number' },
                  { key: 'coverage_pct', label: 'Coverage %', format: 'percent' },
                ]}
                data={drillForDate}
                exportName={`jp-compliance-${expandedDate}`}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
