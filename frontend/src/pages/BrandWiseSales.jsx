import { useState, useEffect, useRef } from 'react';
import { fetchBrandWiseSales, fetchBrandItems } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Target, TrendingUp, Award, Eye, X, ChevronRight, Download } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

function exportToExcel(data, columns, filename) {
  const header = columns.map(c => c.label).join('\t');
  const rows = data.map(row => columns.map(c => {
    const v = row[c.key] ?? '';
    return typeof v === 'number' ? v : String(v);
  }).join('\t'));
  const tsv = header + '\n' + rows.join('\n');
  const blob = new Blob([tsv], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.xls`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BrandWiseSales() {
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
  const [modalBrand, setModalBrand] = useState(null);
  const [modalItems, setModalItems] = useState([]);
  const [modalLoading, setModalLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchBrandWiseSales(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const handleView = (brand) => {
    setModalBrand(brand);
    setModalLoading(true);
    setModalItems([]);
    fetchBrandItems({ ...filters, brand: brand.brand_code })
      .then(res => setModalItems(res.items || []))
      .catch(console.error)
      .finally(() => setModalLoading(false));
  };

  const closeModal = () => {
    setModalBrand(null);
    setModalItems([]);
  };

  const summary = data?.summary || {};
  const brands = data?.brands || [];

  const brandColumns = [
    { key: 'brand_code', label: 'Brand Code' },
    { key: 'brand_name', label: 'Brand Name' },
    { key: 'target', label: 'Target' },
    { key: 'sales', label: 'Sales' },
    { key: 'qty', label: 'Qty' },
    { key: 'achieved_pct', label: 'Achieved %' },
    { key: 'pct_of_total', label: '% of Total' },
  ];

  const itemColumns = [
    { key: 'item_code', label: 'Item Code' },
    { key: 'item_name', label: 'Item Name' },
    { key: 'target', label: 'Target', format: 'currency' },
    { key: 'sales', label: 'Sales', format: 'currency' },
    { key: 'qty', label: 'Qty', format: 'number' },
    { key: 'achieved_pct', label: 'Achieved %', format: 'percent' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Brand Wise Sales</h1>
        <p className="text-sm text-gray-500 mt-1">Performance breakdown by brand with target achievement tracking</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard title="Total Brand Target" value={aed(summary.total_brand_target)} icon={Target} color="blue" />
            <KpiCard title="Total Brand Achieved" value={aed(summary.total_brand_achieved)} icon={TrendingUp} color="green" />
            <KpiCard title="Achievement %" value={summary.brand_achieved_pct != null ? `${Number(summary.brand_achieved_pct).toFixed(1)}%` : '-'}
              icon={Award}
              color={summary.brand_achieved_pct >= 100 ? 'green' : summary.brand_achieved_pct >= 80 ? 'yellow' : 'red'} />
          </div>

          {/* Brand Table with Export */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Brand Breakdown</h2>
              <button
                onClick={() => exportToExcel(brands, brandColumns, 'brand-wise-sales')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <Download className="w-3.5 h-3.5" /> Export Excel
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80 border-b border-gray-100">
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Brand Code</th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Brand Name</th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Target</th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Sales</th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Qty</th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Achieved %</th>
                    <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">% of Total</th>
                    <th className="px-6 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {brands.map((b, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/70 transition-colors">
                      <td className="px-6 py-3.5 font-mono text-xs text-gray-500">{b.brand_code}</td>
                      <td className="px-6 py-3.5 font-medium text-gray-900">{b.brand_name}</td>
                      <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{aed(b.target)}</td>
                      <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{aed(b.sales)}</td>
                      <td className="px-6 py-3.5 text-right text-gray-700 tabular-nums">{b.qty?.toLocaleString() ?? '-'}</td>
                      <td className="px-6 py-3.5 text-right">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${
                          b.achieved_pct >= 100 ? 'bg-emerald-50 text-emerald-700' :
                          b.achieved_pct >= 80 ? 'bg-amber-50 text-amber-700' :
                          'bg-rose-50 text-rose-700'
                        }`}>
                          {b.achieved_pct != null ? `${Number(b.achieved_pct).toFixed(1)}%` : '-'}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-right text-gray-600 tabular-nums">{b.pct_of_total != null ? `${Number(b.pct_of_total).toFixed(1)}%` : '-'}</td>
                      <td className="px-6 py-3.5 text-center">
                        <button onClick={() => handleView(b)}
                          className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors">
                          <Eye className="w-3.5 h-3.5" /> View
                        </button>
                      </td>
                    </tr>
                  ))}
                  {brands.length === 0 && (
                    <tr><td colSpan={8} className="px-6 py-12 text-center text-gray-400">No brands found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Modal for Item Drill-down */}
      {modalBrand && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
                  <ChevronRight className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">
                    {modalBrand.brand_name} <span className="text-gray-400 font-normal text-sm">({modalBrand.brand_code})</span>
                  </h2>
                  <p className="text-sm text-gray-500">
                    Total Sales: {aed(modalBrand.sales)} &bull; {modalItems.length} items
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => exportToExcel(modalItems, itemColumns, `brand-items-${modalBrand.brand_code}`)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  <Download className="w-3.5 h-3.5" /> Export Excel
                </button>
                <button onClick={closeModal}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-auto p-6">
              {modalLoading ? <Loading /> : (
                <DataTable
                  columns={itemColumns}
                  data={modalItems}
                  pageSize={50}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
