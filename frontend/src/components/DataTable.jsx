import { useState } from 'react';
import { Search, Download, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

export default function DataTable({ columns, data, onRowClick, exportName }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [search, setSearch] = useState('');

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  };

  let filtered = data;
  if (search) {
    const s = search.toLowerCase();
    filtered = data.filter(row =>
      columns.some(c => String(row[c.key] ?? '').toLowerCase().includes(s))
    );
  }

  if (sortCol) {
    filtered = [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }

  const exportCsv = () => {
    const header = columns.map(c => c.label).join(',');
    const rows = filtered.map(row => columns.map(c => {
      const v = row[c.key] ?? '';
      return typeof v === 'string' && v.includes(',') ? `"${v}"` : v;
    }).join(','));
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `${exportName || 'export'}.csv`;
    a.click(); URL.revokeObjectURL(url);
  };

  const fmt = (val, col) => {
    if (val == null) return <span className="text-gray-300">-</span>;
    if (col.format === 'number') return Number(val).toLocaleString('en-US', { maximumFractionDigits: 2 });
    if (col.format === 'currency') return Number(val).toLocaleString('en-US', { style: 'currency', currency: 'AED', maximumFractionDigits: 0 });
    if (col.format === 'percent') return Number(val).toFixed(1) + '%';
    return val;
  };

  const SortIcon = ({ colKey }) => {
    if (sortCol !== colKey) return <ArrowUpDown className="w-3 h-3 text-gray-300" />;
    return sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 text-indigo-500" />
      : <ArrowDown className="w-3 h-3 text-indigo-500" />;
  };

  return (
    <div className="bg-white border border-gray-100/80 rounded-2xl shadow-sm overflow-hidden card-enterprise">
      {/* Toolbar */}
      <div className="px-5 py-3.5 flex items-center justify-between border-b border-gray-100/80 gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search records..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-[7px] text-[13px] bg-gray-50/80 border border-gray-200/80 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/15 focus:border-indigo-400 transition-all duration-150 hover:border-gray-300"
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-semibold text-gray-400 bg-gray-50 px-2.5 py-1 rounded-full tabular-nums">
            {filtered.length} rows
          </span>
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-1.5 text-[13px] font-semibold bg-indigo-600 text-white px-4 py-[7px] rounded-lg hover:bg-indigo-700 active:bg-indigo-800 transition-all duration-150 shadow-sm shadow-indigo-600/10"
          >
            <Download className="w-3.5 h-3.5" strokeWidth={2} />
            Export
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-gray-50/60 border-b border-gray-100/80">
              {columns.map(col => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100/60 hover:text-gray-600 whitespace-nowrap transition-colors duration-150 select-none sticky top-0 bg-gray-50/60"
                >
                  <div className="inline-flex items-center gap-1.5">
                    {col.label}
                    <SortIcon colKey={col.key} />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50/80">
            {filtered.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick?.(row)}
                className={`transition-colors duration-100 ${
                  i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                } hover:bg-indigo-50/40 ${onRowClick ? 'cursor-pointer' : ''}`}
              >
                {columns.map(col => (
                  <td
                    key={col.key}
                    className={`px-4 py-2.5 whitespace-nowrap text-gray-700 ${
                      col.format === 'number' || col.format === 'currency' || col.format === 'percent'
                        ? 'text-right tabular-nums font-medium'
                        : ''
                    }`}
                  >
                    {fmt(row[col.key], col)}
                  </td>
                ))}
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-16 text-center text-gray-400">
                  <div className="text-base font-semibold text-gray-500">No data found</div>
                  <div className="text-[13px] mt-1 text-gray-400">Try adjusting your search or filters</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
