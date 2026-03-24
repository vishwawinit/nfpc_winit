import { useState, useEffect, useRef } from 'react';
import { fetchWeeklySalesReturns, fetchOrderDetails, fetchOrderItems } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Banknote, Percent, X } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '-';
const num = (v) => v != null ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '-';

const ACTION_BADGE = {
  Delivered: 'bg-green-100 text-green-700',
  Approved:  'bg-blue-100 text-blue-700',
  Pending:   'bg-yellow-100 text-yellow-700',
  Collected: 'bg-purple-100 text-purple-700',
  Rejected:  'bg-red-100 text-red-700',
  Unknown:   'bg-gray-100 text-gray-500',
};

// ── Order Items Modal ──────────────────────────────────────────────────────
function OrderItemsModal({ order, onClose }) {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchOrderItems(order.order_no)
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [order.order_no]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        className="relative bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Order Items</h2>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-[13px] text-gray-500">
              <span><span className="font-medium text-gray-700">Order No:</span> {order.order_no}</span>
              <span><span className="font-medium text-gray-700">Date:</span> {order.order_date}</span>
              <span><span className="font-medium text-gray-700">Salesman:</span> {order.salesman}</span>
              <span><span className="font-medium text-gray-700">Customer:</span> {order.customer}</span>
              <span><span className="font-medium text-gray-700">Route:</span> {order.route}</span>
              <span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${ACTION_BADGE[order.action] || ACTION_BADGE.Unknown}`}>
                  {order.action}
                </span>
              </span>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors ml-4">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        {/* Order summary row */}
        <div className="px-6 py-3 bg-gray-50/60 border-b border-gray-100 flex flex-wrap gap-6 text-[13px]">
          <span><span className="text-gray-500">Cases:</span> <span className="font-semibold text-gray-800">{num(order.qty_cases)}</span></span>
          <span><span className="text-gray-500">Pieces:</span> <span className="font-semibold text-gray-800">{num(order.qty_pieces)}</span></span>
          <span><span className="text-gray-500">Gross:</span> <span className="font-semibold text-gray-800">{aed(order.gross_amount)}</span></span>
          <span><span className="text-gray-500">Discount:</span> <span className="font-semibold text-red-600">-{aed(order.discount_amount)}</span></span>
          <span><span className="text-gray-500">Net:</span> <span className="font-semibold text-indigo-700">{aed(order.net_amount)}</span></span>
        </div>

        {/* Items table */}
        <div className="overflow-auto flex-1 p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loading /></div>
          ) : !items?.length ? (
            <div className="text-center py-12 text-gray-400 text-sm">No items found</div>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-gray-200">
                  {['#', 'Item Code', 'Item Name', 'Brand', 'Category', 'Cases', 'Pcs', 'Unit Price', 'Gross', 'Discount', 'Net'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                    <td className="py-2 px-3 text-gray-400">{item.line_no ?? i + 1}</td>
                    <td className="py-2 px-3 font-mono text-gray-600">{item.item_code}</td>
                    <td className="py-2 px-3 font-medium text-gray-800">{item.item_name}</td>
                    <td className="py-2 px-3 text-gray-600">{item.brand}</td>
                    <td className="py-2 px-3 text-gray-600">{item.category}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{num(item.qty_cases)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{num(item.qty_pieces)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{aed(item.base_price)}</td>
                    <td className="py-2 px-3 text-right tabular-nums">{aed(item.gross_amount)}</td>
                    <td className="py-2 px-3 text-right tabular-nums text-red-500">{aed(item.discount_amount)}</td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-indigo-700">{aed(item.net_amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-200 bg-gray-50/80">
                  <td colSpan={5} className="py-2 px-3 text-[11px] font-semibold text-gray-500 uppercase">Total</td>
                  <td className="py-2 px-3 text-right font-bold tabular-nums">{num(items.reduce((s, r) => s + r.qty_cases, 0))}</td>
                  <td className="py-2 px-3 text-right font-bold tabular-nums">{num(items.reduce((s, r) => s + r.qty_pieces, 0))}</td>
                  <td className="py-2 px-3" />
                  <td className="py-2 px-3 text-right font-bold tabular-nums">{aed(items.reduce((s, r) => s + r.gross_amount, 0))}</td>
                  <td className="py-2 px-3 text-right font-bold tabular-nums text-red-500">{aed(items.reduce((s, r) => s + r.discount_amount, 0))}</td>
                  <td className="py-2 px-3 text-right font-bold tabular-nums text-indigo-700">{aed(items.reduce((s, r) => s + r.net_amount, 0))}</td>
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function WeeklySalesReturns() {
  const [activeTab, setActiveTab] = useState('weekly');
  const [selectedOrder, setSelectedOrder] = useState(null);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const hasData = useRef(false);

  const [orders, setOrders] = useState(null);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const hasOrders = useRef(false);

  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const d = String(now.getDate()).padStart(2, '0');
    const m = String(now.getMonth() + 1).padStart(2, '0');
    return { date_from: `${y}-01-01`, date_to: `${y}-${m}-${d}` };
  });

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    fetchWeeklySalesReturns(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  useEffect(() => {
    if (activeTab !== 'orders') return;
    let cancelled = false;
    if (!hasOrders.current) setOrdersLoading(true);
    fetchOrderDetails(filters)
      .then(res => { if (!cancelled) { setOrders(res); hasOrders.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setOrdersLoading(false); });
    return () => { cancelled = true; };
  }, [filters, activeTab]);

  useEffect(() => { hasOrders.current = false; }, [filters]);

  const weekly = data?.weekly_data || [];
  const totals = data?.totals || {};
  const chartData = weekly.map(w => ({ ...w, label: `W${w.week_number}` }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Weekly Sales & Returns</h1>
        <p className="text-sm text-gray-500 mt-1">Compare weekly sales performance against returns</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Sales" value={aed(totals.total_sales)} color="blue" icon={TrendingUp} variant="solid" />
            <KpiCard title="Total Returns" value={aed(totals.total_returns)} color="red" icon={TrendingDown} variant="solid" />
            <KpiCard title="Net Amount" value={aed(totals.net_amount)} color="green" icon={Banknote} variant="solid" />
            <KpiCard title="Return %" value={totals.return_pct != null ? `${Number(totals.return_pct).toFixed(1)}%` : '-'} color="yellow" icon={Percent} variant="light" />
          </div>

          {/* Chart */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales vs Returns by Week</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} />
                <YAxis tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} />
                <Tooltip
                  formatter={(value) => aed(value)}
                  labelFormatter={(l) => `Week ${l.replace('W', '')}`}
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                />
                <Legend wrapperStyle={{ paddingTop: '16px' }} />
                <Bar dataKey="sales_amount" name="Sales" fill="#818cf8" radius={[6, 6, 0, 0]} />
                <Bar dataKey="return_amount" name="Returns" fill="#fca5a5" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Tabbed table section */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="flex border-b border-gray-100">
              {[{ id: 'weekly', label: 'Weekly Breakdown' }, { id: 'orders', label: 'Order Details' }].map(t => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-5 py-3 text-sm font-medium transition-colors border-b-2
                    ${activeTab === t.id ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {activeTab === 'weekly' && (
              <div className="p-6">
                <DataTable
                  columns={[
                    { key: 'year', label: 'Year' },
                    { key: 'week_number', label: 'Week' },
                    { key: 'week_start', label: 'Start Date' },
                    { key: 'week_end', label: 'End Date' },
                    { key: 'sales_amount', label: 'Sales', format: 'currency' },
                    { key: 'return_amount', label: 'Returns', format: 'currency' },
                    { key: 'net_amount', label: 'Net', format: 'currency' },
                    { key: 'return_pct', label: 'Return %', format: 'percent' },
                  ]}
                  data={weekly}
                  exportName="weekly-sales-returns"
                />
              </div>
            )}

            {activeTab === 'orders' && (
              ordersLoading ? <div className="p-6"><Loading /></div> : (
                <div className="p-6">
                  <DataTable
                    columns={[
                      { key: 'order_no', label: 'Order No' },
                      { key: 'salesman', label: 'Salesman' },
                      { key: 'customer', label: 'Customer' },
                      { key: 'order_date', label: 'Order Date' },
                      {
                        key: 'action',
                        label: 'Action',
                        render: (val, row) => (
                          <button
                            onClick={() => setSelectedOrder(row)}
                            className="inline-flex items-center px-3 py-1 rounded-lg text-xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors cursor-pointer"
                          >
                            View
                          </button>
                        ),
                      },
                    ]}
                    data={orders || []}
                    exportName="order-details"
                  />
                </div>
              )
            )}
          </div>
        </>
      )}

      {/* Order Items Modal */}
      {selectedOrder && (
        <OrderItemsModal order={selectedOrder} onClose={() => setSelectedOrder(null)} />
      )}
    </div>
  );
}
