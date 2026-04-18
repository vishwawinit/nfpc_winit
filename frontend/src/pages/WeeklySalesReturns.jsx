import { useState, useEffect } from 'react';
import { fetchWeeklySalesReturns, fetchOrderDetails, fetchOrderDetailsExport, fetchOrderItems } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LabelList } from 'recharts';
import { TrendingUp, TrendingDown, Banknote, Percent, X, Eye, Download } from 'lucide-react';

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

  const [ordersBuffer, setOrdersBuffer] = useState([]);
  const [ordersTotal, setOrdersTotal] = useState(0);
  const [ordersDisplaySize] = useState(25);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const ORDERS_FETCH_SIZE = 500;

  const defaultFilters = () => {
    const now = new Date();
    const y = now.getFullYear();
    const d = String(now.getDate()).padStart(2, '0');
    const m = String(now.getMonth() + 1).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  };
  const [filters, setFilters] = useState(defaultFilters);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchWeeklySalesReturns(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  // Fetch initial 500 records when filters or tab changes
  useEffect(() => {
    if (activeTab !== 'orders') return;
    let cancelled = false;
    setOrdersLoading(true);
    setOrdersBuffer([]);
    fetchOrderDetails({ ...filters, page: 1, page_size: ORDERS_FETCH_SIZE })
      .then(res => {
        if (!cancelled) {
          setOrdersBuffer(res.orders || []);
          setOrdersTotal(res.total || 0);
        }
      })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setOrdersLoading(false); });
    return () => { cancelled = true; };
  }, [filters, activeTab]);


  const handleExport = () => {
    setExporting(true);
    fetchOrderDetailsExport(filters)
      .then(rows => {
        const cols = ['order_no','route_code','salesman_code','salesman','customer_code','customer','order_date','route','qty_cases','qty_pieces','gross_amount','discount_amount','net_amount','action'];
        const header = ['Order No','Route Code','Salesman Code','Salesman','Customer Code','Customer','Order Date','Route','Cases','Pieces','Gross','Discount','Net','Action'];
        const csv = [header.join(','), ...rows.map(r => cols.map(k => {
          const v = r[k] ?? '';
          return typeof v === 'string' && v.includes(',') ? `"${v}"` : v;
        }).join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'order-details.csv';
        a.click(); URL.revokeObjectURL(url);
      })
      .catch(console.error)
      .finally(() => setExporting(false));
  };

  const handleRowDownload = (row) => {
    fetchOrderItems(row.order_no).then(items => {
      const cols = ['line_no','item_code','item_name','brand','category','qty_cases','qty_pieces','base_price','gross_amount','discount_amount','net_amount'];
      const header = ['Line','Item Code','Item Name','Brand','Category','Cases','Pieces','Unit Price','Gross','Discount','Net'];
      const csv = [
        `Order No: ${row.order_no},Date: ${row.order_date},Customer: ${row.customer},Salesman: ${row.salesman}`,
        header.join(','),
        ...items.map(r => cols.map(k => { const v = r[k] ?? ''; return typeof v === 'string' && v.includes(',') ? `"${v}"` : v; }).join(','))
      ].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${row.order_no}.csv`;
      a.click(); URL.revokeObjectURL(url);
    }).catch(console.error);
  };

  const weekly = data?.weekly_data || [];
  const totals = data?.totals || {};
  const chartData = weekly.map(w => ({ ...w, label: `W${w.week_number}` }));

  const ordersPageLoading = ordersLoading && ordersBuffer.length === 0;

  const handleOrdersPageChange = (page, pageSize) => {
    const needed = page * pageSize;
    if (needed >= ordersBuffer.length && ordersBuffer.length < ordersTotal && !ordersLoading && ordersBuffer.length > 0) {
      const nextPage = Math.floor(ordersBuffer.length / ORDERS_FETCH_SIZE) + 1;
      setOrdersLoading(true);
      fetchOrderDetails({ ...filters, page: nextPage, page_size: ORDERS_FETCH_SIZE })
        .then(res => {
          setOrdersBuffer(prev => [...prev, ...(res.orders || [])]);
          setOrdersTotal(res.total || 0);
        })
        .catch(console.error)
        .finally(() => setOrdersLoading(false));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Weekly Sales & Returns</h1>
        <p className="text-sm text-gray-500 mt-1">Compare weekly sales performance against returns</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        onReset={() => setFilters(defaultFilters())}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'customer', 'brand', 'category']}
        rowBreakBefore={['route']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Total Sales" value={aed(totals.total_sales)} color="blue" icon={TrendingUp} variant="solid" />
            <KpiCard title="Total Returns" value={aed(totals.total_returns)} color="red" icon={TrendingDown} variant="solid" />
            <KpiCard title="Net Amount" value={aed(totals.net_amount)} color="green" icon={Banknote} variant="solid" />
            <KpiCard title="Return" value={totals.return_pct != null ? `${Number(totals.return_pct).toFixed(1)}` : '-'} color="yellow" icon={Percent} variant="light" />
          </div>

          {/* Chart */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Sales vs Returns by Week</h2>
            <ResponsiveContainer width="100%" height={380}>
              <BarChart data={chartData} margin={{ top: 20, right: 20, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} />
                <YAxis tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={{ stroke: '#e5e7eb' }} tickFormatter={(v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : v} />
                <Tooltip
                  formatter={(value) => aed(value)}
                  labelFormatter={(l) => `Week ${l.replace('W', '')}`}
                  contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                />
                <Legend wrapperStyle={{ paddingTop: '16px' }} />
                <Bar dataKey="sales_amount" name="Sales" fill="#818cf8" radius={[6, 6, 0, 0]}>
                  <LabelList dataKey="sales_amount" position="top" formatter={(v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : v} style={{ fontSize: 10, fill: '#6366f1', fontWeight: 700 }} />
                </Bar>
                <Bar dataKey="return_amount" name="Returns" fill="#fca5a5" radius={[6, 6, 0, 0]}>
                  <LabelList dataKey="return_amount" position="top" formatter={(v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : v} style={{ fontSize: 10, fill: '#f87171', fontWeight: 700 }} />
                </Bar>
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
              <div className="p-6 space-y-3">
                {ordersPageLoading ? <Loading /> : (
                  <>
                    <DataTable
                      columns={[
                        { key: 'order_date', label: 'Order Date' },
                        { key: 'order_no', label: 'Order No' },
                        { key: 'route_code', label: 'Route Code' },
                        { key: 'salesman_code', label: 'Salesman Code' },
                        { key: 'salesman', label: 'Salesman' },
                        { key: 'customer_code', label: 'Customer Code' },
                        { key: 'customer', label: 'Customer' },
                        { key: 'route', label: 'Route' },
                        { key: 'gross_amount', label: 'Gross', format: 'currency' },
                        { key: 'discount_amount', label: 'Discount', format: 'currency' },
                        { key: 'net_amount', label: 'Net', format: 'currency' },
                        {
                          key: '_actions',
                          label: 'Action',
                          render: (_, row) => (
                            <div className="flex items-center gap-2">
                              <button onClick={() => setSelectedOrder(row)} title="View items"
                                className="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 transition-colors">
                                <Eye className="w-4 h-4" />
                              </button>
                              <button onClick={() => handleRowDownload(row)} title="Download order"
                                className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors">
                                <Download className="w-4 h-4" />
                              </button>
                            </div>
                          ),
                        },
                      ]}
                      data={ordersBuffer}
                      disableSort
                      exportName={null}
                      pageSize={ordersDisplaySize}
                      serverTotal={ordersTotal}
                      onExportAll={handleExport}
                      exportingAll={exporting}
                      onPageChange={handleOrdersPageChange}
                    />
                  </>
                )}
              </div>
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
