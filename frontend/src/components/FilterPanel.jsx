import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchFilters } from '../api';
import {
  Calendar, Building2, Route, User, Radio, Tag, Layers, Hash, CalendarDays,
  Warehouse, Users, ChevronDown, X, Check, Shield, Crown
} from 'lucide-react';

const fieldMeta = {
  date_from: { label: 'From', icon: Calendar, type: 'date' },
  date_to: { label: 'To', icon: Calendar, type: 'date' },
  sales_org: { label: 'Sales Org', icon: Building2, multi: true },
  hos: { label: 'HOS', icon: Crown, multi: true },
  asm: { label: 'ASM', icon: Shield, multi: true },
  depot: { label: 'Depot', icon: Warehouse, multi: true },
  supervisor: { label: 'Supervisor', icon: Users, multi: true },
  user_code: { label: 'Salesman', icon: User, multi: true },
  route: { label: 'Route', icon: Route, multi: true },
  channel: { label: 'Channel', icon: Radio, multi: true },
  brand: { label: 'Brand', icon: Tag, multi: true },
  category: { label: 'Category', icon: Layers, multi: true },
  day: { label: 'Day', icon: Calendar, type: 'day' },
  month: { label: 'Month', icon: CalendarDays, type: 'month' },
  year: { label: 'Year', icon: Hash, type: 'year' },
};

/* Hierarchy: sales_org → hos → asm → supervisor → user_code → route
                                       depot ──────┘              │
                                                                   route depends on all above */
const CHILD_MAP = {
  sales_org: ['hos', 'asm', 'depot', 'supervisor', 'user_code', 'route'],
  hos:       ['asm', 'depot', 'supervisor', 'user_code', 'route'],
  asm:       ['supervisor', 'user_code', 'route'],
  depot:     ['user_code', 'route'],
  supervisor:['user_code', 'route'],
  user_code: ['route'],
};

