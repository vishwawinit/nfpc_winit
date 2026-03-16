import { useState, useEffect } from 'react';
import { fetchTopProducts } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import { ArrowUpRight, ArrowDownRight, Package, TrendingUp, Banknote } from 'lucide-react';
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

export default function TopProducts() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ month: 3, year: 2026 });
  const [view, setView] = useState('value'); // 'value' | 'units'

  useEffect(() => {
    setLoading(true);
    fetchTopProducts(filters)
      .then(res => setData(res.data || res))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filters]);

  if (loading) return <Loading />;
  if (!data || data.length === 0)
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Top 20 Products</h1>
          <p className="text-sm text-gray-500 mt-1">Best selling products ranked by revenue and volume</p>
        </div>
        <FilterPanel filters={filters} onChange={setFilters}
          showFields={['sales_org', 'user_code', 'month', 'year']} />
        <div className="text-center py-16 text-gray-400">No data available</div>
      </div>
    );

  const products = (Array.isArray(data) ? data : []).slice(0, 20);
  const dataKey = view === 'value' ? 'total_sales' : 'total_qty';
  const formatter = view === 'value' ? aed : units;

  const totalSales = products.reduce((s, p) => s + (Number(p.total_sales) || 0), 0);
  const totalQty = products.reduce((s, p) => s + (Number(p.total_qty) || 0), 0);
  const avgGrowth = products.filter(p => p.growth_pct != null).reduce((s, p, _, a) => s + p.growth_pct / a.length, 0);

  const barColors = ['#4f46e5', '#4f46e5', '#4f46e5', '#6366f1', '#6366f1', '#6366f1',
    '#818cf8', '#818cf8', '#818cf8', '#818cf8', '#a5b4fc', '#a5b4fc',
    '#a5b4fc', '#a5b4fc', '#a5b4fc', '#a5b4fc', '#c7d2fe', '#c7d2fe', '#c7d2fe', '#c7d2fe'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Top 20 Products</h1>
          <p className="text-sm text-gray-500 mt-1">Best selling products ranked by revenue and volume</p>
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
        showFields={['sales_org', 'user_code', 'month', 'year']} />

      {/* KPI Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard title="Total Sales" value={aed(totalSales)} icon={Banknote} color="blue" variant="light" />
        <KpiCard title="Total Quantity" value={totalQty.toLocaleString()} icon={Package} color="purple" variant="light" />
        <KpiCard title="Avg Growth" value={`${avgGrowth >= 0 ? '+' : ''}${avgGrowth.toFixed(1)}%`} icon={TrendingUp} color={avgGrowth >= 0 ? 'green' : 'red'} variant="light" />
      </div>

      {/* Bar Chart */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
          {view === 'value' ? 'Sales Value' : 'Sales Quantity'} by Product
        </h2>
        <ResponsiveContainer width="100%" height={Math.max(products.length * 40, 300)}>
          <BarChart data={products} layout="vertical" margin={{ left: 10, right: 90, top: 5, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
            <XAxis type="number" tickFormatter={(v) => view === 'value' ? `${(v / 1000).toFixed(0)}K` : v.toLocaleString()} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
            <YAxis dataKey="item_name" type="category" tick={{ fontSize: 11, fill: '#475569' }} width={180} axisLine={false} tickLine={false} />
            <Tooltip
              formatter={(v) => [formatter(v), view === 'value' ? 'Sales' : 'Quantity']}
              contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            />
            <Bar dataKey={dataKey} name={view === 'value' ? 'Sales' : 'Quantity'} radius={[0, 6, 6, 0]}
              label={({ x, y, width, height, index }) => {
                const entry = products[index];
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
              {products.map((_, i) => (
                <Cell key={i} fill={barColors[i] || '#c7d2fe'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Product Details</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-100">
                <th className="text-left px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">#</th>
                <th className="text-left px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Product</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Sales (AED)</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Qty</th>
                <th className="text-right px-6 py-3 font-semibold text-gray-500 text-xs uppercase tracking-wider">Growth</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p, i) => (
                <tr key={p.item_code || i} className="border-b border-gray-50 last:border-0 hover:bg-indigo-50/30 transition-colors">
                  <td className="px-6 py-3.5 text-gray-400 font-medium tabular-nums">{i + 1}</td>
                  <td className="px-6 py-3.5 font-medium text-gray-900">{p.item_name}</td>
                  <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{aed(p.total_sales)}</td>
                  <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{Number(p.total_qty).toLocaleString()}</td>
                  <td className="px-6 py-3.5 text-right"><GrowthBadge value={p.growth_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
