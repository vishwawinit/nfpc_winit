import { useState, useEffect } from 'react';
import { fetchSalesmanJourney } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  MapPin, Clock, Navigation, UserCircle, AlertCircle,
  Play, Square, Route, Map
} from 'lucide-react';

export default function SalesmanJourney() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    if (!filters.user_code) { setLoading(false); return; }
    setLoading(true);
    fetchSalesmanJourney(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const visits = data?.visits || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Salesman Journey</h1>
        <p className="text-sm text-gray-500 mt-1">Track daily route and customer visit timeline</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['user_code', 'date_from', 'date_to']} />

      {!filters.user_code ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
          <div className="w-16 h-16 rounded-2xl bg-amber-50 flex items-center justify-center mx-auto mb-4">
            <UserCircle className="w-8 h-8 text-amber-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-700 mb-1">Select a Salesman</h3>
          <p className="text-sm text-gray-400 max-w-sm mx-auto">
            Choose a salesman from the filters above to view their journey details and customer visit timeline.
          </p>
        </div>
      ) : loading ? <Loading /> : !data ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Map className="w-7 h-7 text-gray-300" />
          </div>
          <p className="text-gray-400 font-medium">No data available</p>
          <p className="text-gray-300 text-sm mt-1">Adjust your filters and try again</p>
        </div>
      ) : (
        <>
          {/* Journey Summary KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard
              title="Journey Start"
              value={data.journey_start || '-'}
              color="green"
              icon={Play}
              variant="light"
            />
            <KpiCard
              title="Journey End"
              value={data.journey_end || '-'}
              color="red"
              icon={Square}
              variant="light"
            />
            <KpiCard
              title="Total Stops"
              value={visits.length}
              color="blue"
              icon={MapPin}
              variant="light"
            />
          </div>

          {/* Visit Timeline */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="p-6 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                  <Route className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Visit Timeline</h2>
                  <p className="text-xs text-gray-400 mt-0.5">{visits.length} stop{visits.length !== 1 ? 's' : ''} recorded</p>
                </div>
              </div>
            </div>
            <div className="p-6">
              {visits.length === 0 ? (
                <div className="text-center py-12">
                  <div className="w-14 h-14 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3">
                    <MapPin className="w-6 h-6 text-gray-300" />
                  </div>
                  <p className="text-gray-400 font-medium">No visits recorded</p>
                </div>
              ) : (
                <div className="relative">
                  {/* Timeline line */}
                  <div className="absolute left-[1.125rem] top-4 bottom-4 w-0.5 bg-gradient-to-b from-blue-400 via-blue-200 to-blue-100 rounded-full"></div>

                  <div className="space-y-3">
                    {visits.map((v, i) => (
                      <div key={i} className="relative flex items-start gap-4 group">
                        {/* Numbered circle */}
                        <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white flex items-center justify-center text-xs font-bold z-10 shadow-sm group-hover:shadow-md transition-shadow">
                          {v.sequence || i + 1}
                        </div>
                        {/* Visit card */}
                        <div className="flex-1 bg-white rounded-xl p-4 border border-gray-100 hover:border-gray-200 hover:shadow-sm transition-all">
                          <div className="flex flex-wrap justify-between items-start gap-3">
                            <div className="min-w-0">
                              <div className="font-semibold text-gray-800 truncate">{v.customer_name || '-'}</div>
                              <div className="flex items-center gap-2 mt-1">
                                <span className="text-xs text-gray-400 font-mono">{v.customer_code}</span>
                                <span className="text-gray-200">|</span>
                                <span className="text-xs text-gray-400">{v.date}</span>
                              </div>
                            </div>
                            <div className="text-right flex-shrink-0">
                              <div className="flex items-center gap-1.5 text-emerald-600">
                                <Clock className="w-3.5 h-3.5" />
                                <span className="text-sm font-semibold">{v.arrival_time || '-'}</span>
                              </div>
                              <div className="text-xs text-gray-400 mt-0.5">to {v.out_time || '-'}</div>
                            </div>
                          </div>
                          {(v.latitude || v.longitude) && (
                            <div className="flex items-center gap-1.5 mt-3 pt-3 border-t border-gray-50">
                              <Navigation className="w-3 h-3 text-gray-300" />
                              <span className="text-xs text-gray-400 font-mono">
                                {v.latitude}, {v.longitude}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
