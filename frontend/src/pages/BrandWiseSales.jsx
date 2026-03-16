import { useState, useEffect } from 'react';
import { fetchBrandWiseSales, fetchBrandItems } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Target, TrendingUp, Award, Eye, X, ChevronRight } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function BrandWiseSales() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ date_from: '2026-03-01', date_to: '2026-03-12' });
  const [drillBrand, setDrillBrand] = useState(null);
  const [drillItems, setDrillItems] = useState([]);
  const [drillLoading, setDrillLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchBrandWiseSales(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const handleDrill = (brand) => {
    if (drillBrand?.brand_code === brand.brand_code) {
      setDrillBrand(null);
      setDrillItems([]);
      return;
    }
    setDrillBrand(brand);
    setDrillLoading(true);
    fetchBrandItems({ ...filters, brand: brand.brand_code })
      .then(res => setDrillItems(res.items || []))
      .catch(console.error)
      .finally(() => setDrillLoading(false));
  };

  const summary = data?.summary || {};
  const brands = data?.brands || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Brand Wise Sales</h1>
        <p className="text-sm text-gray-500 mt-1">Performance breakdown by brand with target achievement tracking</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['sales_org', 'brand', 'user_code', 'date_from', 'date_to', 'route']} />

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

          {/* Brand Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Brand Breakdown</h2>
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
                    <tr key={i} className={`border-b border-gray-50 last:border-0 transition-colors ${
                      drillBrand?.brand_code === b.brand_code ? 'bg-indigo-50/50' : 'hover:bg-gray-50/70'
                    }`}>
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
                        <button onClick={() => handleDrill(b)}
                          className={`inline-flex items-center gap-1 text-sm font-medium transition-colors ${
                            drillBrand?.brand_code === b.brand_code
                              ? 'text-rose-600 hover:text-rose-700'
                              : 'text-indigo-600 hover:text-indigo-700'
                          }`}>
                          {drillBrand?.brand_code === b.brand_code ? (
                            <><X className="w-3.5 h-3.5" /> Close</>
                          ) : (
                            <><Eye className="w-3.5 h-3.5" /> View</>
                          )}
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

          {/* Drill-down Items */}
          {drillBrand && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center gap-2 mb-4">
                <ChevronRight className="w-4 h-4 text-indigo-500" />
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
                  Items for {drillBrand.brand_name}
                </h2>
              </div>
              {drillLoading ? <Loading /> : (
                <DataTable
                  columns={[
                    { key: 'item_code', label: 'Item Code' },
                    { key: 'item_name', label: 'Item Name' },
                    { key: 'target', label: 'Target', format: 'currency' },
                    { key: 'sales', label: 'Sales', format: 'currency' },
                    { key: 'qty', label: 'Qty', format: 'number' },
                    { key: 'achieved_pct', label: 'Achieved %', format: 'percent' },
                  ]}
                  data={drillItems}
                  exportName={`brand-items-${drillBrand.brand_code}`}
                />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
