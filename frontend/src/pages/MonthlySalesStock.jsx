import React, { useState, useEffect } from 'react';
import { fetchMonthlySalesStock } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import { Package, Layers } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function MonthlySalesStock() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });

  useEffect(() => {
    setLoading(true);
    fetchMonthlySalesStock(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const items = data?.items || [];

  // Collect all unique channel names dynamically
  const channelSet = new Set();
  items.forEach(item => {
    if (item.channels) Object.keys(item.channels).forEach(ch => channelSet.add(ch));
  });
  const channels = [...channelSet].sort();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Monthly Sales & Stock</h1>
          <p className="text-sm text-gray-500 mt-1">Item-level sales across channels with MTD and YTD comparison</p>
        </div>
        {!loading && items.length > 0 && (
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-2">
              <Package className="w-4 h-4 text-indigo-500" />
              <span className="text-sm font-semibold text-gray-700">{items.length}</span>
              <span className="text-sm text-gray-400">items</span>
            </div>
            <div className="flex items-center gap-2 bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-2">
              <Layers className="w-4 h-4 text-violet-500" />
              <span className="text-sm font-semibold text-gray-700">{channels.length}</span>
              <span className="text-sm text-gray-400">channels</span>
            </div>
          </div>
        )}
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['sales_org', 'brand', 'category', 'date_from', 'date_to']} />

      {loading ? <Loading /> : items.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50/80 z-10 backdrop-blur-sm" rowSpan={2}>
                    Item Code
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-50/80" rowSpan={2}>
                    Item Name
                  </th>
                  {channels.map(ch => (
                    <th key={ch} colSpan={2} className="px-4 py-3 text-center text-xs font-semibold text-indigo-600 uppercase tracking-wider border-l border-gray-200">
                      {ch}
                    </th>
                  ))}
                </tr>
                <tr className="bg-gray-50/60 border-b border-gray-200">
                  {channels.map(ch => (
                    <React.Fragment key={ch}>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 border-l border-gray-200">MTD</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-400">YTD</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={i} className={`border-b border-gray-50 last:border-0 transition-colors hover:bg-indigo-50/30 ${
                    i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                  }`}>
                    <td className={`px-6 py-3 font-mono text-xs text-gray-500 whitespace-nowrap sticky left-0 z-10 ${
                      i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                    }`}>{item.item_code}</td>
                    <td className="px-6 py-3 font-medium text-gray-900 whitespace-nowrap">{item.item_name}</td>
                    {channels.map(ch => {
                      const chData = item.channels?.[ch] || {};
                      return (
                        <React.Fragment key={ch}>
                          <td className="px-3 py-3 text-right text-xs text-gray-700 tabular-nums border-l border-gray-100">{aed(chData.mtd_amount)}</td>
                          <td className="px-3 py-3 text-right text-xs text-gray-500 tabular-nums">{aed(chData.ytd_amount)}</td>
                        </React.Fragment>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-6 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-400">{items.length} items across {channels.length} channels</span>
          </div>
        </div>
      )}
    </div>
  );
}
