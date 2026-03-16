import { useState, useEffect } from 'react';
import { fetchWeeklySalesReturns } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Banknote, Percent } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function WeeklySalesReturns() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-01-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchWeeklySalesReturns(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const weekly = data?.weekly_data || [];
  const totals = data?.totals || {};

  const chartData = weekly.map(w => ({
    ...w,
    label: `W${w.week_number}`,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Weekly Sales & Returns</h1>
        <p className="text-sm text-gray-500 mt-1">Compare weekly sales performance against returns</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['sales_org', 'user_code', 'date_from', 'date_to', 'route']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Totals Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Sales" value={aed(totals.total_sales)} color="blue" icon={TrendingUp} variant="solid" />
            <KpiCard title="Total Returns" value={aed(totals.total_returns)} color="red" icon={TrendingDown} variant="solid" />
            <KpiCard title="Net Amount" value={aed(totals.net_amount)} color="green" icon={Banknote} variant="solid" />
            <KpiCard title="Return %" value={totals.return_pct != null ? `${Number(totals.return_pct).toFixed(1)}%` : '-'} color="yellow" icon={Percent} variant="light" />
          </div>

          {/* Bar Chart */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales vs Returns by Week</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} />
                <YAxis tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} />
                <Tooltip
                  formatter={(value) => aed(value)}
                  labelFormatter={(l) => `Week ${l.replace('W', '')}`}
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                />
                <Legend wrapperStyle={{ paddingTop: '16px' }} />
                <Bar dataKey="sales_amount" name="Sales" fill="#818cf8" radius={[6, 6, 0, 0]} />
                <Bar dataKey="return_amount" name="Returns" fill="#fca5a5" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Weekly Data Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Weekly Breakdown</h2>
            <DataTable
              columns={[
                { key: 'year', label: 'Year' },
                { key: 'week_number', label: 'Week' },
                { key: 'week_start', label: 'Start Date' },
                { key: 'week_end', label: 'End Date' },
                { key: 'sales_amount', label: 'Sales', format: 'currency' },
                { key: 'return_amount', label: 'Returns', format: 'currency' },
                { key: 'net_amount', label: 'Net', format: 'currency' },
                { key: 'return_pct', label: 'Return %', format: 'percent' },
              ]}
              data={weekly}
              exportName="weekly-sales-returns"
            />
          </div>
        </>
      )}
    </div>
  );
}
