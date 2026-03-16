import { useState, useEffect } from 'react';
import { fetchEotStatus } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  ShoppingCart, Banknote, Wallet, CheckCircle2, XCircle,
  User, Truck, MapPin, Clock, Phone, BarChart3
} from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

const metricIcons = {
  planned: MapPin,
  visited: CheckCircle2,
  productive: BarChart3,
  unproductive: XCircle,
  missed: XCircle,
  total_calls: Phone,
  strike_rate: BarChart3,
};

export default function EotStatus() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchEotStatus(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const user = data?.user_info || {};
  const kpis = data?.kpis || {};
  const callMetrics = data?.call_metrics || {};
  const stops = data?.journey_stops || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">EOT Status</h1>
        <p className="text-sm text-gray-500 mt-1">End-of-trip summary and journey details</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['route', 'date_from', 'date_to', 'user_code', 'sales_org']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Truck className="w-7 h-7 text-gray-300" />
          </div>
          <p className="text-gray-400 font-medium">No data available</p>
          <p className="text-gray-300 text-sm mt-1">Adjust your filters and try again</p>
        </div>
      ) : (
        <>
          {/* User Info Header */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                <User className="w-5 h-5 text-blue-600" />
              </div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">User Information</h2>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-4">
              {Object.entries(user).map(([key, val]) => (
                <div key={key}>
                  <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
                    {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </div>
                  <div className="text-sm font-semibold text-gray-800">{val ?? '-'}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Route Plan & Compliance Badges */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Route Plan Followed</p>
                  <p className={`text-2xl font-bold ${data.route_plan_followed ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {data.route_plan_followed ? 'Yes' : 'No'}
                  </p>
                </div>
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
                  data.route_plan_followed ? 'bg-emerald-50' : 'bg-rose-50'
                }`}>
                  {data.route_plan_followed
                    ? <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                    : <XCircle className="w-6 h-6 text-rose-500" />
                  }
                </div>
              </div>
            </div>
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">All Customers Visited</p>
                  <p className={`text-2xl font-bold ${data.all_customers_visited ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {data.all_customers_visited ? 'Yes' : 'No'}
                  </p>
                </div>
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
                  data.all_customers_visited ? 'bg-emerald-50' : 'bg-rose-50'
                }`}>
                  {data.all_customers_visited
                    ? <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                    : <XCircle className="w-6 h-6 text-rose-500" />
                  }
                </div>
              </div>
            </div>
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard title="Order Count" value={kpis.order_count ?? '-'} color="blue" icon={ShoppingCart} />
            <KpiCard title="Sales Amount" value={aed(kpis.sales_amount)} color="green" icon={Banknote} />
            <KpiCard title="Collection Amount" value={aed(kpis.collection_amount)} color="purple" icon={Wallet} />
          </div>

          {/* Call Metrics */}
          {Object.keys(callMetrics).length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center">
                  <Phone className="w-5 h-5 text-violet-600" />
                </div>
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Call Metrics</h2>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
                {Object.entries(callMetrics).map(([key, val]) => {
                  const Icon = metricIcons[key.toLowerCase()] || BarChart3;
                  return (
                    <div key={key} className="text-center p-4 bg-gray-50/80 rounded-xl border border-gray-100 hover:border-gray-200 transition-colors">
                      <div className="w-8 h-8 rounded-lg bg-white shadow-sm flex items-center justify-center mx-auto mb-2">
                        <Icon className="w-4 h-4 text-gray-500" />
                      </div>
                      <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </div>
                      <div className="text-xl font-bold text-gray-800 mt-1">
                        {typeof val === 'number' ? val.toLocaleString() : val ?? '-'}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Journey Stops */}
          {stops.length > 0 && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="p-6 border-b border-gray-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                      <MapPin className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Journey Stops</h2>
                      <p className="text-xs text-gray-400 mt-0.5">{stops.length} stop{stops.length !== 1 ? 's' : ''} recorded</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="divide-y divide-gray-50">
                {stops.map((stop, i) => (
                  <div key={i} className="p-5 flex items-start gap-4 hover:bg-gray-50/50 transition-colors">
                    <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
                      {i + 1}
                    </div>
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-sm">
                      {Object.entries(stop).map(([key, val]) => (
                        <div key={key}>
                          <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                            {key.replace(/_/g, ' ')}
                          </span>
                          <div className="font-medium text-gray-700 mt-0.5">{val != null ? String(val) : '-'}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
