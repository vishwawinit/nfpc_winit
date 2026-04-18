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
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    return { month: now.getMonth() + 1, year: now.getFullYear() };
  });
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchTopProducts(filters)
      .then(res => { if (!cancelled) setData(res.data || res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  const products = (Array.isArray(data) ? data : []).slice(0, 20);
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
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['month', 'year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'category', 'brand']} />

      {loading ? <Loading /> : products.length === 0 ? (
        <div className="text-center py-20 text-gray-400">No data available</div>
      ) : (
        <div className="space-y-6">
          {/* KPI Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard title="Total Sales" value={aed(totalSales)} icon={Banknote} color="blue" variant="light" />
            <KpiCard title="Total Quantity" value={totalQty.toLocaleString()} icon={Package} color="purple" variant="light" />
            <KpiCard title="Avg Growth" value={`${avgGrowth >= 0 ? '+' : ''}${avgGrowth.toFixed(1)}%`} icon={TrendingUp} color={avgGrowth >= 0 ? 'green' : 'red'} variant="light" />
          </div>

          {/* Bar Chart */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales Value by Product</h2>
            <ResponsiveContainer width="100%" height={Math.max(products.length * 40, 300)}>
              <BarChart data={products} layout="vertical" margin={{ left: 10, right: 130, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis type="number" tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis dataKey="item_name" type="category" tick={{ fontSize: 11, fill: '#475569' }} width={180} axisLine={false} tickLine={false} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="bg-white border border-gray-200 rounded-xl shadow-lg px-4 py-3 text-[13px]">
                        <p className="font-semibold text-gray-800 mb-1">{d.item_name}</p>
                        <p className="text-indigo-600">Sales: {aed(d.total_sales)}</p>
                        <p className="text-purple-600">Qty: {Number(d.total_qty).toLocaleString()} Units</p>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="total_sales" name="Sales" radius={[0, 6, 6, 0]}
                  label={({ x, y, width, height, value, index }) => {
                    const fmt = v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v;
                    return (
                      <text x={x + width + 8} y={y + height / 2 + 4} fontSize={11} fontWeight="700" fill={barColors[index] || '#c7d2fe'}>{fmt(value)}</text>
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
      )}
    </div>
  );
}