function MultiSelect({ options, value, onChange, placeholder = 'All', loading = false }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const btnRef = useRef(null);
  const dropRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 });
  const selected = value ? value.split(',').filter(Boolean) : [];

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (btnRef.current?.contains(e.target)) return;
      if (dropRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  useEffect(() => {
    if (!open || !btnRef.current) return;
    const reposition = () => {
      const rect = btnRef.current.getBoundingClientRect();
      const dropH = 300;
      const spaceBelow = window.innerHeight - rect.bottom - 8;
      const openAbove = spaceBelow < dropH && rect.top > dropH;
      setPos({
        top: openAbove ? rect.top - dropH - 4 : rect.bottom + 4,
        left: rect.left,
        width: Math.max(rect.width, 240),
      });
    };
    reposition();
    const main = document.querySelector('main');
    const close = () => setOpen(false);
    main?.addEventListener('scroll', close, { passive: true });
    window.addEventListener('resize', reposition);
    return () => {
      main?.removeEventListener('scroll', close);
      window.removeEventListener('resize', reposition);
    };
  }, [open]);

  const toggle = (code) => {
    const s = new Set(selected);
    if (s.has(code)) s.delete(code); else s.add(code);
    onChange(s.size ? [...s].join(',') : undefined);
  };

  const clear = (e) => { e.stopPropagation(); onChange(undefined); };

  const filtered = search
    ? options.filter(o => (o.name || o.code || '').toLowerCase().includes(search.toLowerCase())
        || (o.code || '').toLowerCase().includes(search.toLowerCase()))
    : options;

  const displayText = selected.length === 0 ? placeholder
    : selected.length === 1 ? (options.find(o => o.code === selected[0])?.name || selected[0])
    : `${selected.length} selected`;

  return (
    <div>
      <button
        ref={btnRef}
        type="button"
        onClick={() => { setOpen(!open); setSearch(''); }}
        className={`w-full bg-white border rounded-lg px-3 py-[7px] text-[13px] text-gray-700
          focus:outline-none focus:ring-2 focus:ring-indigo-500/15 focus:border-indigo-400
          transition-all duration-150 flex items-center justify-between gap-1 hover:border-gray-300
          ${open ? 'border-indigo-400 ring-2 ring-indigo-500/15' : ''}
          ${loading ? 'border-gray-200/60 opacity-60' : 'border-gray-200/80'}`}
        disabled={loading}
      >
        <span className={`truncate ${selected.length === 0 ? 'text-gray-400' : 'font-medium'}`}>
          {loading ? 'Loading...' : displayText}
        </span>
        <span className="flex items-center gap-1 flex-shrink-0">
          {selected.length > 0 && (
            <span className="w-4 h-4 rounded-full bg-gray-100 hover:bg-red-50 inline-flex items-center justify-center" onClick={clear}>
              <X className="w-2.5 h-2.5 text-gray-400" />
            </span>
          )}
          <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>

      {open && (
        <div
          ref={dropRef}
          style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width, zIndex: 9999 }}
        >
          <div
            className="bg-white border border-gray-200 rounded-xl overflow-hidden"
            style={{ boxShadow: '0 12px 28px -4px rgba(0,0,0,0.14), 0 4px 10px -2px rgba(0,0,0,0.06)' }}
          >
            {options.length > 5 && (
              <div className="p-2 border-b border-gray-100 bg-gray-50/40">
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Type to search..."
                  className="w-full text-[13px] border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-colors placeholder:text-gray-400"
                  autoFocus
                />
              </div>
            )}

            {selected.length > 0 && (
              <div className="px-3 py-1.5 bg-indigo-50/60 border-b border-indigo-100/50 flex items-center justify-between">
                <span className="text-[11px] font-semibold text-indigo-600">{selected.length} selected</span>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onChange(undefined); }}
                  className="text-[11px] font-medium text-indigo-500 hover:text-indigo-700"
                >Clear all</button>
              </div>
            )}

            <div className="overflow-y-auto" style={{ maxHeight: 220 }}>
              {filtered.map(o => {
                const isOn = selected.includes(o.code);
                return (
                  <div
                    key={o.code}
                    onClick={() => toggle(o.code)}
                    className={`flex items-center gap-2.5 px-3 py-[7px] cursor-pointer text-[13px] transition-colors
                      ${isOn ? 'bg-indigo-50/40' : 'hover:bg-gray-50'}`}
                  >
                    <span className={`w-[18px] h-[18px] rounded flex items-center justify-center flex-shrink-0 transition-all duration-150 ${
                      isOn ? 'bg-indigo-500 text-white' : 'border-[1.5px] border-gray-300 bg-white'
                    }`}>
                      {isOn && <Check className="w-3 h-3" strokeWidth={2.5} />}
                    </span>
                    <span className={`truncate ${isOn ? 'font-medium text-gray-900' : 'text-gray-600'}`}>
                      {o.name && o.name !== o.code ? o.name : o.code}
                    </span>
                    {o.name && o.code && o.name !== o.code && (
                      <span className="text-[11px] text-gray-400 ml-auto flex-shrink-0 tabular-nums bg-gray-100 px-1.5 py-0.5 rounded">{o.code}</span>
                    )}
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div className="px-3 py-5 text-[13px] text-gray-400 text-center">
                  {options.length === 0 ? 'No data available' : 'No matching results'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FilterPanel({ filters, onChange, showFields = [] }) {
  const [salesOrgs, setSalesOrgs] = useState([]);
  const [hosList, setHosList] = useState([]);
  const [asms, setAsms] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [users, setUsers] = useState([]);
  const [channels, setChannels] = useState([]);
  const [brands, setBrands] = useState([]);
  const [categories, setCategories] = useState([]);
  const [depots, setDepots] = useState([]);
  const [supervisors, setSupervisors] = useState([]);

  const [loadingHos, setLoadingHos] = useState(false);
  const [loadingAsms, setLoadingAsms] = useState(false);
  const [loadingSupervisors, setLoadingSupervisors] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingRoutes, setLoadingRoutes] = useState(false);
  const [loadingDepots, setLoadingDepots] = useState(false);

  // Abort controllers to cancel stale requests
  const abortRefs = useRef({});
  const abortAndFetch = useCallback((key, fetchFn, setData, setLoading) => {
    // Cancel any in-flight request for this key
    abortRefs.current[key]?.abort();
    const ctrl = new AbortController();
    abortRefs.current[key] = ctrl;
    setLoading?.(true);
    fetchFn()
      .then(data => {
        if (!ctrl.signal.aborted) setData(data);
      })
      .catch(err => {
        if (err?.name !== 'AbortError' && !ctrl.signal.aborted) {
          console.error(`Filter ${key} error:`, err);
        }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading?.(false);
      });
  }, []);

  const show = useCallback(
    (field) => showFields.length === 0 || showFields.includes(field),
    [showFields]
  );

  // ─── Static filters (no cascade dependency) ───
  useEffect(() => {
    if (show('sales_org')) fetchFilters.salesOrgs().then(setSalesOrgs);
    if (show('channel'))   fetchFilters.channels().then(setChannels);
    if (show('brand'))     fetchFilters.brands().then(setBrands);
    if (show('category'))  fetchFilters.categories().then(setCategories);
  }, [show]);

  // ─── HOS depend on: sales_org ───
  useEffect(() => {
    if (!show('hos')) return;
    abortAndFetch('hos',
      () => fetchFilters.hos({ sales_org: filters.sales_org }),
      setHosList, setLoadingHos
    );
  }, [filters.sales_org, show, abortAndFetch]);

  // ─── ASMs depend on: sales_org + hos ───
  useEffect(() => {
    if (!show('asm')) return;
    abortAndFetch('asm',
      () => fetchFilters.asms({ sales_org: filters.sales_org, hos: filters.hos }),
      setAsms, setLoadingAsms
    );
  }, [filters.sales_org, filters.hos, show, abortAndFetch]);

  // ─── Supervisors depend on: sales_org + hos + asm ───
  useEffect(() => {
    if (!show('supervisor')) return;
    abortAndFetch('supervisor',
      () => fetchFilters.supervisors({ sales_org: filters.sales_org, asm: filters.asm, hos: filters.hos }),
      setSupervisors, setLoadingSupervisors
    );
  }, [filters.sales_org, filters.hos, filters.asm, show, abortAndFetch]);

  // ─── Depots depend on: sales_org + asm ───
  useEffect(() => {
    if (!show('depot')) return;
    abortAndFetch('depot',
      () => fetchFilters.depots({ sales_org: filters.sales_org, asm: filters.asm }),
      setDepots, setLoadingDepots
    );
  }, [filters.sales_org, filters.asm, show, abortAndFetch]);

  // ─── Users depend on: sales_org + hos + asm + supervisor + depot ───
  useEffect(() => {
    if (!show('user_code')) return;
    abortAndFetch('users',
      () => fetchFilters.users({
        sales_org: filters.sales_org, hos: filters.hos, asm: filters.asm,
        supervisor: filters.supervisor, depot: filters.depot,
      }),
      setUsers, setLoadingUsers
    );
  }, [filters.sales_org, filters.hos, filters.asm, filters.supervisor, filters.depot, show, abortAndFetch]);

  // ─── Routes depend on: sales_org + hos + asm + depot + supervisor ───
  useEffect(() => {
    if (!show('route')) return;
    abortAndFetch('routes',
      () => fetchFilters.routes({
        sales_org: filters.sales_org, hos: filters.hos, asm: filters.asm,
        depot: filters.depot, supervisor: filters.supervisor,
      }),
      setRoutes, setLoadingRoutes
    );
  }, [filters.sales_org, filters.hos, filters.asm, filters.depot, filters.supervisor, show, abortAndFetch]);

  // ─── Cascade clearing: when parent changes, clear all children ───
  const set = (key, value) => {
    const newFilters = { ...filters, [key]: value || undefined };

    // Clear all downstream children defined in CHILD_MAP
    const children = CHILD_MAP[key];
    if (children) {
      children.forEach(child => delete newFilters[child]);
    }

    onChange(newFilters);
  };

  const visibleFields = Object.keys(fieldMeta).filter(show);
  const hasDateFrom = show('date_from');
  const hasDateTo = show('date_to');
  const multiFields = visibleFields.filter(f => f !== 'date_from' && f !== 'date_to');

  const inputClass =
    'w-full bg-white border border-gray-200/80 rounded-lg px-3 py-[7px] text-[13px] text-gray-700 ' +
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/15 focus:border-indigo-400 transition-all duration-150 hover:border-gray-300';

  const selectClass =
    'w-full bg-white border border-gray-200/80 rounded-lg px-3 py-[7px] text-[13px] text-gray-700 ' +
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/15 focus:border-indigo-400 ' +
    'transition-all duration-150 appearance-none cursor-pointer hover:border-gray-300';

  const Label = ({ field }) => {
    const meta = fieldMeta[field];
    const Icon = meta.icon;
    return (
      <label className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide select-none">
        <Icon className="w-3.5 h-3.5 text-gray-400" strokeWidth={2} />
        {meta.label}
      </label>
    );
  };

  const handleDateFrom = (val) => {
    if (filters.date_to && val > filters.date_to) return;
    set('date_from', val);
  };
  const handleDateTo = (val) => {
    if (filters.date_from && val < filters.date_from) return;
    set('date_to', val);
  };

  const optionsFor = (field) => {
    switch (field) {
      case 'sales_org': return salesOrgs;
      case 'hos': return hosList;
      case 'asm': return asms;
      case 'route': return routes;
      case 'user_code': return users;
      case 'channel': return channels;
      case 'brand': return brands;
      case 'category': return categories;
      case 'depot': return depots;
      case 'supervisor': return supervisors;
      default: return [];
    }
  };

  const loadingFor = (field) => {
    switch (field) {
      case 'hos': return loadingHos;
      case 'asm': return loadingAsms;
      case 'supervisor': return loadingSupervisors;
      case 'user_code': return loadingUsers;
      case 'route': return loadingRoutes;
      case 'depot': return loadingDepots;
      default: return false;
    }
  };

  const multiGridCols =
    multiFields.length <= 3 ? 'grid-cols-1 sm:grid-cols-3'
    : multiFields.length <= 5 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5'
    : multiFields.length <= 7 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7'
    : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7';

  return (
    <div className="bg-white/70 border border-gray-200/60 rounded-xl p-4 pb-5 space-y-4">
      {/* Row 1: Date range */}
      {(hasDateFrom || hasDateTo) && (
        <div className="flex flex-wrap items-end gap-3">
          {hasDateFrom && (
            <div className="min-w-[180px] flex-1 max-w-[220px]">
              <Label field="date_from" />
              <input
                type="date"
                value={filters.date_from || ''}
                max={filters.date_to || undefined}
                onChange={e => handleDateFrom(e.target.value)}
                className={inputClass}
              />
            </div>
          )}
          {hasDateTo && (
            <div className="min-w-[180px] flex-1 max-w-[220px]">
              <Label field="date_to" />
              <input
                type="date"
                value={filters.date_to || ''}
                min={filters.date_from || undefined}
                onChange={e => handleDateTo(e.target.value)}
                className={inputClass}
              />
            </div>
          )}
        </div>
      )}

      {/* Row 2: All other filters in hierarchy order */}
      {multiFields.length > 0 && (
        <div className={`grid ${multiGridCols} gap-x-3 gap-y-4`}>
          {['sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'channel', 'brand', 'category'].map(field =>
            show(field) && (
              <div key={field}>
                <Label field={field} />
                <MultiSelect
                  options={optionsFor(field)}
                  value={filters[field]}
                  onChange={(val) => set(field, val)}
                  loading={loadingFor(field)}
                />
              </div>
            )
          )}

          {show('day') && (
            <div>
              <Label field="day" />
              <select
                value={String(filters.day || '')}
                onChange={e => onChange({ ...filters, day: e.target.value ? Number(e.target.value) : undefined })}
                className={selectClass}
              >
                <option value="">All (MTD)</option>
                {Array.from({ length: (() => {
                  const y = Number(filters.year) || new Date().getFullYear();
                  const m = Number(filters.month) || new Date().getMonth() + 1;
                  return new Date(y, m, 0).getDate();
                })() }, (_, i) => i + 1).map(d =>
                  <option key={d} value={String(d)}>{d}</option>
                )}
              </select>
            </div>
          )}
          {show('month') && (
            <div>
              <Label field="month" />
              <select
                value={String(filters.month || '')}
                onChange={e => {
                  const val = e.target.value ? Number(e.target.value) : undefined;
                  const newFilters = { ...filters, month: val, day: undefined };
                  onChange(newFilters);
                }}
                className={selectClass}
              >
                <option value="">All</option>
                {[1,2,3,4,5,6,7,8,9,10,11,12].map(m =>
                  <option key={m} value={String(m)}>{new Date(2000, m-1).toLocaleString('default',{month:'long'})}</option>
                )}
              </select>
            </div>
          )}
          {show('year') && (
            <div>
              <Label field="year" />
              <select
                value={String(filters.year || '')}
                onChange={e => {
                  const val = e.target.value ? Number(e.target.value) : undefined;
                  const newFilters = { ...filters, year: val, day: undefined };
                  onChange(newFilters);
                }}
                className={selectClass}
              >
                <option value="">All</option>
                <option value="2026">2026</option>
                <option value="2025">2025</option>
                <option value="2024">2024</option>
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
