import { useState, useEffect } from 'react';
import { fetchEndorsement } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { MapPin, User, LogIn, LogOut, Clock, Timer, Users, CheckCircle2 } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function Endorsement() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchEndorsement(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const h = data?.header || {};
  const customers = data?.customers || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Endorsement Report</h1>
          <p className="text-sm text-gray-500 mt-1">Customer visit tracking and journey plan compliance</p>
        </div>
        {customers.length > 0 && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-600">
            <Users className="w-3.5 h-3.5" />
            {customers.length} visits
          </span>
        )}
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['route', 'date_from', 'date_to', 'sales_org', 'user_code']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Route Header Info */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Route Information</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-5">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
                  <MapPin className="w-4 h-4 text-indigo-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Route</div>
                  <div className="font-semibold text-gray-800 text-sm">{h.route_name || '-'}</div>
                  <div className="text-xs text-gray-400">{h.route_code || ''}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4 text-violet-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Salesman</div>
                  <div className="font-semibold text-gray-800 text-sm">{h.user_name || '-'}</div>
                  <div className="text-xs text-gray-400">{h.user_code || ''}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center flex-shrink-0">
                  <LogOut className="w-4 h-4 text-emerald-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Depot Out</div>
                  <div className="font-semibold text-emerald-600 text-sm">{h.depot_out_time || '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-rose-50 flex items-center justify-center flex-shrink-0">
                  <LogIn className="w-4 h-4 text-rose-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Depot In</div>
                  <div className="font-semibold text-rose-600 text-sm">{h.depot_in_time || '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">
                  <Clock className="w-4 h-4 text-amber-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Total Driving</div>
                  <div className="font-semibold text-gray-800 text-sm">{h.total_driving_mins != null ? `${h.total_driving_mins} mins` : '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
                  <Timer className="w-4 h-4 text-blue-600" />
                </div>
                <div>
                  <div className="text-xs text-gray-400 font-medium">Avg Time/Visit</div>
                  <div className="font-semibold text-gray-800 text-sm">{h.avg_time_per_visit != null ? `${h.avg_time_per_visit} mins` : '-'}</div>
                </div>
              </div>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Visits" value={h.total_visits ?? '-'} color="blue" icon={Users} variant="solid" />
            <KpiCard title="Productive Visits" value={h.productive_visits ?? '-'} color="green" icon={CheckCircle2} variant="solid"
              subtitle={h.total_visits ? `${((h.productive_visits / h.total_visits) * 100).toFixed(1)}% strike rate` : undefined} />
            <KpiCard title="Depot Out" value={h.depot_out_time || '-'} color="purple" icon={LogOut} variant="solid" />
            <KpiCard title="Depot In" value={h.depot_in_time || '-'} color="yellow" icon={LogIn} variant="solid" />
          </div>

          {/* Customer Detail Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Customer Visits</h2>
            <DataTable
              columns={[
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
                { key: 'visit_type', label: 'Visit Type' },
                { key: 'arrival_time', label: 'Arrival' },
                { key: 'out_time', label: 'Departure' },
                { key: 'time_spent_mins', label: 'Time (mins)', format: 'number' },
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
