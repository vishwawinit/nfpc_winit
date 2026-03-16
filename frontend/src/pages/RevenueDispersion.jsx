import React, { useState, useEffect } from 'react';
import { fetchRevenueDispersion } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import { BarChart3, Layers, TrendingUp } from 'lucide-react';

const pctColor = (val) => {
  const n = parseFloat(val);
  if (isNaN(n)) return '';
  if (n >= 30) return 'bg-emerald-50 text-emerald-700 font-semibold';
  if (n >= 15) return 'bg-blue-50 text-blue-700 font-semibold';
  if (n >= 5) return 'bg-amber-50 text-amber-700 font-semibold';
  return 'text-gray-500';
};

export default function RevenueDispersion() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-01-01', date_to: '2026-03-12' });
  const [activeTab, setActiveTab] = useState('revenue');

  useEffect(() => {
    setLoading(true);
    fetchRevenueDispersion(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const revenueData = data?.revenue_dispersion || [];
  const skuData = data?.sku_dispersion || [];
  const rows = activeTab === 'revenue' ? revenueData : skuData;
  const rangeKey = activeTab === 'revenue' ? 'billing_range' : 'sku_range';

  // Pivot: group by range, months as columns
  const months = [...new Set(rows.map(r => r.month))].sort();
  const ranges = [...new Set(rows.map(r => r[rangeKey]))];

  const pivoted = ranges.map(range => {
    const row = { range };
    months.forEach(m => {
      const match = rows.find(r => r[rangeKey] === range && r.month === m);
      row[`${m}_invoices`] = match?.invoice_count ?? '-';
      row[`${m}_customers`] = match?.customer_count ?? '-';
      row[`${m}_pct`] = match?.pct != null ? `${Number(match.pct).toFixed(1)}%` : '-';
    });
    return row;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Revenue Dispersion</h1>
        <p className="text-sm text-gray-500 mt-1">Analyze billing and SKU distribution across customer segments</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['sales_org', 'user_code', 'date_from', 'date_to']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <BarChart3 className="w-7 h-7 text-gray-300" />
          </div>
          <p className="text-gray-400 font-medium">No data available</p>
          <p className="text-gray-300 text-sm mt-1">Adjust your filters and try again</p>
        </div>
      ) : (
        <>
          {/* Tab Toggle */}
          <div className="flex gap-1 bg-gray-100/80 rounded-xl p-1 w-fit">
            <button onClick={() => setActiveTab('revenue')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'revenue'
                  ? 'bg-white shadow-sm text-blue-600 ring-1 ring-gray-200/50'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              <TrendingUp className="w-4 h-4" />
              Revenue Dispersion
            </button>
            <button onClick={() => setActiveTab('sku')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'sku'
                  ? 'bg-white shadow-sm text-blue-600 ring-1 ring-gray-200/50'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              <Layers className="w-4 h-4" />
              SKU Dispersion
            </button>
          </div>

          {/* Pivot Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80">
                    <th className="px-5 py-3.5 text-left text-xs text-gray-500 uppercase font-semibold tracking-wider sticky left-0 bg-gray-50/80 z-10" rowSpan={2}>
                      {activeTab === 'revenue' ? 'Billing Range' : 'SKU Range'}
                    </th>
                    {months.map(m => (
                      <th key={m} colSpan={3} className="px-2 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider border-l border-gray-200/60">
                        {m}
                      </th>
                    ))}
                  </tr>
                  <tr className="bg-gray-50/50">
                    {months.map(m => (
                      <React.Fragment key={m}>
                        <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase tracking-wide border-l border-gray-200/60">Invoices</th>
                        <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase tracking-wide">Customers</th>
                        <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase tracking-wide">%</th>
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pivoted.map((row, i) => (
                    <tr key={i} className="hover:bg-blue-50/30 transition-colors">
                      <td className="px-5 py-3 font-semibold text-gray-700 whitespace-nowrap sticky left-0 bg-white z-10 border-r border-gray-50">
                        {row.range}
                      </td>
                      {months.map(m => {
                        const pctVal = row[`${m}_pct`];
                        return (
                          <React.Fragment key={m}>
                            <td className="px-3 py-3 text-center text-gray-600 tabular-nums border-l border-gray-100/60">
                              {row[`${m}_invoices`]}
                            </td>
                            <td className="px-3 py-3 text-center text-gray-600 tabular-nums">
                              {row[`${m}_customers`]}
                            </td>
                            <td className="px-3 py-3 text-center tabular-nums">
                              <span className={`inline-block px-2 py-0.5 rounded-md text-xs ${pctColor(pctVal)}`}>
                                {pctVal}
                              </span>
                            </td>
                          </React.Fragment>
                        );
                      })}
                    </tr>
                  ))}
                  {pivoted.length === 0 && (
                    <tr>
                      <td colSpan={1 + months.length * 3} className="px-4 py-12 text-center">
                        <div className="flex flex-col items-center">
                          <BarChart3 className="w-8 h-8 text-gray-200 mb-2" />
                          <span className="text-gray-400 font-medium">No dispersion data</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
