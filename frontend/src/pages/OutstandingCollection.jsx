import { useState, useEffect } from 'react';
import { fetchOutstandingCollection, fetchOutstandingInvoices } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import DataTable from '../components/DataTable';
import { X, Clock, AlertCircle, Users, FileText } from 'lucide-react';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

export default function OutstandingCollection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({});
  const [selectedBucket, setSelectedBucket] = useState(null);
  const [invoiceCustomer, setInvoiceCustomer] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [invoiceLoading, setInvoiceLoading] = useState(false);

  useEffect(() => {
    if (!filters.sales_org) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchOutstandingCollection(filters).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [filters]);

  const handleInvoiceDrill = (customer) => {
    setInvoiceCustomer(customer);
    setInvoiceLoading(true);
    fetchOutstandingInvoices({ ...filters, customer_code: customer.customer_code })
      .then(res => setInvoices(Array.isArray(res) ? res : []))
      .catch(console.error)
      .finally(() => setInvoiceLoading(false));
  };

  const buckets = data?.aging_buckets || [];
  const customers = data?.customers || [];

  const bucketStyles = [
    { border: 'border-emerald-400', bg: 'bg-emerald-50', text: 'text-emerald-700', ring: 'ring-emerald-300', icon: 'text-emerald-500' },
    { border: 'border-blue-400', bg: 'bg-blue-50', text: 'text-blue-700', ring: 'ring-blue-300', icon: 'text-blue-500' },
    { border: 'border-amber-400', bg: 'bg-amber-50', text: 'text-amber-700', ring: 'ring-amber-300', icon: 'text-amber-500' },
    { border: 'border-orange-400', bg: 'bg-orange-50', text: 'text-orange-700', ring: 'ring-orange-300', icon: 'text-orange-500' },
    { border: 'border-rose-400', bg: 'bg-rose-50', text: 'text-rose-700', ring: 'ring-rose-300', icon: 'text-rose-500' },
    { border: 'border-violet-400', bg: 'bg-violet-50', text: 'text-violet-700', ring: 'ring-violet-300', icon: 'text-violet-500' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Outstanding Collection</h1>
        <p className="text-sm text-gray-500 mt-1">Aging analysis and customer-level outstanding balances</p>
      </div>

      <FilterPanel filters={filters} onChange={setFilters}
        showFields={['sales_org', 'user_code', 'route']} />

      {!filters.sales_org ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
          <AlertCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400 font-medium">Please select a Sales Org to view outstanding collection data</p>
        </div>
      ) : loading ? <Loading /> : !data ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* Aging Bucket Cards */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Aging Buckets</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {buckets.map((b, i) => {
                const style = bucketStyles[i % bucketStyles.length];
                const isActive = selectedBucket === b.bucket;
                return (
                  <div key={i}
                    onClick={() => setSelectedBucket(isActive ? null : b.bucket)}
                    className={`bg-white rounded-2xl shadow-sm border-l-4 ${style.border} p-5 cursor-pointer transition-all duration-200 hover:shadow-md ${
                      isActive ? `ring-2 ${style.ring} shadow-md` : 'border border-gray-100'
                    }`}>
                    <div className="flex items-center gap-2 mb-2">
                      <Clock className={`w-3.5 h-3.5 ${style.icon}`} />
                      <span className={`text-xs font-semibold uppercase ${style.text}`}>{b.bucket}</span>
                    </div>
                    <div className="text-xl font-bold text-gray-800 mt-1">{aed(b.amount)}</div>
                    <div className="flex items-center gap-1 mt-2">
                      <Users className="w-3 h-3 text-gray-400" />
                      <span className="text-xs text-gray-500">{b.customer_count} customers</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Customer Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Customer Outstanding</h2>
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
                      <span className="text-xs text-gray-400">{invoiceCustomer.customer_code}</span>
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
                        { key: 'invoice_number', label: 'Invoice #' },
                        { key: 'invoice_date', label: 'Date' },
                        { key: 'due_date', label: 'Due Date' },
                        { key: 'invoice_amount', label: 'Amount', format: 'currency' },
                        { key: 'pending_amount', label: 'Pending', format: 'currency' },
                        { key: 'days_overdue', label: 'Days Overdue', format: 'number' },
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
