import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchFilters } from '../api';
import { useAuth } from '../context/AuthContext';
import {
  Calendar, Building2, Route, User, Radio, Tag, Layers, Hash, CalendarDays,
  Warehouse, Users, ChevronDown, X, Check, Shield, Crown, RotateCcw, UserCircle, Package, Network, Lock,
} from 'lucide-react';

const fieldMeta = {
  date_from: { label: 'From', icon: Calendar, type: 'date' },
  date_to: { label: 'To', icon: Calendar, type: 'date' },
  sales_org: { label: 'Sales Org', icon: Building2, multi: true },
  hos: { label: 'HOS', icon: Crown, multi: true },
  asm: { label: 'ASM', icon: Shield, multi: true },
  depot: { label: 'NSM', icon: Network, multi: true },
  supervisor: { label: 'Supervisor', icon: Users, multi: true },
  user_code: { label: 'Salesman', icon: User, multi: true },
  route: { label: 'Route', icon: Route, multi: true },
  channel: { label: 'Channel', icon: Radio, multi: true },
  brand: { label: 'Brand', icon: Tag, multi: true },
  category: { label: 'Category', icon: Layers, multi: true },
  customer: { label: 'Customer', icon: UserCircle, multi: true },
  item: { label: 'Item', icon: Package, multi: true },
  day: { label: 'Day', icon: Calendar, type: 'day' },
  month: { label: 'Month', icon: CalendarDays, type: 'month' },
  year: { label: 'Year', icon: Hash, type: 'year' },
};

/* Hierarchy: sales_org → hos → asm → supervisor → user_code → route
                                       depot ──────┘              │
                                                                   route depends on all above */
const CHILD_MAP = {
  sales_org: ['asm', 'depot', 'supervisor', 'user_code', 'route', 'customer', 'item'],
  hos:       ['sales_org', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'customer'],
  asm:       ['depot', 'supervisor', 'user_code', 'route', 'customer'],
  depot:     ['supervisor', 'user_code', 'route', 'customer'],
  supervisor:['user_code', 'route', 'customer'],
  user_code: ['route', 'customer'],
  route:     ['customer'],
  brand:     ['item'],
  category:  ['item'],
};

