import { useState, useEffect, useRef } from 'react';
import { fetchSalesPerformance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Package, BarChart3, TrendingUp, ArrowUpRight, ArrowDownRight, RotateCcw, ShoppingBag, AlertTriangle, Timer } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const pct = (v) => v != null ? `${Number(v).toFixed(1)}%` : '-';

/* ---------- ROS metric card ---------- */
function RosCard({ label, value, icon: Icon, bgClass, textClass, iconClass }) {
  return (
    <div className={`${bgClass} rounded-xl p-4 text-center border border-transparent transition-all duration-200 hover:scale-[1.02] hover:shadow-sm`}>
      <div className="flex items-center justify-center gap-1.5 mb-2.5">
        {Icon && <Icon className={`w-4 h-4 ${iconClass}`} strokeWidth={1.75} />}
        <span className={`text-[10px] uppercase tracking-wider font-semibold ${textClass} opacity-70`}>{label}</span>
      </div>
      <div className={`text-[15px] font-bold tabular-nums ${textClass}`}>{aed(value)}</div>
    </div>
  );
}

export default function SalesPerformance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    return { day: now.getDate(), month: now.getMonth() + 1, year: now.getFullYear() };
  });

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchSalesPerformance(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  const ros = data?.return_on_sales || {};
  const sku = data?.sku_counts || {};

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Sales Performance</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Monthly achievement, returns analysis & SKU performance</p>
        </div>
      </div>

      {/* Filters — always mounted, never unmounted during loading */}
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        showFields={['day', 'month', 'year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'category', 'brand']}
      />

      {/* Refreshing indicator — subtle bar, doesn't hide content */}
      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {/* Data area — full loading only on first load */}
      {loading && !data ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (<>

      {/* ===== MTD vs LMTD Sales ===== */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <KpiCard
          title={`LMTD Sales${data.last_month_label ? ` (${data.last_month_label})` : ''}`}
          value={aed(data.lmtd_sales)}
          color="purple"
          icon={TrendingUp}
          variant="solid"
        />
        <KpiCard
          title={`MTD Sales${data.period_label ? ` (${data.period_label})` : ''}`}
          value={aed(data.mtd_sales)}
          color="blue"
          icon={TrendingUp}
          variant="solid"
        />
      </div>

      {/* ===== Return on Sales ===== */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100/80 p-6 kpi-card relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-slate-400 to-slate-600 opacity-40 rounded-t-2xl" />
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center shadow-sm">
              <RotateCcw className="w-4.5 h-4.5 text-slate-500" strokeWidth={1.75} />
            </div>
            <div>
              <h2 className="text-[13px] font-semibold text-gray-700 uppercase tracking-wide">Return on Sales</h2>
              <p className="text-[11px] text-gray-400 mt-0.5">Returns as % of total sales</p>
            </div>
          </div>
          <span className={`text-sm font-bold px-3.5 py-1.5 rounded-full border ${
            (ros.ros_pct || 0) <= 2 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' :
            (ros.ros_pct || 0) <= 5 ? 'bg-amber-50 text-amber-600 border-amber-100' :
            'bg-violet-50 text-violet-600 border-violet-100'
          }`}>
            {pct(ros.ros_pct)}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <RosCard label="Total Sales" value={ros.total_sales} icon={ShoppingBag}
            bgClass="bg-indigo-50/70" textClass="text-indigo-600" iconClass="text-indigo-400" />
          <RosCard label="Total Returns" value={ros.total_returns} icon={RotateCcw}
            bgClass="bg-slate-100/70" textClass="text-slate-600" iconClass="text-slate-400" />
          <RosCard label="Good Returns" value={ros.good_return} icon={RotateCcw}
            bgClass="bg-emerald-50/70" textClass="text-emerald-600" iconClass="text-emerald-400" />
          <RosCard label="Bad Returns" value={ros.bad_return} icon={AlertTriangle}
            bgClass="bg-amber-50/70" textClass="text-amber-600" iconClass="text-amber-400" />
        </div>
      </div>

      {/* ===== SKU Counts ===== */}
      <div>
        <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">SKU Performance</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            title={`Today SKU Sold (${sku.today_label || '-'})`}
            value={sku.today != null ? Number(sku.today).toLocaleString() : '-'}
            color="blue"
            icon={Package}
            variant="solid"
          />
          <KpiCard
            title="MTD SKU Sold"
            value={sku.mtd != null ? Number(sku.mtd).toLocaleString() : '-'}
            color="purple"
            icon={BarChart3}
            variant="solid"
          />
          <KpiCard
            title="YTD SKU Sold"
            value={sku.ytd != null ? Number(sku.ytd).toLocaleString() : '-'}
            color="green"
            icon={TrendingUp}
            variant="solid"
          />
        </div>
      </div>

      {/* ===== SKU Performance Table ===== */}
      {data.sku_table && data.sku_table.length > 0 && (
        <div>
          <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">SKU Detail</h2>
          <DataTable
            columns={[
              { key: 'item_code', label: 'Item Code' },
              { key: 'item_name', label: 'Item Name' },
              { key: 'category_name', label: 'Category' },
              { key: 'last_month_sales', label: 'Last Month', format: 'currency' },
              { key: 'current_month_sales', label: 'Current Month', format: 'currency' },
              { key: 'current_week_sales', label: 'This Week', format: 'currency' },
              {
                key: 'growth',
                label: 'Growth %',
                format: 'percent',
                render: (val) => {
                  const isPositive = val > 0;
                  const isNegative = val < 0;
                  const Icon = isPositive ? ArrowUpRight : ArrowDownRight;
                  return (
                    <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                      isPositive ? 'bg-emerald-50 text-emerald-600' :
                      isNegative ? 'bg-orange-50 text-orange-500' :
                      'bg-gray-50 text-gray-500'
                    }`}>
                      {(isPositive || isNegative) && <Icon className="w-3 h-3" />}
                      {isPositive ? '+' : ''}{pct(val)}
                    </span>
                  );
                },
              },
            ]}
            data={data.sku_table}
            exportName="sales-performance-sku"
          />
        </div>
      )}

      </>)}
    </div>
  );
}
