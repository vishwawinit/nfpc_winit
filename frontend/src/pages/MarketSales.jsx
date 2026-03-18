import { useState, useEffect, useRef } from 'react';
import { fetchMarketSales } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';

const aed = (v) => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export default function MarketSales() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState({ year: new Date().getFullYear() });

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchMarketSales(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const monthlyData = data?.monthly_data || [];

  const chartData = MONTHS.map((m, i) => {
    const row = monthlyData.find((d) => d.month === i + 1);
    return {
      month: m,
      current_year_sales: row?.current_year_sales ?? 0,
      last_year_sales: row?.last_year_sales ?? 0,
      growth_pct: row?.growth_pct ?? 0,
    };
  });

  const currentRow = { label: 'CURRENT YEAR', ytd: data?.ytd_current };
  const lastRow = { label: 'LAST YEAR', ytd: data?.ytd_last };
  const growthRow = { label: 'GROWTH', ytd: data?.ytd_growth };

  MONTHS.forEach((m, i) => {
    const row = monthlyData.find((d) => d.month === i + 1);
    currentRow[m] = row?.current_year_sales ?? 0;
    lastRow[m] = row?.last_year_sales ?? 0;
    growthRow[m] = row?.growth_pct ?? 0;
  });

  const tableRows = [currentRow, lastRow, growthRow];

  const formatCell = (row, key) => {
    const val = row[key];
    if (val == null) return '-';
    if (row.label === 'GROWTH') return `${Number(val).toFixed(1)}%`;
    return aed(val);
  };

  const getGrowthColor = (val) => {
    if (val == null) return '';
    const n = Number(val);
    if (n > 0) return 'text-emerald-600 font-semibold';
    if (n < 0) return 'text-rose-600 font-semibold';
    return 'text-gray-500';
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Market Sales Performance</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Year-over-year comparison by month</p>
        </div>
      </div>

      {/* Filters — always mounted */}
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        showFields={['year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']}
      />

      {/* Refreshing indicator */}
      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {/* Data area */}
      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (<>

      {/* Combo Chart */}
      <div className="chart-container">
        <div className="chart-header">
          <div className="pb-4 border-b border-gray-100/60">
            <h2 className="text-[13px] font-semibold text-gray-700 uppercase tracking-wide">Monthly Sales Comparison</h2>
          </div>
        </div>
        <div className="chart-body">
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData}>
              <defs>
                <linearGradient id="gradCurYear" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" />
                  <stop offset="100%" stopColor="#6366f1" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v}
                axisLine={false} tickLine={false}
              />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#9ca3af' }} unit="%" axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(v, name) =>
                  name === 'Growth %' ? `${Number(v).toFixed(1)}%` : aed(v)
                }
                contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 12px 32px -4px rgb(0 0 0 / 0.12)', fontSize: 13, padding: '10px 14px', backgroundColor: 'rgba(255,255,255,0.97)' }}
                cursor={{ fill: 'rgba(99,102,241,0.04)' }}
              />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', color: '#6b7280', paddingTop: '16px' }} />
              <Bar yAxisId="left" dataKey="current_year_sales" fill="url(#gradCurYear)" name="Current Year" radius={[6, 6, 0, 0]} />
              <Bar yAxisId="left" dataKey="last_year_sales" fill="#e0e7ff" name="Last Year" radius={[6, 6, 0, 0]} />
              <Line yAxisId="right" dataKey="growth_pct" stroke="#f59e0b" name="Growth %" strokeWidth={2.5}
                dot={{ r: 4, fill: '#fff', stroke: '#f59e0b', strokeWidth: 2 }}
                activeDot={{ r: 6, fill: '#f59e0b', stroke: '#fff', strokeWidth: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100/80 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider sticky left-0 bg-gray-50 z-10"></th>
              <th className="px-4 py-3 text-right text-[11px] font-semibold text-gray-400 uppercase tracking-wider">YTD</th>
              {MONTHS.map((m) => (
                <th key={m} className="px-4 py-3 text-right text-[11px] font-semibold text-gray-400 uppercase tracking-wider">{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row, idx) => (
              <tr key={row.label} className={`border-b border-gray-50 last:border-b-0 hover:bg-indigo-50/30 transition-colors ${idx % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                <td className="px-4 py-3 font-semibold text-gray-800 sticky left-0 bg-white whitespace-nowrap z-10">
                  {row.label}
                </td>
                <td className={`px-4 py-3 text-right font-medium tabular-nums ${row.label === 'GROWTH' ? getGrowthColor(row.ytd) : 'text-gray-700'}`}>
                  {formatCell(row, 'ytd')}
                </td>
                {MONTHS.map((m) => (
                  <td key={m} className={`px-4 py-3 text-right tabular-nums ${row.label === 'GROWTH' ? getGrowthColor(row[m]) : 'text-gray-700'}`}>
                    {formatCell(row, m)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      </>)}
    </div>
  );
}
