import { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { fetchSalesPerformance } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { Package, BarChart3, TrendingUp, ArrowUpRight, ArrowDownRight, RotateCcw, ShoppingBag, AlertTriangle, Timer } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const pct = (v) => v != null ? `${Number(v).toFixed(1)}%` : '-';

/* ---------- Modern gauge with gradient arc ---------- */
function GaugeDial({ label, value, accentColor = '#818cf8', bgColor = '#e0e7ff' }) {
  const clamped = Math.min(Math.max(Number(value) || 0, 0), 150);
  const remaining = 150 - clamped;
  const data = [
    { name: 'value', v: clamped },
    { name: 'rest', v: remaining },
  ];

  const statusColor =
    clamped >= 100 ? '#6ee7b7' :
    clamped >= 75  ? '#fcd34d' :
    clamped >= 50  ? '#fdba74' : '#fca5a5';

  const statusTextColor =
    clamped >= 100 ? 'text-emerald-600' :
    clamped >= 75  ? 'text-amber-600' :
    clamped >= 50  ? 'text-orange-600' : 'text-rose-500';

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col items-center">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">{label}</h3>
      <div className="w-44 h-24 relative">
        <ResponsiveContainer width="100%" height={100}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="100%"
              startAngle={180}
              endAngle={0}
              innerRadius={55}
              outerRadius={72}
              dataKey="v"
              stroke="none"
              cornerRadius={6}
            >
              <Cell fill={statusColor} />
              <Cell fill="#f1f5f9" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex items-end justify-center pb-0">
          <span className={`text-2xl font-bold ${statusTextColor}`}>{pct(value)}</span>
        </div>
      </div>
      <div className="flex justify-between w-36 mt-1 text-[10px] text-gray-300 font-medium">
        <span>0%</span>
        <span>75%</span>
        <span>150%</span>
      </div>
    </div>
  );
}

/* ---------- ROS metric card ---------- */
function RosCard({ label, value, icon: Icon, bgClass = 'bg-gray-50', textClass = 'text-gray-600', iconClass = 'text-gray-400' }) {
  return (
    <div className={`${bgClass} rounded-xl p-4 text-center border border-transparent`}>
      <div className="flex items-center justify-center gap-1.5 mb-2">
        {Icon && <Icon className={`w-3.5 h-3.5 ${iconClass}`} />}
        <span className={`text-[10px] uppercase tracking-wider font-semibold ${textClass} opacity-70`}>{label}</span>
      </div>
      <div className={`text-sm font-bold ${textClass}`}>{aed(value)}</div>
    </div>
  );
}

export default function SalesPerformance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ month: 3, year: 2026 });

  useEffect(() => {
    setLoading(true);
    fetchSalesPerformance(filters)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filters]);

  if (loading) return <Loading />;
  if (!data) return <div className="text-center py-12 text-gray-400">No data available</div>;

  const ros = data.return_on_sales || {};
  const sku = data.sku_counts || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Sales Performance</h1>
        <p className="text-sm text-gray-500 mt-1">Monthly achievement, returns analysis, and SKU performance</p>
      </div>

      {/* Filters */}
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        showFields={['route', 'month', 'year', 'sales_org']}
      />

      {/* ===== Achievement Gauges ===== */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <GaugeDial
          label="Last Month Achievement"
          value={data.last_month_achievement_pct}
        />
        <GaugeDial
          label="Current Month Achievement"
          value={data.current_month_achievement_pct}
        />
      </div>

      {/* ===== Return on Sales ===== */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Return on Sales</h2>
          <span className={`text-sm font-bold px-3 py-1 rounded-full ${
            (ros.ros_pct || 0) <= 2 ? 'bg-emerald-50 text-emerald-600' :
            (ros.ros_pct || 0) <= 5 ? 'bg-amber-50 text-amber-600' :
            'bg-rose-50 text-rose-500'
          }`}>
            {pct(ros.ros_pct)}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <RosCard label="Goods Return" value={ros.gr} icon={RotateCcw}
            bgClass="bg-rose-50" textClass="text-rose-600" iconClass="text-rose-400" />
          <RosCard label="Expiry" value={ros.expiry} icon={Timer}
            bgClass="bg-orange-50" textClass="text-orange-600" iconClass="text-orange-400" />
          <RosCard label="Damage" value={ros.damage} icon={AlertTriangle}
            bgClass="bg-amber-50" textClass="text-amber-600" iconClass="text-amber-400" />
          <RosCard label="Near Expiry" value={ros.near_expiry} icon={Timer}
            bgClass="bg-yellow-50" textClass="text-yellow-600" iconClass="text-yellow-400" />
          <RosCard label="Total Sales" value={ros.total_sales} icon={ShoppingBag}
            bgClass="bg-blue-50" textClass="text-blue-600" iconClass="text-blue-400" />
        </div>
      </div>

      {/* ===== SKU Counts ===== */}
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">SKU Counts</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            title="SKU Count - Today"
            value={sku.today != null ? Number(sku.today).toLocaleString() : '-'}
            color="blue"
            icon={Package}
            variant="light"
          />
          <KpiCard
            title="SKU Count - MTD"
            value={sku.mtd != null ? Number(sku.mtd).toLocaleString() : '-'}
            color="purple"
            icon={BarChart3}
            variant="light"
          />
          <KpiCard
            title="SKU Count - YTD"
            value={sku.ytd != null ? Number(sku.ytd).toLocaleString() : '-'}
            color="green"
            icon={TrendingUp}
            variant="light"
          />
        </div>
      </div>

      {/* ===== SKU Performance Table ===== */}
      {data.sku_table && data.sku_table.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">SKU Performance</h2>
          <DataTable
            columns={[
              { key: 'item_code', label: 'Item Code' },
              { key: 'item_name', label: 'Item Name' },
              { key: 'category_name', label: 'Category' },
              { key: 'last_month_sales', label: 'Last Month Sales', format: 'currency' },
              { key: 'current_month_sales', label: 'Current Month Sales', format: 'currency' },
              { key: 'current_week_sales', label: 'Current Week Sales', format: 'currency' },
              {
                key: 'growth',
                label: 'Growth %',
                format: 'percent',
                render: (val) => {
                  const isPositive = val > 0;
                  const isNegative = val < 0;
                  const Icon = isPositive ? ArrowUpRight : ArrowDownRight;
                  return (
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                      isPositive ? 'bg-emerald-50 text-emerald-600' :
                      isNegative ? 'bg-rose-50 text-rose-500' :
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
    </div>
  );
}
