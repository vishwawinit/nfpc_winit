import { useState, useEffect } from 'react';
import { fetchMtdWastage, fetchMtdWastageItems } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import DataTable from '../components/DataTable';
import { RotateCcw, ShieldAlert, TrendingDown, Eye, X, Package, Download } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';
const aedFull = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '-';

const TYPE_META = {
  gr:  { label: 'Good Return', color: 'bg-teal-50 text-teal-700', dot: 'bg-teal-500' },
  bad: { label: 'Bad Return',  color: 'bg-rose-50 text-rose-700', dot: 'bg-rose-500' },
};

export default function MtdWastage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${d}` };
  });

  const [modal, setModal] = useState({ open: false, loading: false, items: [], title: '', subtitle: '' });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchMtdWastage(filters)
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters]);

  const summary = data?.summary || {};
  const details = data?.details || [];

  // Flatten detail rows: one row per (date, customer) for Good Return and Bad Return
  const flatRows = [];
  for (const d of details) {
    if (d.gr_qty > 0 || d.gr_value > 0)
      flatRows.push({ date: d.date, customer_code: d.customer_code, customer_name: d.customer_name, return_type: 'gr', qty: d.gr_qty, amount: d.gr_value });
    if (d.bad_qty > 0 || d.bad_value > 0)
      flatRows.push({ date: d.date, customer_code: d.customer_code, customer_name: d.customer_name, return_type: 'bad', qty: d.bad_qty, amount: d.bad_value });
  }

  const exportItems = (items, row) => {
    const header = ['Item Code', 'Item Name', 'Qty', 'Amount'];
    const csv = [
      `Customer: ${row.customer_name?.trim() || row.customer_code}, Date: ${row.date}, Type: ${TYPE_META[row.return_type]?.label}`,
      header.join(','),
      ...items.map(r => [r.item_code, `"${r.item_name?.trim()}"`, r.qty, r.amount].join(',')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `wastage-${row.customer_code}-${row.date}-${row.return_type}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleRowExport = (row) => {
    fetchMtdWastageItems({ customer_code: row.customer_code, date_val: row.date, return_type: row.return_type })
      .then(res => exportItems(res.items || [], row))
      .catch(console.error);
  };

  const openModal = (row) => {
    setModal({ open: true, loading: true, items: [], _row: row, title: row.customer_name?.trim() || row.customer_code, subtitle: `${TYPE_META[row.return_type]?.label} — ${row.date}` });
    fetchMtdWastageItems({ customer_code: row.customer_code, date_val: row.date, return_type: row.return_type })
      .then(res => setModal(m => ({ ...m, loading: false, items: res.items || [] })))
      .catch(() => setModal(m => ({ ...m, loading: false })));
  };

  const closeModal = () => setModal(m => ({ ...m, open: false }));

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">MTD Wastage Summary</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Track expired and damaged inventory across customers</p>
        </div>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['date_from', 'date_to', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'customer', 'category', 'brand']} />

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400 font-medium">No data available</div>
      ) : (
        <>
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Total Returns */}
            <div className="bg-gradient-to-br from-violet-50 to-purple-50/60 border border-violet-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-violet-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-violet-100 flex items-center justify-center">
                    <TrendingDown className="w-4.5 h-4.5 text-violet-600" strokeWidth={1.75} />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-500/80">Total Returns</span>
                </div>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-violet-100 text-violet-600">
                  {summary.total_returns_pct != null ? `${summary.total_returns_pct}% of sales` : ''}
                </span>
              </div>
              <div className="text-[15px] sm:text-[20px] md:text-[23px] font-bold text-violet-700 tracking-tight whitespace-nowrap">{aed(summary.total_returns_value)}</div>
              <div className="mt-2 flex items-center gap-4 text-[12px] text-violet-500/70 font-medium">
                <span>Qty: <span className="font-bold text-violet-700">{summary.total_returns_qty?.toLocaleString() ?? '-'}</span></span>
                <span>Sales: <span className="font-bold text-violet-700">{aed(summary.total_sales)}</span></span>
              </div>
            </div>

            {/* Good Returns (GR) */}
            <div className="bg-gradient-to-br from-teal-50 to-emerald-50/60 border border-teal-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-teal-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-teal-100 flex items-center justify-center">
                    <RotateCcw className="w-4.5 h-4.5 text-teal-600" strokeWidth={1.75} />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-teal-500/80">Good Returns (GR)</span>
                </div>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-teal-100 text-teal-600">
                  {summary.gr_pct != null ? `${summary.gr_pct}% of returns` : ''}
                </span>
              </div>
              <div className="text-[15px] sm:text-[20px] md:text-[23px] font-bold text-teal-700 tracking-tight whitespace-nowrap">{aed(summary.gr_value)}</div>
              <div className="mt-2 flex items-center gap-4 text-[12px] text-teal-500/70 font-medium">
                <span>Qty: <span className="font-bold text-teal-700">{summary.gr_qty?.toLocaleString() ?? '-'}</span></span>
                <span className="text-teal-400/60 text-[11px]">Normal customer returns</span>
              </div>
            </div>

            {/* Bad Returns */}
            <div className="bg-gradient-to-br from-rose-50 to-red-50/60 border border-rose-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-rose-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-rose-100 flex items-center justify-center">
                    <ShieldAlert className="w-4.5 h-4.5 text-rose-600" strokeWidth={1.75} />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-rose-500/80">Bad Returns</span>
                </div>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-600">
                  {summary.bad_returns_pct != null ? `${summary.bad_returns_pct}% of returns` : ''}
                </span>
              </div>
              <div className="text-[15px] sm:text-[20px] md:text-[23px] font-bold text-rose-700 tracking-tight whitespace-nowrap">{aed(summary.bad_returns_value)}</div>
              <div className="mt-2 flex items-center gap-4 text-[12px] text-rose-500/70 font-medium">
                <span>Qty: <span className="font-bold text-rose-700">{summary.bad_returns_qty?.toLocaleString() ?? '-'}</span></span>
              </div>
            </div>
          </div>

          {/* Customer Breakdown Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Customer Breakdown</h2>
            <DataTable
              disableSort
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'customer_code', label: 'Code' },
                { key: 'customer_name', label: 'Customer', render: (v) => <span className="font-medium text-gray-800">{v?.trim()}</span> },
                {
                  key: 'return_type', label: 'Return Type',
                  render: (v) => {
                    const meta = TYPE_META[v];
                    if (!meta) return v;
                    return (
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${meta.color}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        {meta.label}
                      </span>
                    );
                  }
                },
                { key: 'qty', label: 'Return Qty', format: 'number' },
                { key: 'amount', label: 'Return Amount', format: 'currency2' },
                {
                  key: '_action', label: 'Action',
                  render: (_, row) => (
                    <div className="flex items-center gap-1">
                      <button onClick={() => openModal(row)} title="View Items"
                        className="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 transition-colors">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleRowExport(row)} title="Export"
                        className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors">
                        <Download className="w-4 h-4" />
                      </button>
                    </div>
                  )
                },
              ]}
              data={flatRows}
              exportName="mtd-wastage"
            />
          </div>
        </>
      )}

      {/* Item Detail Modal */}
      {modal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeModal} />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <div className="flex items-center gap-2 mb-0.5">
                  <Package className="w-4 h-4 text-indigo-500" />
                  <span className="text-[13px] font-semibold text-gray-800">{modal.title}</span>
                </div>
                <span className="text-[12px] text-gray-400">{modal.subtitle}</span>
              </div>
              <div className="flex items-center gap-2">
                {!modal.loading && modal.items.length > 0 && (
                  <button
                    onClick={() => exportItems(modal.items, modal._row)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export
                  </button>
                )}
                <button onClick={closeModal} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
                  <X className="w-4 h-4 text-gray-400" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="overflow-y-auto flex-1">
              {modal.loading ? (
                <div className="flex items-center justify-center py-16 text-gray-400 text-[13px]">Loading items...</div>
              ) : modal.items.length === 0 ? (
                <div className="flex items-center justify-center py-16 text-gray-400 text-[13px]">No items found</div>
              ) : (
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="px-5 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider">#</th>
                      <th className="px-5 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Item Code</th>
                      <th className="px-5 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Item Name</th>
                      <th className="px-5 py-3 text-right text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Qty</th>
                      <th className="px-5 py-3 text-right text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50/80">
                    {modal.items.map((item, i) => (
                      <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}>
                        <td className="px-5 py-2.5 text-gray-400 tabular-nums">{i + 1}</td>
                        <td className="px-5 py-2.5 text-gray-500 font-mono text-[12px]">{item.item_code}</td>
                        <td className="px-5 py-2.5 text-gray-700 font-medium">{item.item_name?.trim()}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums text-gray-700">{Number(item.qty).toLocaleString()}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums font-semibold text-gray-800">{aedFull(item.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-gray-50 border-t border-gray-200">
                      <td colSpan={3} className="px-5 py-3 text-[12px] font-semibold text-gray-500">{modal.items.length} items</td>
                      <td className="px-5 py-3 text-right tabular-nums text-[12px] font-bold text-gray-700">
                        {modal.items.reduce((s, r) => s + r.qty, 0).toLocaleString()}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-[12px] font-bold text-gray-800">
                        {aedFull(modal.items.reduce((s, r) => s + r.amount, 0))}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
