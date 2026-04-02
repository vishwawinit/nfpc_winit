import React, { useState, useEffect, useMemo, useRef } from 'react';
import { fetchRevenueDispersion } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import { BarChart3, Layers, TrendingUp, TrendingDown, Minus, ChevronLeft, ChevronRight, CalendarDays } from 'lucide-react';

const pctColor = (val) => {
  const n = parseFloat(val);
  if (isNaN(n)) return '';
  if (n >= 30) return 'bg-emerald-50 text-emerald-700 font-semibold';
  if (n >= 15) return 'bg-blue-50 text-blue-700 font-semibold';
  if (n >= 5) return 'bg-amber-50 text-amber-700 font-semibold';
  return 'text-gray-500';
};

function ChangeCell({ current, prev }) {
  const c = parseInt(current) || 0;
  const p = parseInt(prev) || 0;
  if (!current || !prev || current === '-' || prev === '-') {
    return <td className="px-3 py-3 text-center text-gray-300">—</td>;
  }
  const diff = c - p;
  if (p === 0) return <td className="px-3 py-3 text-center text-gray-300">—</td>;
  const pct = ((diff / p) * 100).toFixed(1);
  if (diff > 0) return (
    <td className="px-3 py-3 text-center">
      <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">
        <TrendingUp className="w-3 h-3" />+{pct}%
      </span>
    </td>
  );
  if (diff < 0) return (
    <td className="px-3 py-3 text-center">
      <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-red-500 bg-red-50 px-1.5 py-0.5 rounded">
        <TrendingDown className="w-3 h-3" />{pct}%
      </span>
    </td>
  );
  return (
    <td className="px-3 py-3 text-center">
      <span className="inline-flex items-center gap-0.5 text-xs text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded">
        <Minus className="w-3 h-3" />0%
      </span>
    </td>
  );
}

function PctBadge({ cell }) {
  if (!cell) return <td className="px-3 py-3 text-center text-gray-300">—</td>;
  return (
    <td className="px-3 py-3 text-center tabular-nums">
      <span className={`inline-block px-2 py-0.5 rounded-md text-xs ${pctColor(cell.pct)}`}>
        {Number(cell.pct).toFixed(1)}%
      </span>
    </td>
  );
}

function monthLabel(m) {
  if (!m || m === 'YTD') return 'YTD';
  const [y, mo] = m.split('-').map(Number);
  return new Date(y, mo - 1, 1).toLocaleString('default', { month: 'short' }) + ' ' + y;
}

const REVENUE_ORDER = ['0-200', '200-500', '500-1000', '1000-2500', '2500-5000', '5000+'];
const SKU_ORDER = ['0-5', '5-10', '10-15', '15-20', '20+'];

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTHS_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function getDateRange(ym) {
  const [y, m] = ym.split('-').map(Number);
  const now = new Date();
  const isCurrentMonth = y === now.getFullYear() && m === (now.getMonth() + 1);
  const date_from = `${ym}-01`;
  if (isCurrentMonth) {
    const d = String(now.getDate()).padStart(2, '0');
    return { date_from, date_to: `${ym}-${d}` };
  }
  const lastDay = new Date(y, m, 0).getDate();
  return { date_from, date_to: `${ym}-${String(lastDay).padStart(2, '0')}` };
}

function MonthPicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [viewYear, setViewYear] = useState(() => Number(value.split('-')[0]));
  const ref = useRef(null);

  const [selY, selM] = value.split('-').map(Number);
  const now = new Date();
  const maxY = now.getFullYear();
  const maxM = now.getMonth() + 1;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const select = (m) => {
    const ym = `${viewYear}-${String(m).padStart(2, '0')}`;
    onChange(ym);
    setOpen(false);
  };

  const displayLabel = `${MONTHS_FULL[selM - 1]} ${selY}`;

  return (
    <div className="relative" ref={ref}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => { setViewYear(selY); setOpen(o => !o); }}
        className={`flex items-center gap-2 pl-3 pr-4 py-2 rounded-xl border text-sm font-medium transition-all
          ${open
            ? 'bg-blue-600 text-white border-blue-600 shadow-md'
            : 'bg-white text-gray-700 border-gray-200 hover:border-blue-400 hover:text-blue-600 shadow-sm'
          }`}
      >
        <CalendarDays className="w-4 h-4 flex-shrink-0" />
        {displayLabel}
        <ChevronRight className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>

      {/* Calendar dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-2 z-50 bg-white rounded-2xl shadow-xl border border-gray-100 p-4 w-64"
          style={{ boxShadow: '0 12px 32px -4px rgba(0,0,0,0.15), 0 4px 12px -2px rgba(0,0,0,0.08)' }}>

          {/* Year navigation */}
          <div className="flex items-center justify-between mb-3">
            <button
              onClick={() => setViewYear(y => y - 1)}
              disabled={viewYear <= maxY - 4}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-30"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm font-bold text-gray-800">{viewYear}</span>
            <button
              onClick={() => setViewYear(y => y + 1)}
              disabled={viewYear >= maxY}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-30"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Month grid — 4 cols × 3 rows */}
          <div className="grid grid-cols-4 gap-1.5">
            {MONTHS.map((mn, idx) => {
              const mNum = idx + 1;
              const isSel = viewYear === selY && mNum === selM;
              const isToday = viewYear === maxY && mNum === maxM;
              const isFuture = viewYear === maxY && mNum > maxM || viewYear > maxY;
              return (
                <button
                  key={mn}
                  disabled={isFuture}
                  onClick={() => select(mNum)}
                  className={`py-1.5 rounded-lg text-xs font-semibold transition-all
                    ${isSel
                      ? 'bg-blue-600 text-white shadow-sm'
                      : isFuture
                        ? 'text-gray-200 cursor-not-allowed'
                        : isToday
                          ? 'bg-blue-50 text-blue-600 ring-1 ring-blue-200'
                          : 'text-gray-600 hover:bg-blue-50 hover:text-blue-600'
                    }`}
                >
                  {mn}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function RevenueDispersion() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('revenue');

  const [selectedYM, setSelectedYM] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });

  const [filters, setFilters] = useState({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const { date_from, date_to } = getDateRange(selectedYM);
    fetchRevenueDispersion({ date_from, date_to, ...filters })
      .then(res => { if (!cancelled) setData(res); })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedYM, filters]);

  const rows = activeTab === 'revenue' ? (data?.revenue_dispersion || []) : (data?.sku_dispersion || []);
  const rangeKey = activeTab === 'revenue' ? 'billing_range' : 'sku_range';
  const rangeOrder = activeTab === 'revenue' ? REVENUE_ORDER : SKU_ORDER;

  const selectedMonth = data?.selected_month;
  const prevMonth = data?.prev_month;
  const YTD = 'YTD';

  const ranges = useMemo(() => {
    const found = new Set(rows.map(r => r[rangeKey]));
    return rangeOrder.filter(r => found.has(r));
  }, [rows, rangeKey, rangeOrder]);

  const getCell = (range, month) => rows.find(r => r[rangeKey] === range && r.month === month);
  const totalFor = (month, field) =>
    rows.filter(r => r.month === month).reduce((s, r) => s + (parseInt(r[field]) || 0), 0);

  const { date_from, date_to } = getDateRange(selectedYM);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Revenue Dispersion</h1>
        <p className="text-sm text-gray-500 mt-1">Customer billing and SKU distribution — prev month vs current month vs YTD</p>
      </div>

      {/* Unified Filter Panel */}
      <div className="bg-white/70 border border-gray-200/60 rounded-xl p-4 pb-5 space-y-4">

        {/* Month picker + other filters in one block */}
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">
              Month
            </label>
            <MonthPicker value={selectedYM} onChange={setSelectedYM} />
          </div>
        </div>

        {/* Other filters (flat — no wrapper div) */}
        <FilterPanel
          flat
          filters={filters}
          onChange={setFilters}
          showFields={['sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']}
        />
      </div>

      {loading ? <Loading /> : !data ? (
        <div className="text-center py-20">
          <BarChart3 className="w-12 h-12 text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400 font-medium">No data available</p>
        </div>
      ) : (
        <>
          {/* Tab Toggle */}
          <div className="flex gap-1 bg-gray-100/80 rounded-xl p-1 w-fit">
            <button onClick={() => setActiveTab('revenue')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'revenue' ? 'bg-white shadow-sm text-blue-600 ring-1 ring-gray-200/50' : 'text-gray-500 hover:text-gray-700'
              }`}>
              <TrendingUp className="w-4 h-4" /> Revenue Dispersion
            </button>
            <button onClick={() => setActiveTab('sku')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'sku' ? 'bg-white shadow-sm text-blue-600 ring-1 ring-gray-200/50' : 'text-gray-500 hover:text-gray-700'
              }`}>
              <Layers className="w-4 h-4" /> SKU Dispersion
            </button>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80">
                    <th className="px-5 py-3.5 text-left text-xs text-gray-500 uppercase font-semibold tracking-wider sticky left-0 bg-gray-50/80 z-10" rowSpan={2}>
                      {activeTab === 'revenue' ? 'Billing Range (AED)' : 'SKU Range'}
                    </th>
                    <th colSpan={3} className="px-2 py-3 text-center text-xs font-semibold text-blue-600 uppercase tracking-wider border-l border-blue-200">
                      {monthLabel(selectedMonth)} <span className="font-normal text-blue-400">(Current)</span>
                    </th>
                    <th colSpan={4} className="px-2 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider border-l border-gray-200">
                      {monthLabel(prevMonth)} <span className="font-normal text-gray-400">(Prev)</span>
                    </th>
                    <th colSpan={3} className="px-2 py-3 text-center text-xs font-semibold text-violet-600 uppercase tracking-wider border-l border-violet-200">
                      YTD
                    </th>
                  </tr>
                  <tr className="bg-gray-50/50 border-b border-gray-200">
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-blue-400 uppercase border-l border-blue-100">Invoices</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-blue-400 uppercase">Customers</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-blue-400 uppercase">%</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase border-l border-gray-200">Invoices</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase">Customers</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase">%</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-gray-400 uppercase">Change</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-violet-400 uppercase border-l border-violet-100">Invoices</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-violet-400 uppercase">Customers</th>
                    <th className="px-3 py-2 text-center text-[11px] font-medium text-violet-400 uppercase">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {ranges.map((range) => {
                    const prev = getCell(range, prevMonth);
                    const curr = getCell(range, selectedMonth);
                    const ytd  = getCell(range, YTD);
                    return (
                      <tr key={range} className="hover:bg-blue-50/20 transition-colors">
                        <td className="px-5 py-3 font-semibold text-gray-700 whitespace-nowrap sticky left-0 bg-white z-10 border-r border-gray-100">
                          {range}
                        </td>
                        <td className="px-3 py-3 text-center text-gray-800 tabular-nums font-medium border-l border-blue-100">{curr?.invoice_count ?? '—'}</td>
                        <td className="px-3 py-3 text-center text-gray-800 tabular-nums font-medium">{curr?.customer_count ?? '—'}</td>
                        <PctBadge cell={curr} />
                        <td className="px-3 py-3 text-center text-gray-500 tabular-nums border-l border-gray-100">{prev?.invoice_count ?? '—'}</td>
                        <td className="px-3 py-3 text-center text-gray-500 tabular-nums">{prev?.customer_count ?? '—'}</td>
                        <PctBadge cell={prev} />
                        <ChangeCell current={curr?.customer_count} prev={prev?.customer_count} />
                        <td className="px-3 py-3 text-center text-violet-700 tabular-nums font-medium border-l border-violet-100">{ytd?.invoice_count ?? '—'}</td>
                        <td className="px-3 py-3 text-center text-violet-700 tabular-nums font-medium">{ytd?.customer_count ?? '—'}</td>
                        <PctBadge cell={ytd} />
                      </tr>
                    );
                  })}
                  {ranges.length === 0 && (
                    <tr>
                      <td colSpan={11} className="px-4 py-12 text-center">
                        <BarChart3 className="w-8 h-8 text-gray-200 mx-auto mb-2" />
                        <span className="text-gray-400">No dispersion data</span>
                      </td>
                    </tr>
                  )}
                </tbody>

                {ranges.length > 0 && (
                  <tfoot>
                    <tr className="bg-gray-50 border-t-2 border-gray-200 font-bold">
                      <td className="px-5 py-3 text-gray-700 sticky left-0 bg-gray-50 z-10">Total</td>
                      <td className="px-3 py-3 text-center text-gray-800 tabular-nums border-l border-blue-100">{totalFor(selectedMonth, 'invoice_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-gray-800 tabular-nums">{totalFor(selectedMonth, 'customer_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-gray-600">100%</td>
                      <td className="px-3 py-3 text-center text-gray-600 tabular-nums border-l border-gray-200">{totalFor(prevMonth, 'invoice_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-gray-600 tabular-nums">{totalFor(prevMonth, 'customer_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-gray-500">100%</td>
                      <ChangeCell
                        current={totalFor(selectedMonth, 'customer_count')}
                        prev={totalFor(prevMonth, 'customer_count')}
                      />
                      <td className="px-3 py-3 text-center text-violet-700 tabular-nums border-l border-violet-100">{totalFor(YTD, 'invoice_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-violet-700 tabular-nums">{totalFor(YTD, 'customer_count') || '—'}</td>
                      <td className="px-3 py-3 text-center text-violet-600">100%</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