function MultiSelect({ options, value, onChange, placeholder = 'All', loading = false, onSearch = null, searchByCode = false, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const btnRef = useRef(null);
  const dropRef = useRef(null);
  const debounceRef = useRef(null);
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

  const handleSearchChange = (val) => {
    setSearch(val);
    if (onSearch) {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => onSearch(val), 300);
    }
  };

  const DISPLAY_LIMIT = 200;
  const allFiltered = onSearch
    ? options
    : search
      ? options.filter(o => (o.name || o.code || '').toLowerCase().includes(search.toLowerCase())
          || (o.code || '').toLowerCase().includes(search.toLowerCase()))
      : options;
  const filtered = allFiltered.slice(0, DISPLAY_LIMIT);
  const hasMore = allFiltered.length > DISPLAY_LIMIT;

  const displayText = selected.length === 0 ? placeholder
    : selected.length === 1 ? (options.find(o => o.code === selected[0])?.name || selected[0])
    : `${selected.length} selected`;

  return (
    <div>
      <button
        ref={btnRef}
        type="button"
        onClick={() => { if (disabled) return; setOpen(!open); setSearch(''); }}
        className={`w-full border rounded-lg px-3 py-[7px] text-[13px] text-gray-700
          focus:outline-none transition-all duration-150 flex items-center justify-between gap-1
          ${disabled
            ? 'bg-indigo-50/60 border-indigo-200/60 cursor-not-allowed opacity-80'
            : `bg-white hover:border-gray-300 focus:ring-2 focus:ring-indigo-500/15 focus:border-indigo-400
               ${open ? 'border-indigo-400 ring-2 ring-indigo-500/15' : ''}
               ${loading ? 'border-gray-200/60 opacity-60' : 'border-gray-200/80'}`
          }`}
        disabled={loading || disabled}
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
                  onChange={e => handleSearchChange(e.target.value)}
                  placeholder={searchByCode ? 'Search by name or code...' : 'Type to search...'}
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
              {hasMore && (
                <div className="px-3 py-2 text-[11px] text-gray-400 text-center border-t border-gray-100 bg-gray-50/60">
                  Showing {DISPLAY_LIMIT} of {allFiltered.length} — type to search
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FilterPanel({ filters, onChange, showFields = [], onReset, rowBreakBefore = [], flat = false }) {
  const { user } = useAuth() || {};
  const lockedFilters = user?.locked_filters || {};
  const initialFiltersRef = useRef(filters);

  // On mount: if locked filters aren't in the page's current filter state, inject them.
  // This ensures the UI reflects what the API interceptor enforces.
  useEffect(() => {
    if (!Object.keys(lockedFilters).length) return;
    const needsSync = Object.entries(lockedFilters).some(([k, v]) => filters[k] !== v);
    if (needsSync) onChange({ ...filters, ...lockedFilters });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [salesOrgs, setSalesOrgs] = useState([]);
  const [hosList, setHosList] = useState([]);
  const [asms, setAsms] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [users, setUsers] = useState([]);
  const [channels, setChannels] = useState([]);
  const [brands, setBrands] = useState([]);
  const [categories, setCategories] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [depots, setDepots] = useState([]);
  const [supervisors, setSupervisors] = useState([]);
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);

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

  // ─── Sales orgs: reload on any hierarchy change — backend filters to user's own orgs ───
  useEffect(() => {
    if (!show('sales_org')) return;
    fetchFilters.salesOrgs({
      hos:        filters.hos        || undefined,
      asm:        filters.asm        || undefined,
      depot:      filters.depot      || undefined,
      supervisor: filters.supervisor || undefined,
      user_code:  filters.user_code  || undefined,
    }).then(setSalesOrgs);
  }, [filters.hos, filters.asm, filters.depot, filters.supervisor, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Static filters (no hierarchy dependency) ───
  useEffect(() => {
    if (show('channel'))  fetchFilters.channels().then(setChannels);
    if (show('brand'))    fetchFilters.brands().then(setBrands);
    if (show('category')) fetchFilters.categories().then(setCategories);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Items depend on: brand + category + sales_org ───
  useEffect(() => {
    if (!show('item')) return;
    abortAndFetch('item',
      () => fetchFilters.items({ brand: filters.brand, category: filters.category, sales_org: filters.sales_org }),
      setItems, setLoadingItems
    );
  }, [filters.brand, filters.category, filters.sales_org]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── HOS: top-down (sales_org) + bottom-up (asm/depot/supervisor/user_code) ───
  useEffect(() => {
    if (!show('hos')) return;
    abortAndFetch('hos',
      () => fetchFilters.hos({
        sales_org:  filters.sales_org  || undefined,
        asm:        filters.asm        || undefined,
        depot:      filters.depot      || undefined,
        supervisor: filters.supervisor || undefined,
        user_code:  filters.user_code  || undefined,
      }),
      setHosList, setLoadingHos
    );
  }, [filters.sales_org, filters.asm, filters.depot, filters.supervisor, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── ASMs: top-down (sales_org/hos) + bottom-up (supervisor/user_code) ───
  useEffect(() => {
    if (!show('asm')) return;
    abortAndFetch('asm',
      () => fetchFilters.asms({
        sales_org:  filters.sales_org  || undefined,
        hos:        filters.hos        || undefined,
        supervisor: filters.supervisor || undefined,
        user_code:  filters.user_code  || undefined,
      }),
      setAsms, setLoadingAsms
    );
  }, [filters.sales_org, filters.hos, filters.supervisor, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Depots (NSM): top-down (sales_org/hos/asm) + bottom-up (supervisor/user_code) ───
  useEffect(() => {
    if (!show('depot')) return;
    abortAndFetch('depot',
      () => fetchFilters.depots({
        sales_org:  filters.sales_org  || undefined,
        hos:        filters.hos        || undefined,
        asm:        filters.asm        || undefined,
        supervisor: filters.supervisor || undefined,
        user_code:  filters.user_code  || undefined,
      }),
      setDepots, setLoadingDepots
    );
  }, [filters.sales_org, filters.hos, filters.asm, filters.supervisor, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Supervisors: top-down (sales_org/hos/asm/depot) + bottom-up (user_code) ───
  useEffect(() => {
    if (!show('supervisor')) return;
    abortAndFetch('supervisor',
      () => fetchFilters.supervisors({
        sales_org:  filters.sales_org  || undefined,
        hos:        filters.hos        || undefined,
        asm:        filters.asm        || undefined,
        depot:      filters.depot      || undefined,
        user_code:  filters.user_code  || undefined,
      }),
      setSupervisors, setLoadingSupervisors
    );
  }, [filters.sales_org, filters.hos, filters.asm, filters.depot, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

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
  }, [filters.sales_org, filters.hos, filters.asm, filters.supervisor, filters.depot]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Routes depend on: all hierarchy filters ───
  useEffect(() => {
    if (!show('route')) return;
    abortAndFetch('routes',
      () => fetchFilters.routes({
        sales_org: filters.sales_org, hos: filters.hos, asm: filters.asm,
        depot: filters.depot, supervisor: filters.supervisor, user_code: filters.user_code,
      }),
      setRoutes, setLoadingRoutes
    );
  }, [filters.sales_org, filters.hos, filters.asm, filters.depot, filters.supervisor, filters.user_code]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Customers: load once from dim_customer, filter client-side by sales_org ───
  const [allCustomers, setAllCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);

  useEffect(() => {
    if (!show('customer')) return;
    abortAndFetch('customer',
      () => fetchFilters.orderCustomers(),
      setAllCustomers, setLoadingCustomers
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!show('customer')) return;
    if (filters.sales_org) {
      const orgs = new Set(filters.sales_org.split(',').map(s => s.trim()).filter(Boolean));
      setCustomers(allCustomers.filter(c => orgs.has(c.sales_org)));
    } else {
      setCustomers(allCustomers);
    }
  }, [filters.sales_org, allCustomers]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Hierarchy: hide filters above/beside the user's locked level ───
  // Order reflects UI display: HOS → NSM → ASM → Supervisor → Salesman
  // NSM (depot) and ASM are sibling branches under HOS — each hides the other's branch
  const HIERARCHY = ['hos', 'depot', 'asm', 'supervisor', 'user_code'];
  const lockedKey = Object.keys(lockedFilters)[0] || null;
  const lockedIdx = lockedKey ? HIERARCHY.indexOf(lockedKey) : -1;

  const isHidden = (key) => {
    if (lockedIdx < 0) return false; // GCD — sees all filters

    // Sales org: show for everyone EXCEPT salesman (user_code locked)
    // HOS, ASM, NSM, Supervisor, DP all manage multiple orgs via tbl_user_details
    // Backend filters orgs to only those the user manages (via interceptor)
    if (key === 'sales_org') return lockedKey === 'user_code';

    // NSM login (depot locked): hide HOS and ASM — NSM is a separate branch from ASM
    if (lockedKey === 'depot' && key === 'asm') return true;

    // ASM login: hide NSM (depot) — ASM branch doesn't use NSM filter
    if (lockedKey === 'asm' && key === 'depot') return true;

    const idx = HIERARCHY.indexOf(key);
    if (idx < 0) return false; // non-hierarchy field (date, channel, brand, etc.)
    return idx < lockedIdx;    // hide anything above the user's locked level
  };

  const isLocked = (key) => key in lockedFilters;

  const set = (key, value) => {
    if (isLocked(key)) return; // cannot override locked filters
    const newFilters = { ...filters, [key]: value || undefined };

    // Clear all downstream children defined in CHILD_MAP
    const children = CHILD_MAP[key];
    if (children) {
      children.forEach(child => {
        if (!isLocked(child)) delete newFilters[child];
      });
    }

    // Always restore locked filters
    Object.entries(lockedFilters).forEach(([k, v]) => { newFilters[k] = v; });
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

  // Local state buffers the displayed date while user browses months — no API call until confirmed
  const [localDateFrom, setLocalDateFrom] = useState(filters.date_from || '');
  const [localDateTo,   setLocalDateTo]   = useState(filters.date_to   || '');

  // Sync when external reset fires
  useEffect(() => { setLocalDateFrom(filters.date_from || ''); }, [filters.date_from]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLocalDateTo(filters.date_to   || ''); }, [filters.date_to]);     // eslint-disable-line react-hooks/exhaustive-deps

  const applyDateFrom = (val) => {
    if (!val) return;
    if (!show('date_to')) { onChange({ ...filters, date_from: val, date_to: val }); return; }
    if (filters.date_to && val > filters.date_to) {
      onChange({ ...filters, date_from: val, date_to: val });
      setLocalDateTo(val);
      return;
    }
    set('date_from', val);
  };

  const applyDateTo = (val) => {
    if (!val) return;
    if (show('date_from') && filters.date_from && val < filters.date_from) return;
    set('date_to', val);
  };

  // onChange → only update what the input shows, no filter/API call
  const handleDateFromChange = (val) => setLocalDateFrom(val);
  const handleDateToChange   = (val) => setLocalDateTo(val);

  // onBlur → user finished selecting, now apply to filter and trigger data load
  const handleDateFromBlur = () => {
    if (localDateFrom && localDateFrom !== filters.date_from) applyDateFrom(localDateFrom);
  };
  const handleDateToBlur = () => {
    if (localDateTo && localDateTo !== filters.date_to) applyDateTo(localDateTo);
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
      case 'customer': return customers;
      case 'depot': return depots;
      case 'supervisor': return supervisors;
      case 'item': return items;
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
      case 'customer': return loadingCustomers;
      case 'item': return loadingItems;
      default: return false;
    }
  };

  const multiGridCols =
    multiFields.length <= 3 ? 'grid-cols-1 sm:grid-cols-3'
    : multiFields.length <= 5 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5'
    : multiFields.length <= 7 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7'
    : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7';

  const content = (
    <>
      {/* Row 1: Date range */}
      {(hasDateFrom || hasDateTo) && (
        <div className="flex flex-wrap items-end gap-3">
          {hasDateFrom && (
            <div className="min-w-[180px] flex-1 max-w-[220px]">
              {hasDateTo ? <Label field="date_from" /> : (
                <label className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 mb-1.5 uppercase tracking-wide select-none">
                  <Calendar className="w-3.5 h-3.5 text-gray-400" strokeWidth={2} />
                  Date
                </label>
              )}
              <input
                type="date"
                value={localDateFrom}
                max={hasDateTo ? (localDateTo || undefined) : undefined}
                onChange={e => handleDateFromChange(e.target.value)}
                onBlur={handleDateFromBlur}
                className={inputClass}
              />
            </div>
          )}
          {hasDateTo && (
            <div className="min-w-[180px] flex-1 max-w-[220px]">
              <Label field="date_to" />
              <input
                type="date"
                value={localDateTo}
                min={localDateFrom || undefined}
                onChange={e => handleDateToChange(e.target.value)}
                onBlur={handleDateToBlur}
                className={inputClass}
              />
            </div>
          )}
          {/* Reset Filters Button */}
          <button
            type="button"
            onClick={() => onChange(initialFiltersRef.current)}
            className="flex items-center gap-1.5 px-3 py-[7px] text-[13px] font-medium text-gray-500 bg-gray-100 hover:bg-red-50 hover:text-red-600 rounded-lg border border-gray-200/80 transition-all duration-150 self-end"
            title="Reset all filters"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        </div>
      )}

      {/* Row 2: All other filters in hierarchy order */}
      {multiFields.length > 0 && (
        <div className={`grid ${multiGridCols} gap-x-3 gap-y-4`}>
          {['sales_org', 'hos', 'depot', 'asm', 'supervisor', 'user_code', 'route', 'channel', 'customer', 'brand', 'category', 'item'].map(field =>
            show(field) && !isHidden(field) && (
              <div key={field} className={rowBreakBefore.includes(field) ? 'col-start-1' : ''}>
                <div className="flex items-center gap-1">
                  <Label field={field} />
                  {isLocked(field) && (
                    <Lock className="w-3 h-3 text-indigo-400 opacity-60 -mt-1.5" title="Locked by your role" />
                  )}
                </div>
                <MultiSelect
                  options={optionsFor(field)}
                  value={filters[field]}
                  onChange={(val) => set(field, val)}
                  loading={loadingFor(field)}
                  onSearch={null}
                  searchByCode={field === 'item' || field === 'customer'}
                  disabled={isLocked(field)}
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

          {onReset && !hasDateFrom && !hasDateTo && (
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => onChange(initialFiltersRef.current)}
                className="flex items-center gap-1.5 px-3 py-[7px] text-[13px] font-medium text-gray-500 bg-gray-100 hover:bg-red-50 hover:text-red-600 rounded-lg border border-gray-200/80 transition-all duration-150"
                title="Reset all filters"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );

  if (flat) return content;

  return (
    <div className="bg-white/70 border border-gray-200/60 rounded-xl p-4 pb-5 space-y-4">
      {content}
    </div>
  );
}
