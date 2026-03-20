import React, { useState, useEffect, useMemo, useRef } from 'react';
import { fetchMonthlySalesStock } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import { Package, Layers, Search, Download, ChevronLeft, ChevronRight } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const PAGE_SIZES = [20, 50, 100, 200];

function exportToExcel(items, channels, filename) {
  const header = ['Item Code', 'Item Name', ...channels.flatMap(ch => [`${ch} MTD`, `${ch} YTD`])].join('\t');
  const rows = items.map(item => {
    const base = [item.item_code, item.item_name];
    const chVals = channels.flatMap(ch => {
      const d = item.channels?.[ch] || {};
      return [d.mtd_amount || 0, d.ytd_amount || 0];
    });
    return [...base, ...chVals].join('\t');
  });
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `${filename}.xls`; a.click();
  URL.revokeObjectURL(url);
}

export default function MonthlySalesStock() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchMonthlySalesStock(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const items = data?.items || [];

  // Collect channels
  const channels = useMemo(() => {
    const s = new Set();
    items.forEach(item => {
      if (item.channels) Object.keys(item.channels).forEach(ch => s.add(ch));
    });
    return [...s].sort();
  }, [items]);

  // Search filter
  const filtered = useMemo(() => {
    if (!search) return items;
    const s = search.toLowerCase();
    return items.filter(item =>
      item.item_code?.toLowerCase().includes(s) ||
      item.item_name?.toLowerCase().includes(s)
    );
  }, [items, search]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIdx = (safePage - 1) * pageSize;
  const paged = filtered.slice(startIdx, startIdx + pageSize);

  // Reset page on search/filter change
  useEffect(() => { setPage(1); }, [search, filters, pageSize]);

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
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'category', 'brand']} />

      {loading ? <Loading /> : items.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          {/* Toolbar: Search + Export + Page Size */}
          <div className="px-6 py-3 border-b border-gray-100 flex items-center justify-between gap-4">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search items..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => exportToExcel(filtered, channels, 'monthly-sales-stock')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <Download className="w-3.5 h-3.5" /> Export Excel
              </button>
            </div>
          </div>

          {/* Table */}
          <div className={`overflow-x-auto ${paged.length >= 50 ? 'max-h-[600px] overflow-y-auto' : ''}`}>
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-20">
                <tr className="bg-gray-50">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50 z-30" rowSpan={2}>
                    Item Code
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-50" rowSpan={2}>
                    Item Name
                  </th>
                  {channels.map(ch => (
                    <th key={ch} colSpan={2} className="px-4 py-3 text-center text-xs font-semibold text-indigo-600 uppercase tracking-wider border-l border-gray-200">
                      {ch}
                    </th>
                  ))}
                </tr>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {channels.map(ch => (
                    <React.Fragment key={ch}>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 border-l border-gray-200">MTD</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-400">YTD</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.map((item, i) => (
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
                {paged.length === 0 && (
                  <tr><td colSpan={2 + channels.length * 2} className="px-6 py-12 text-center text-gray-400">No matching items</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Footer: Page Size (left) + Info (center) + Pagination (right) */}
          <div className="px-6 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
            <select
              value={pageSize}
              onChange={e => setPageSize(Number(e.target.value))}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none"
            >
              {PAGE_SIZES.map(s => (
                <option key={s} value={s}>{s} rows</option>
              ))}
            </select>
            <span className="text-xs text-gray-400">
              Showing {startIdx + 1}–{Math.min(startIdx + pageSize, filtered.length)} of {filtered.length} items
              {search && ` (filtered from ${items.length})`}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-gray-500 min-w-[80px] text-center">
                Page {safePage} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
