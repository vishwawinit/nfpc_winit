import { useState, useEffect, useRef } from 'react';
import { fetchOutstandingCollection, fetchOutstandingInvoices } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import DataTable from '../components/DataTable';
import { X, Clock, AlertCircle, Users, FileText, Banknote, TrendingUp } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function OutstandingCollection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState({ year: new Date().getFullYear() });
  const [selectedBucket, setSelectedBucket] = useState(null);
  const [invoiceCustomer, setInvoiceCustomer] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [invoiceLoading, setInvoiceLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchOutstandingCollection({ ...filters, ...(selectedBucket ? { bucket: selectedBucket } : {}) })
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters, selectedBucket]);

  const handleInvoiceDrill = (customer) => {
    setInvoiceCustomer(customer);
    setInvoiceLoading(true);
    fetchOutstandingInvoices({ ...filters, customer: customer.customer_code })
      .then(res => setInvoices(Array.isArray(res) ? res : []))
      .catch(console.error)
      .finally(() => setInvoiceLoading(false));
  };

  const buckets = data?.aging_buckets || [];
  const customers = data?.customers || [];
  const totalOutstanding = buckets.reduce((s, b) => s + (Number(b.amount) || 0), 0);
  const totalCustomers = buckets.reduce((s, b) => s + (Number(b.customer_count) || 0), 0);

  const bucketConfig = {
    'Current':  { label: 'Current',      bg: 'bg-emerald-50', text: 'text-emerald-700', ring: 'ring-emerald-300', icon: 'bg-emerald-100 text-emerald-600', accent: 'bg-emerald-500' },
    '1-30':     { label: '1-30 Days',    bg: 'bg-blue-50',    text: 'text-blue-700',    ring: 'ring-blue-300',    icon: 'bg-blue-100 text-blue-600',       accent: 'bg-blue-500' },
    '31-60':    { label: '31-60 Days',   bg: 'bg-indigo-50',  text: 'text-indigo-700',  ring: 'ring-indigo-300',  icon: 'bg-indigo-100 text-indigo-600',   accent: 'bg-indigo-500' },
    '61-90':    { label: '61-90 Days',   bg: 'bg-amber-50',   text: 'text-amber-700',   ring: 'ring-amber-300',   icon: 'bg-amber-100 text-amber-600',     accent: 'bg-amber-500' },
    '91-120':   { label: '91-120 Days',  bg: 'bg-orange-50',  text: 'text-orange-700',  ring: 'ring-orange-300',  icon: 'bg-orange-100 text-orange-600',   accent: 'bg-orange-500' },
    '120+':     { label: '120+ Days',    bg: 'bg-violet-50',  text: 'text-violet-700',  ring: 'ring-violet-300',  icon: 'bg-violet-100 text-violet-600',   accent: 'bg-violet-500' },
  };
  const defaultBucket = { label: 'Other', bg: 'bg-slate-50', text: 'text-slate-700', ring: 'ring-slate-300', icon: 'bg-slate-100 text-slate-600', accent: 'bg-slate-500' };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Outstanding Collection</h1>
          <p className="text-[13px] text-gray-400 mt-0.5 font-medium">Aging analysis and customer-level outstanding balances</p>
        </div>
      </div>

      {/* Filters — always mounted */}
      <FilterPanel filters={filters} onChange={(f) => { setFilters(f); setSelectedBucket(null); }}
        showFields={['year', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {/* Refreshing indicator */}
      {refreshing && (
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-indigo-500 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {/* Data area */}
      {loading && !data ? <Loading /> : !data || !buckets.length ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100/80 p-12 text-center">
          <AlertCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400 font-medium">No outstanding collection data available</p>
        </div>
      ) : (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="kpi-card bg-gradient-to-br from-indigo-50 to-blue-50/60 border border-indigo-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-indigo-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center shadow-sm">
                  <Banknote className="w-5 h-5 text-indigo-600" strokeWidth={1.75} />
                </div>
                <div>
                  <div className="text-[11px] font-semibold text-indigo-500/80 uppercase tracking-wider">Total Outstanding</div>
                  <div className="text-[22px] font-bold text-indigo-700 tracking-tight tabular-nums">{aed(totalOutstanding)}</div>
                </div>
              </div>
            </div>
            <div className="kpi-card bg-gradient-to-br from-violet-50 to-purple-50/60 border border-violet-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-violet-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-violet-100 flex items-center justify-center shadow-sm">
                  <Users className="w-5 h-5 text-violet-600" strokeWidth={1.75} />
                </div>
                <div>
                  <div className="text-[11px] font-semibold text-violet-500/80 uppercase tracking-wider">Total Customers</div>
                  <div className="text-[22px] font-bold text-violet-700 tracking-tight tabular-nums">{totalCustomers.toLocaleString()}</div>
                </div>
              </div>
            </div>
            <div className="kpi-card bg-gradient-to-br from-emerald-50 to-teal-50/60 border border-emerald-100/80 rounded-2xl shadow-sm p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-emerald-500 opacity-40 rounded-t-2xl" />
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center shadow-sm">
                  <TrendingUp className="w-5 h-5 text-emerald-600" strokeWidth={1.75} />
                </div>
                <div>
                  <div className="text-[11px] font-semibold text-emerald-500/80 uppercase tracking-wider">Aging Buckets</div>
                  <div className="text-[22px] font-bold text-emerald-700 tracking-tight tabular-nums">{buckets.length}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Aging Bucket Cards */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider">Aging Buckets</h2>
              {selectedBucket && (
                <button onClick={() => setSelectedBucket(null)}
                  className="text-[12px] font-medium text-indigo-600 hover:text-indigo-800 transition-colors">
                  Clear filter
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {buckets.map((b) => {
                const cfg = bucketConfig[b.bucket] || defaultBucket;
                const isActive = selectedBucket === b.bucket;
                return (
                  <div key={b.bucket}
                    onClick={() => setSelectedBucket(isActive ? null : b.bucket)}
                    className={`kpi-card ${cfg.bg} rounded-2xl shadow-sm p-4 cursor-pointer transition-all duration-200 hover:shadow-md relative overflow-hidden ${
                      isActive ? `ring-2 ${cfg.ring} shadow-md` : 'border border-gray-100/80'
                    }`}>
                    <div className={`absolute top-0 left-0 right-0 h-[2px] ${cfg.accent} opacity-50 rounded-t-2xl`} />
                    <div className="flex items-center gap-2 mb-3">
                      <div className={`w-8 h-8 rounded-lg ${cfg.icon} flex items-center justify-center`}>
                        <Clock className="w-3.5 h-3.5" strokeWidth={2} />
                      </div>
                      <span className={`text-[10px] font-semibold uppercase tracking-wider ${cfg.text} opacity-80`}>{cfg.label}</span>
                    </div>
                    <div className={`text-[17px] font-bold tabular-nums ${cfg.text}`}>{aed(b.amount)}</div>
                    <div className="flex items-center gap-1 mt-2">
                      <Users className="w-3 h-3 text-gray-400" />
                      <span className="text-[10px] text-gray-500 font-medium">{b.customer_count} customers</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Customer Table */}
          <div>
            <h2 className="text-[13px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Customer Outstanding {selectedBucket ? `- ${selectedBucket}` : ''}
            </h2>
            <DataTable
              columns={[
                { key: 'customer_code', label: 'Code' },
                { key: 'customer_name', label: 'Customer' },
                { key: 'invoice_count', label: 'Invoices', format: 'number' },
                { key: 'pending_amount', label: 'Pending Amount', format: 'currency' },
              ]}
              data={customers}
              onRowClick={handleInvoiceDrill}
              exportName="outstanding-collection"
            />
          </div>

          {/* Invoice Drill-down Modal */}
          {invoiceCustomer && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
              onClick={() => { setInvoiceCustomer(null); setInvoices([]); }}>
              <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[80vh] overflow-hidden border border-gray-100"
                onClick={e => e.stopPropagation()}>
                <div className="p-5 border-b border-gray-100 flex justify-between items-center">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-800">{invoiceCustomer.customer_name}</h3>
                      <span className="text-[11px] text-gray-400">{invoiceCustomer.customer_code} - {aed(invoiceCustomer.pending_amount)} outstanding</span>
                    </div>
                  </div>
                  <button onClick={() => { setInvoiceCustomer(null); setInvoices([]); }}
                    className="w-8 h-8 rounded-lg bg-gray-100 hover:bg-gray-200 flex items-center justify-center transition-colors">
                    <X className="w-4 h-4 text-gray-500" />
                  </button>
                </div>
                <div className="p-5 overflow-auto max-h-[65vh]">
                  {invoiceLoading ? <Loading /> : (
                    <DataTable
                      columns={[
                        { key: 'trx_code', label: 'Invoice #' },
                        { key: 'trx_date', label: 'Date' },
                        { key: 'due_date', label: 'Due Date' },
                        { key: 'original_amount', label: 'Original', format: 'currency' },
                        { key: 'balance_amount', label: 'Balance', format: 'currency' },
                        { key: 'days_overdue', label: 'Days Overdue', format: 'number' },
                        { key: 'aging_bucket', label: 'Bucket' },
                      ]}
                      data={invoices}
                      exportName={`invoices-${invoiceCustomer.customer_code}`}
                    />
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
