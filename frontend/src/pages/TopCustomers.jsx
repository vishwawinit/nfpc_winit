import { useState, useEffect, useRef } from 'react';
import { fetchTopCustomers } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import { ArrowUpRight, ArrowDownRight, Users, TrendingUp, Banknote } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';

const aed = (v) => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const units = (v) => `${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })} Units`;

function GrowthBadge({ value }) {
  if (value == null) return null;
  const positive = value >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap ${
      positive ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'
    }`}>
      {positive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
      {positive ? '+' : ''}{value.toFixed(1)}%
    </span>
  );
}

export default function TopCustomers() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    return { month: now.getMonth() + 1, year: now.getFullYear() };
  });
  const [view, setView] = useState('value'); // 'value' | 'units'

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchTopCustomers(filters)
      .then(res => { if (!cancelled) { setData(res.data || res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  
  if (!data || data.length === 0)
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Top 20 Customers</h1>
          <p className="text-sm text-gray-500 mt-1">Highest performing customers by sales value and quantity</p>
        </div>
        <FilterPanel filters={filters} onChange={setFilters}
          showFields={['month', 'year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel']} />
        <div className="text-center py-16 text-gray-400">No data available</div>
      </div>
    );

  const customers = (Array.isArray(data) ? data : []).slice(0, 20);
  const dataKey = view === 'value' ? 'total_sales' : 'total_qty';
  const formatter = view === 'value' ? aed : units;

  const totalSales = customers.reduce((s, c) => s + (Number(c.total_sales) || 0), 0);
  const totalQty = customers.reduce((s, c) => s + (Number(c.total_qty) || 0), 0);
  const avgGrowth = customers.filter(c => c.growth_pct != null).reduce((s, c, _, a) => s + c.growth_pct / a.length, 0);

  const barColors = ['#4f46e5', '#4f46e5', '#4f46e5', '#6366f1', '#6366f1', '#6366f1',
    '#818cf8', '#818cf8', '#818cf8', '#818cf8', '#a5b4fc', '#a5b4fc',
    '#a5b4fc', '#a5b4fc', '#a5b4fc', '#a5b4fc', '#c7d2fe', '#c7d2fe', '#c7d2fe', '#c7d2fe'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Top 20 Customers</h1>
          <p className="text-sm text-gray-500 mt-1">Highest performing customers by sales value and quantity</p>
        </div>
        <div className="bg-gray-100 p-1 rounded-xl flex">
          <button
            onClick={() => setView('value')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
              view === 'value' ? 'bg-white shadow-sm text-indigo-600' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            AED (Value)
          </button>
          <button
            onClick={() => setView('units')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
              view === 'units' ? 'bg-white shadow-sm text-indigo-600' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Units
          </button>
        </div>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['month', 'year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel']} />

      {/* KPI Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard title="Total Sales" value={aed(totalSales)} icon={Banknote} color="blue" variant="light" />
        <KpiCard title="Total Quantity" value={totalQty.toLocaleString()} icon={Users} color="purple" variant="light" />
        <KpiCard title="Avg Growth" value={`${avgGrowth >= 0 ? '+' : ''}${avgGrowth.toFixed(1)}%`} icon={TrendingUp} color={avgGrowth >= 0 ? 'green' : 'red'} variant="light" />
      </div>

      {/* Bar Chart */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
          {view === 'value' ? 'Sales Value' : 'Sales Quantity'} by Customer
        </h2>
        <ResponsiveContainer width="100%" height={Math.max(customers.length * 40, 300)}>
          <BarChart data={customers} layout="vertical" margin={{ left: 10, right: 90, top: 5, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
            <XAxis type="number" tickFormatter={(v) => view === 'value' ? `${(v / 1000).toFixed(0)}K` : v.toLocaleString()} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
            <YAxis dataKey="customer_name" type="category" tick={{ fontSize: 11, fill: '#475569' }} width={160} axisLine={false} tickLine={false} />
            <Tooltip
              formatter={(v) => [formatter(v), view === 'value' ? 'Sales' : 'Quantity']}
              contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            />
            <Bar dataKey={dataKey} name={view === 'value' ? 'Sales' : 'Quantity'} radius={[0, 6, 6, 0]}
              label={({ x, y, width, height, index }) => {
                const entry = customers[index];
                if (entry?.growth_pct == null) return null;
                const positive = entry.growth_pct >= 0;
                return (
                  <text x={x + width + 8} y={y + height / 2 + 4} fontSize={11} fontWeight="600"
                    fill={positive ? '#059669' : '#e11d48'}>
                    {positive ? '+' : ''}{entry.growth_pct.toFixed(1)}%
                  </text>
                );
              }}
            >
              {customers.map((_, i) => (
                <Cell key={i} fill={barColors[i] || '#c7d2fe'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Customer Details</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-100">
                <th className="text-left px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">#</th>
                <th className="text-left px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Customer</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Sales (AED)</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Qty</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Growth</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c, i) => (
                <tr key={c.customer_code || i} className="border-b border-gray-50 last:border-0 hover:bg-indigo-50/30 transition-colors">
                  <td className="px-6 py-3.5 text-gray-400 font-medium tabular-nums">{i + 1}</td>
                  <td className="px-6 py-3.5 font-medium text-gray-900">{c.customer_name}</td>
                  <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{aed(c.total_sales)}</td>
                  <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{Number(c.total_qty).toLocaleString()}</td>
                  <td className="px-6 py-3.5 text-right"><GrowthBadge value={c.growth_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
