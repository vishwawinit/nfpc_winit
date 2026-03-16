import { useState, useEffect } from 'react';
import { fetchMarketSales } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';

const aed = (v) => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const chartTooltipStyle = {
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
};

export default function MarketSales() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ year: 2026 });

  useEffect(() => {
    setLoading(true);
    fetchMarketSales(filters)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filters]);

  if (loading) return <Loading />;
  if (!data) return <div className="text-center py-12 text-gray-400">No data available</div>;

  const monthlyData = data.monthly_data || [];

  // Build chart data keyed by month name (API returns month as int 1-12)
  const chartData = MONTHS.map((m, i) => {
    const row = monthlyData.find((d) => d.month === i + 1);
    return {
      month: m,
      current_year_sales: row?.current_year_sales ?? 0,
      last_year_sales: row?.last_year_sales ?? 0,
      growth_pct: row?.growth_pct ?? 0,
    };
  });

  // Build table rows: CURRENT YEAR, LAST YEAR, GROWTH
  const currentRow = { label: 'CURRENT YEAR', ytd: data.ytd_current };
  const lastRow = { label: 'LAST YEAR', ytd: data.ytd_last };
  const growthRow = { label: 'GROWTH', ytd: data.ytd_growth };

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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Market Sales Performance</h1>
        <p className="text-sm text-gray-500 mt-1">Year-over-year comparison by month</p>
      </div>

      <FilterPanel
        filters={filters}
        onChange={setFilters}
        showFields={['sales_org', 'year']}
      />

      {/* Combo Chart */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Monthly Sales Comparison</h2>
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 12 }}
              tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v}
            />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} unit="%" />
            <Tooltip
              formatter={(v, name) =>
                name === 'Growth %' ? `${Number(v).toFixed(1)}%` : aed(v)
              }
              contentStyle={chartTooltipStyle}
            />
            <Legend />
            <Bar
              yAxisId="left"
              dataKey="current_year_sales"
              fill="#818cf8"
              name="Current Year"
              radius={[6, 6, 0, 0]}
            />
            <Bar
              yAxisId="left"
              dataKey="last_year_sales"
              fill="#c7d2fe"
              name="Last Year"
              radius={[6, 6, 0, 0]}
            />
            <Line
              yAxisId="right"
              dataKey="growth_pct"
              stroke="#fb923c"
              name="Growth %"
              strokeWidth={2}
              dot={{ r: 4, fill: '#fb923c' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Table: Rows = CURRENT YEAR / LAST YEAR / GROWTH, Columns = YTD + Jan..Dec */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50/80 border-b border-gray-100">
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50/80 z-10"></th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">YTD</th>
              {MONTHS.map((m) => (
                <th key={m} className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row, idx) => (
              <tr key={row.label} className={`border-b border-gray-50 last:border-b-0 hover:bg-gray-50/50 transition-colors ${idx % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
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
    </div>
  );
}
