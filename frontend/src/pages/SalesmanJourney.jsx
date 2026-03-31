import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { GoogleMap, Marker, InfoWindow, Polyline, useJsApiLoader } from '@react-google-maps/api';
import { fetchSalesmanJourney, fetchSalesmanJourneyDetail } from '../api';
import FilterPanel from '../components/FilterPanel';
import Loading from '../components/Loading';
import KpiCard from '../components/KpiCard';
import {
  MapPin, Banknote, Users, Package, Search, Download,
  Eye, X, ChevronLeft, ChevronRight, Map, ChevronDown,
  Clock, CheckCircle2, XCircle, Navigation, TrendingUp, Route
} from 'lucide-react';

const PAGE_SIZES = [20, 50, 100];
const GMAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '';
const DUBAI_CENTER = { lat: 25.2048, lng: 55.2708 };

const PRODUCTIVE_COLOR   = '#10b981';
const UNPRODUCTIVE_COLOR = '#f43f5e';
const ROUTE_COLOR        = '#6366f1';

const aed = (v) => v != null ? `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '-';

const calcDuration = (checkIn, checkOut) => {
  if (!checkIn || !checkOut) return '-';
  const a = new Date(checkIn), b = new Date(checkOut);
  const diff = Math.round((b - a) / 1000);
  if (isNaN(diff) || diff < 0) return '-';
  const m = Math.floor(diff / 60), s = diff % 60;
  return `${m}m ${s}s`;
};

const fmtTime = (ts) => {
  if (!ts) return '-';
  const t = ts.toString();
  const part = t.includes('T') ? t.split('T')[1] : t.includes(' ') ? t.split(' ')[1] : t;
  return part.substring(0, 8);
};

// Pastel gradient by index for salesman avatars
const AVATAR_GRADIENTS = [
  'from-violet-500 to-indigo-600',
  'from-blue-500 to-cyan-600',
  'from-emerald-500 to-teal-600',
  'from-orange-500 to-amber-600',
  'from-rose-500 to-pink-600',
  'from-fuchsia-500 to-purple-600',
];
const avatarGradient = (name) => AVATAR_GRADIENTS[(name?.charCodeAt(0) || 0) % AVATAR_GRADIENTS.length];

// ─── Map View Component ────────────────────────────────────────────────────────
function MapView({ users, filters, effectiveDateFrom, effectiveDateTo }) {
  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: GMAPS_KEY,
    id: 'google-map-script',
  });

  const [selectedUser, setSelectedUser]   = useState(null);
  const [mapDetail, setMapDetail]         = useState(null);
  const [mapLoading, setMapLoading]       = useState(false);
  const [activeMarker, setActiveMarker]   = useState(null);
  const [dropdownOpen, setDropdownOpen]   = useState(false);
  const [userSearch, setUserSearch]       = useState('');
  const [roadPath, setRoadPath]           = useState([]);
  const mapRef       = useRef(null);
  const loadingRef   = useRef(false);
  const dropdownRef  = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
        setUserSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const onMapLoad = useCallback((map) => { mapRef.current = map; }, []);

  const loadDetail = useCallback((user) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setSelectedUser(user);
    setMapDetail(null);
    setActiveMarker(null);
    setRoadPath([]);
    setMapLoading(true);
    const df = {
      ...filters,
      user_code: user.user_code,
      ...(effectiveDateFrom && { date_from: effectiveDateFrom }),
      ...(effectiveDateTo   && { date_to:   effectiveDateTo }),
    };
    fetchSalesmanJourneyDetail(df)
      .then(d => setMapDetail(d))
      .catch(console.error)
      .finally(() => { setMapLoading(false); loadingRef.current = false; });
  }, [filters, effectiveDateFrom, effectiveDateTo]);

  // Auto-select first user on initial load
  useEffect(() => {
    if (users.length > 0 && !selectedUser) {
      loadDetail(users[0]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [users]);

  const selectUser = (user) => {
    loadDetail(user);
    setDropdownOpen(false);
    setUserSearch('');
  };

  const filteredDropdownUsers = useMemo(() => {
    if (!userSearch.trim()) return users;
    const s = userSearch.toLowerCase();
    return users.filter(u =>
      u.user_name?.toLowerCase().includes(s) ||
      u.route_name?.toLowerCase().includes(s) ||
      u.user_code?.toLowerCase().includes(s)
    );
  }, [users, userSearch]);

  // Valid visits with lat/lng
  const validVisits = useMemo(() => {
    if (!mapDetail?.visits) return [];
    return mapDetail.visits.filter(v =>
      v.latitude != null && v.longitude != null &&
      Number(v.latitude) !== 0 && Number(v.longitude) !== 0
    );
  }, [mapDetail]);

  const allVisits = mapDetail?.visits || [];

  const mapCenter = useMemo(() => {
    if (validVisits.length === 0) return DUBAI_CENTER;
    const sum = validVisits.reduce((a, v) => ({
      lat: a.lat + Number(v.latitude),
      lng: a.lng + Number(v.longitude),
    }), { lat: 0, lng: 0 });
    return { lat: sum.lat / validVisits.length, lng: sum.lng / validVisits.length };
  }, [validVisits]);

  const path = useMemo(() =>
    validVisits.map(v => ({ lat: Number(v.latitude), lng: Number(v.longitude) })),
    [validVisits]
  );

  // Fetch road-following route via Directions Service
  useEffect(() => {
    setRoadPath([]);
    if (!isLoaded || !window.google || validVisits.length < 2) return;

    const points = validVisits.map(v => ({ lat: Number(v.latitude), lng: Number(v.longitude) }));
    const CHUNK = 10; // 10 stops = 9 legs = 8 waypoints (well within 25 limit)
    const svc = new window.google.maps.DirectionsService();

    const chunks = [];
    for (let i = 0; i < points.length; i += CHUNK - 1) {
      const c = points.slice(i, i + CHUNK);
      if (c.length >= 2) chunks.push(c);
    }

    const results = new Array(chunks.length).fill(null);
    let done = 0;

    chunks.forEach((chunk, ci) => {
      svc.route({
        origin: chunk[0],
        destination: chunk[chunk.length - 1],
        waypoints: chunk.slice(1, -1).map(p => ({ location: p, stopover: true })),
        travelMode: window.google.maps.TravelMode.DRIVING,
      }, (result, status) => {
        if (status === 'OK') {
          results[ci] = result.routes[0].overview_path.map(p => ({ lat: p.lat(), lng: p.lng() }));
        } else {
          results[ci] = chunk; // fallback to straight line for this chunk
        }
        done++;
        if (done === chunks.length) {
          setRoadPath(results.filter(Boolean).flat());
        }
      });
    });
  }, [isLoaded, validVisits]);

  const productiveCount   = allVisits.filter(v => v.productive).length;
  const unproductiveCount = allVisits.filter(v => !v.productive).length;
  const kpis = mapDetail?.kpis;

  if (loadError) return (
    <div className="flex items-center justify-center h-64 text-red-500 text-sm">
      Failed to load Google Maps. Check your API key.
    </div>
  );

  return (
    <div className="space-y-3">

      {/* ── FILTER BAR (above map) ── */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm" style={{ overflow: 'visible', position: 'relative', zIndex: 30 }}>
        <div className="flex items-center gap-3 px-5 py-3.5">

          {/* Salesman combobox */}
          <div ref={dropdownRef} className="relative flex-shrink-0" style={{ minWidth: 280 }}>
            {/* Trigger button */}
            <button
              onClick={() => { setDropdownOpen(o => !o); setUserSearch(''); }}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl border text-sm font-semibold text-left transition-all
                ${dropdownOpen ? 'border-indigo-400 ring-2 ring-indigo-200 bg-white' : 'border-gray-200 bg-gray-50 hover:border-indigo-300'}`}
            >
              {selectedUser ? (
                <div className={`w-7 h-7 rounded-full bg-gradient-to-br ${avatarGradient(selectedUser.user_name)} flex items-center justify-center text-[11px] font-bold text-white shadow-sm flex-shrink-0`}>
                  {(selectedUser.user_name || '?')[0].toUpperCase()}
                </div>
              ) : (
                <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                  <Users className="w-3.5 h-3.5 text-gray-500" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="truncate text-gray-800">{selectedUser?.user_name || 'Select Salesman'}</div>
                {selectedUser && <div className="text-[10px] font-normal text-gray-400 truncate">{selectedUser.route_name}</div>}
              </div>
              <ChevronDown className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Dropdown panel */}
            {dropdownOpen && (
              <div className="absolute left-0 top-full mt-1.5 w-full bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden"
                style={{ minWidth: 300, zIndex: 9999 }}>
                {/* Search inside dropdown */}
                <div className="p-2 border-b border-gray-100">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                    <input
                      autoFocus
                      type="text"
                      placeholder="Search name, route…"
                      value={userSearch}
                      onChange={e => setUserSearch(e.target.value)}
                      className="w-full pl-8 pr-3 py-2 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    />
                  </div>
                </div>
                {/* List */}
                <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
                  {filteredDropdownUsers.length === 0 ? (
                    <div className="px-4 py-6 text-center text-xs text-gray-400">No salesmen found</div>
                  ) : filteredDropdownUsers.map((u, i) => (
                    <button
                      key={i}
                      onClick={() => selectUser(u)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-indigo-50
                        ${selectedUser?.user_code === u.user_code ? 'bg-indigo-50' : ''}`}
                    >
                      <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${avatarGradient(u.user_name)} flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0 shadow-sm`}>
                        {(u.user_name || '?')[0].toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-semibold truncate ${selectedUser?.user_code === u.user_code ? 'text-indigo-700' : 'text-gray-800'}`}>
                          {u.user_name}
                        </div>
                        <div className="text-[10px] text-gray-400 truncate">{u.route_name} · {u.user_code}</div>
                      </div>
                      {selectedUser?.user_code === u.user_code && (
                        <div className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
                {/* Count footer */}
                <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 text-[10px] text-gray-400">
                  {filteredDropdownUsers.length} of {users.length} salesmen
                </div>
              </div>
            )}
          </div>

          <div className="h-8 w-px bg-gray-200 flex-shrink-0" />

          {/* Stats chips */}
          <div className="flex items-center gap-2 flex-wrap">
            <StatChip icon={<Navigation   className="w-3.5 h-3.5" />} label="Stops"      value={allVisits.length}  color="indigo"  />
            <StatChip icon={<CheckCircle2 className="w-3.5 h-3.5" />} label="Productive" value={productiveCount}   color="emerald" />
            <StatChip icon={<XCircle      className="w-3.5 h-3.5" />} label="Non-Prod"   value={unproductiveCount} color="rose"    />
            {kpis && <StatChip icon={<TrendingUp className="w-3.5 h-3.5" />} label="Sales" value={aed(kpis.total_sales)} color="amber" />}
            {kpis && <StatChip icon={<Banknote   className="w-3.5 h-3.5" />} label="Collection" value={aed(kpis.collection)} color="purple" />}
          </div>

          {/* Journey time (right-aligned) */}
          {mapDetail?.journey_info?.journey_start && (
            <>
              <div className="h-8 w-px bg-gray-200 flex-shrink-0 ml-auto" />
              <div className="flex items-center gap-2 text-xs text-gray-500 flex-shrink-0">
                <Route className="w-3.5 h-3.5 text-indigo-400" />
                <span className="font-medium text-gray-700">{selectedUser?.route_name}</span>
                <span className="text-gray-300">·</span>
                <Clock className="w-3.5 h-3.5 text-blue-400" />
                <span>{fmtTime(mapDetail.journey_info.journey_start)}</span>
                <span className="text-gray-300">→</span>
                <span>{fmtTime(mapDetail.journey_info.journey_end)}</span>
              </div>
            </>
          )}
        </div>

      </div>

      {/* GPS warning strip */}
      {!mapLoading && mapDetail && validVisits.length < allVisits.length && allVisits.length > 0 && (
        <div className="px-5 py-2 bg-amber-50 border border-amber-100 rounded-xl flex items-center gap-2">
          <MapPin className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
          <span className="text-[11px] text-amber-700 font-medium">
            {allVisits.length - validVisits.length} of {allVisits.length} stops have no GPS coordinates and are not shown on the map
          </span>
        </div>
      )}

      {/* ── MAP CANVAS ── */}
      <div
        className="relative rounded-2xl overflow-hidden shadow-xl border border-gray-200"
        style={{ height: 'calc(100vh - 380px)', minHeight: 500 }}
      >
        {isLoaded ? (
          <GoogleMap
            mapContainerStyle={{ width: '100%', height: '100%' }}
            center={mapCenter}
            zoom={validVisits.length > 0 ? 13 : 11}
            onLoad={onMapLoad}
            options={{
              streetViewControl: false,
              mapTypeControl: false,
              fullscreenControl: true,
              zoomControl: true,
              zoomControlOptions: { position: 9 },
              gestureHandling: 'greedy',
              styles: [
                { featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] },
                { featureType: 'transit', stylers: [{ visibility: 'simplified' }] },
              ],
            }}
          >
            {(roadPath.length > 1 || path.length > 1) && (
              <Polyline
                path={roadPath.length > 1 ? roadPath : path}
                options={{
                  strokeColor: ROUTE_COLOR,
                  strokeOpacity: 0.85,
                  strokeWeight: 4,
                  icons: [{
                    icon: {
                      path: window.google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                      scale: 3,
                      strokeColor: ROUTE_COLOR,
                      fillColor: ROUTE_COLOR,
                      fillOpacity: 1,
                      strokeOpacity: 1,
                    },
                    offset: '50%',
                    repeat: '120px',
                  }],
                }}
              />
            )}

            {validVisits.map((v, idx) => (
              <Marker
                key={idx}
                position={{ lat: Number(v.latitude), lng: Number(v.longitude) }}
                label={{ text: String(v.sequence), color: 'white', fontSize: '10px', fontWeight: 'bold' }}
                icon={{
                  path: window.google.maps.SymbolPath.CIRCLE,
                  scale: 15,
                  fillColor: v.productive ? PRODUCTIVE_COLOR : UNPRODUCTIVE_COLOR,
                  fillOpacity: activeMarker === idx ? 1 : 0.88,
                  strokeColor: 'white',
                  strokeWeight: activeMarker === idx ? 3 : 2,
                }}
                zIndex={activeMarker === idx ? 10 : 1}
                onClick={() => setActiveMarker(activeMarker === idx ? null : idx)}
              >
                {activeMarker === idx && (
                  <InfoWindow onCloseClick={() => setActiveMarker(null)}>
                    <div style={{ fontFamily: 'Inter, sans-serif', minWidth: 200, padding: 2 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <div style={{
                          width: 28, height: 28, borderRadius: '50%',
                          background: v.productive ? '#10b981' : '#f43f5e',
                          color: 'white', display: 'flex', alignItems: 'center',
                          justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0,
                        }}>{v.sequence}</div>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, color: '#0f172a', lineHeight: 1.3 }}>{v.customer_name}</div>
                          <div style={{ fontSize: 11, color: '#94a3b8' }}>{v.customer_code}</div>
                        </div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 11 }}>
                        <div>
                          <div style={{ color: '#94a3b8', marginBottom: 1 }}>Check In</div>
                          <div style={{ fontWeight: 600, color: '#334155' }}>{fmtTime(v.arrival_time)}</div>
                        </div>
                        <div>
                          <div style={{ color: '#94a3b8', marginBottom: 1 }}>Check Out</div>
                          <div style={{ fontWeight: 600, color: '#334155' }}>{fmtTime(v.out_time)}</div>
                        </div>
                        <div style={{ gridColumn: '1/-1' }}>
                          <div style={{ color: '#94a3b8', marginBottom: 1 }}>Duration</div>
                          <div style={{ fontWeight: 600, color: '#334155' }}>{v.duration_mins != null ? `${v.duration_mins} min` : '-'}</div>
                        </div>
                      </div>
                      <div style={{
                        marginTop: 10, padding: '4px 10px', borderRadius: 99,
                        display: 'inline-block', fontSize: 10, fontWeight: 700,
                        background: v.productive ? '#d1fae5' : '#ffe4e6',
                        color: v.productive ? '#065f46' : '#be123c',
                      }}>
                        {v.productive ? '✓ Productive' : '✗ Non-Productive'}
                      </div>
                    </div>
                  </InfoWindow>
                )}
              </Marker>
            ))}
          </GoogleMap>
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center">
            <div className="text-slate-400 text-sm">Loading map…</div>
          </div>
        )}

        {/* Loading overlay */}
        {mapLoading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/50 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl px-8 py-6 flex flex-col items-center gap-3">
              <div className="w-8 h-8 rounded-full animate-spin" style={{ border: '3px solid #e0e7ff', borderTopColor: '#6366f1' }} />
              <span className="text-sm font-semibold text-gray-700">Loading route…</span>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 right-4 z-10 bg-white/90 backdrop-blur rounded-xl shadow-lg border border-white/60 px-3 py-2.5">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-emerald-500" />
              <span className="text-[10px] font-medium text-gray-600">Productive</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-rose-400" />
              <span className="text-[10px] font-medium text-gray-600">Non-Productive</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-5 h-0.5 rounded-full bg-indigo-400" />
              <span className="text-[10px] font-medium text-gray-600">Route</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Small stat chip for top bar
function StatChip({ icon, label, value, color }) {
  const colors = {
    indigo:  'bg-indigo-50 text-indigo-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    rose:    'bg-rose-50 text-rose-600',
    amber:   'bg-amber-50 text-amber-700',
    purple:  'bg-purple-50 text-purple-700',
  };
  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold ${colors[color]}`}>
      {icon}
      <span className="hidden sm:inline text-[10px] opacity-70">{label}</span>
      <span>{value}</span>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────
export default function SalesmanJourney() {
  const [activeTab, setActiveTab]     = useState('details');
  const [data, setData]               = useState(null);
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);
  const hasData = useRef(false);
  const [filters, setFilters] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const today = `${y}-${m}-${d}`;
    return { date_from: today, date_to: today };
  });
  const [search, setSearch]     = useState('');
  const [page, setPage]         = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Modal state
  const [modalUser, setModalUser]       = useState(null);
  const [detail, setDetail]             = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    fetchSalesmanJourney(filters)
      .then(res => { if (!cancelled) { setData(res); hasData.current = true; } })
      .catch(err => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) { setLoading(false); setRefreshing(false); } });
    return () => { cancelled = true; };
  }, [filters]);

  useEffect(() => { setPage(1); }, [search, filters, pageSize]);

  const users          = data?.users || [];
  const effectiveDateFrom = data?.effective_date_from;
  const effectiveDateTo   = data?.effective_date_to;

  const filtered = useMemo(() => {
    if (!search) return users;
    const s = search.toLowerCase();
    return users.filter(u =>
      u.user_code?.toLowerCase().includes(s) ||
      u.user_name?.toLowerCase().includes(s) ||
      u.route_code?.toLowerCase().includes(s) ||
      u.route_name?.toLowerCase().includes(s)
    );
  }, [users, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage   = Math.min(page, totalPages);
  const startIdx   = (safePage - 1) * pageSize;
  const paged      = filtered.slice(startIdx, startIdx + pageSize);

  const totalSales     = users.reduce((s, u) => s + (Number(u.total_sales)    || 0), 0);
  const totalCustomers = users.reduce((s, u) => s + (Number(u.customer_count) || 0), 0);
  const totalSku       = users.reduce((s, u) => s + (Number(u.sku_count)      || 0), 0);

  const openModal = (user) => {
    setModalUser(user);
    setDetail(null);
    setDetailLoading(true);
    const detailFilters = {
      ...filters,
      user_code: user.user_code,
      ...(effectiveDateFrom && { date_from: effectiveDateFrom }),
      ...(effectiveDateTo   && { date_to:   effectiveDateTo }),
    };
    fetchSalesmanJourneyDetail(detailFilters)
      .then(setDetail)
      .catch(console.error)
      .finally(() => setDetailLoading(false));
  };

  const closeModal = () => { setModalUser(null); setDetail(null); };

  const exportUsers = () => {
    const header = ['User Code', 'Salesman', 'Route Code', 'Route Name', 'Sales', 'Customers', 'SKUs', 'Productive', 'Non-Productive'].join('\t');
    const rows = filtered.map(u => [
      u.user_code, u.user_name, u.route_code, u.route_name,
      u.total_sales, u.customer_count, u.sku_count,
      u.productive_count, u.non_productive_count
    ].join('\t'));
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'application/vnd.ms-excel' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = 'salesman-journey.xls'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <style>{`
        @keyframes tabFadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
      `}</style>
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Salesman Journey</h1>
        <p className="text-sm text-gray-500 mt-1">Track salesmen routes, visits and performance</p>
      </div>

      <FilterPanel filters={filters} onChange={(f) => {
        if (f.date_from && f.date_from !== filters.date_from) f.date_to = f.date_from;
        setFilters(f);
      }}
        showFields={['date_from', 'sales_org', 'hos', 'asm', 'depot', 'supervisor', 'user_code', 'route']} />

      {loading ? <Loading /> : users.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No data available</div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard title="Salesmen"        value={users.length}                     icon={Users}    color="blue"   variant="light"  />
            <KpiCard title="Total Sales"     value={aed(totalSales)}                  icon={Banknote} color="green"  variant="solid"  />
            <KpiCard title="Total Customers" value={totalCustomers.toLocaleString()}  icon={MapPin}   color="purple" variant="light"  />
            <KpiCard title="Total SKUs"      value={totalSku.toLocaleString()}        icon={Package}  color="indigo" variant="light"  />
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1 p-1 bg-gray-100/80 rounded-2xl w-fit">
            {[
              { key: 'details', label: 'Journey Details', icon: <Users className="w-3.5 h-3.5" /> },
              { key: 'map',     label: 'Map View',        icon: <Map   className="w-3.5 h-3.5" /> },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`relative inline-flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl transition-all duration-200
                  ${activeTab === tab.key
                    ? 'bg-white text-indigo-700 shadow-md shadow-indigo-100/60 scale-[1.02]'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-white/50'}`}
                style={activeTab === tab.key ? { letterSpacing: '-0.01em' } : {}}
              >
                <span className={`transition-colors duration-200 ${activeTab === tab.key ? 'text-indigo-500' : 'text-gray-400'}`}>
                  {tab.icon}
                </span>
                {tab.label}
                {activeTab === tab.key && (
                  <span className="absolute bottom-1.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-indigo-400" />
                )}
              </button>
            ))}
          </div>

          {/* ── Tab: Details ── */}
          {activeTab === 'details' && (
            <div key="details" style={{ animation: 'tabFadeUp 0.22s ease both' }}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="px-6 py-3 border-b border-gray-100 flex items-center justify-between gap-4">
                <div className="relative min-w-[220px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input type="text" placeholder="Search salesman, route..."
                    value={search} onChange={e => setSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200" />
                </div>
                <button onClick={exportUsers}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                  <Download className="w-3.5 h-3.5" /> Export
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {['User Code','Salesman','Route Code','Route Name','Sales','Customers','SKUs','Productive','Non-Productive','Action']
                        .map((h, i) => (
                          <th key={i} className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase
                            ${i < 4 ? 'text-left' : i === 9 ? 'text-center' : 'text-right'}`}>{h}</th>
                        ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {paged.map((u, i) => (
                      <tr key={i} className={`transition-colors hover:bg-indigo-50/40 ${i % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                        <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{u.user_code}</td>
                        <td className="px-4 py-2.5 font-medium text-gray-800">{u.user_name}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{u.route_code}</td>
                        <td className="px-4 py-2.5 text-xs text-gray-600">{u.route_name}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-emerald-700 font-medium">{aed(u.total_sales)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{u.customer_count}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{u.sku_count}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-emerald-600">{u.productive_count}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-rose-500">{u.non_productive_count}</td>
                        <td className="px-4 py-2.5 text-center">
                          <button onClick={() => openModal(u)}
                            className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors">
                            <Eye className="w-3.5 h-3.5" /> View
                          </button>
                        </td>
                      </tr>
                    ))}
                    {paged.length === 0 && (
                      <tr><td colSpan={10} className="px-4 py-12 text-center text-gray-400">No matching records</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="px-6 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
                <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
                  className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none">
                  {PAGE_SIZES.map(s => <option key={s} value={s}>{s} rows</option>)}
                </select>
                <span className="text-xs text-gray-400">
                  {startIdx + 1}–{Math.min(startIdx + pageSize, filtered.length)} of {filtered.length}
                  {search && ` (filtered from ${users.length})`}
                </span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage <= 1}
                    className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 transition-colors">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="text-xs text-gray-500 min-w-[80px] text-center">Page {safePage}/{totalPages}</span>
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}
                    className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 disabled:opacity-30 transition-colors">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Tab: Map ── */}
          {activeTab === 'map' && (
            <div key="map" style={{ animation: 'tabFadeUp 0.22s ease both' }}>
            <MapView
              users={users}
              filters={filters}
              effectiveDateFrom={effectiveDateFrom}
              effectiveDateTo={effectiveDateTo}
            />
            </div>
          )}
        </>
      )}

      {/* ── Detail Modal ── */}
      {modalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
          onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[88vh] flex flex-col"
            onClick={e => e.stopPropagation()}>

            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${avatarGradient(modalUser.user_name)} text-white flex items-center justify-center text-sm font-bold shadow-sm`}>
                  {(modalUser.user_name || '?')[0].toUpperCase()}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">{modalUser.user_name}</h2>
                  <p className="text-xs text-gray-500">{modalUser.user_code} &bull; {modalUser.route_code} &bull; {modalUser.route_name}</p>
                </div>
              </div>
              <button onClick={closeModal}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {detailLoading ? (
                <div className="py-16 text-center"><Loading /></div>
              ) : detail ? (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-emerald-50 rounded-xl border border-emerald-100 p-3 text-center">
                      <div className="text-[10px] text-emerald-600 uppercase font-semibold">Sales</div>
                      <div className="text-base font-bold text-emerald-700">{aed(detail.kpis?.total_sales)}</div>
                    </div>
                    <div className="bg-purple-50 rounded-xl border border-purple-100 p-3 text-center">
                      <div className="text-[10px] text-purple-600 uppercase font-semibold">Collection</div>
                      <div className="text-base font-bold text-purple-700">{aed(detail.kpis?.collection)}</div>
                    </div>
                    <div className="bg-blue-50 rounded-xl border border-blue-100 p-3 text-center">
                      <div className="text-[10px] text-blue-600 uppercase font-semibold">Journey Start</div>
                      <div className="text-base font-bold text-blue-700">{fmtTime(detail.journey_info?.journey_start)}</div>
                    </div>
                    <div className="bg-gray-50 rounded-xl border border-gray-100 p-3 text-center">
                      <div className="text-[10px] text-gray-500 uppercase font-semibold">Journey End</div>
                      <div className="text-base font-bold text-gray-700">{fmtTime(detail.journey_info?.journey_end)}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 px-1">
                    <span className="text-xs font-semibold text-gray-500">{detail.visits?.length || 0} Total Stops</span>
                    <span className="w-1 h-1 rounded-full bg-gray-300" />
                    <span className="text-xs font-semibold text-emerald-600">{detail.visits?.filter(v => v.productive).length || 0} Productive</span>
                    <span className="w-1 h-1 rounded-full bg-gray-300" />
                    <span className="text-xs font-semibold text-rose-500">{detail.visits?.filter(v => !v.productive).length || 0} Non-Productive</span>
                    {detail.journey_info?.vehicle && (
                      <><span className="w-1 h-1 rounded-full bg-gray-300" /><span className="text-xs text-gray-400">Vehicle: {detail.journey_info.vehicle}</span></>
                    )}
                  </div>

                  <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-gray-50 border-b border-gray-100">
                            {['#','Customer','Code','Check In','Check Out','Duration','Status'].map((h, i) => (
                              <th key={i} className={`px-3 py-2.5 font-semibold text-gray-500 uppercase
                                ${i === 5 ? 'text-right' : i === 6 ? 'text-center' : 'text-left'}`}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {(detail.visits || []).map((v, vi) => (
                            <tr key={vi} className={`hover:bg-indigo-50/30 ${vi % 2 !== 0 ? 'bg-gray-50/30' : ''}`}>
                              <td className="px-3 py-2 tabular-nums text-gray-400">{v.sequence}</td>
                              <td className="px-3 py-2 font-medium text-gray-800">{v.customer_name}</td>
                              <td className="px-3 py-2 font-mono text-gray-400">{v.customer_code}</td>
                              <td className="px-3 py-2 tabular-nums text-gray-600">{v.arrival_time || '-'}</td>
                              <td className="px-3 py-2 tabular-nums text-gray-600">{v.out_time || '-'}</td>
                              <td className="px-3 py-2 text-right tabular-nums text-gray-500">{calcDuration(v.arrival_time, v.out_time)}</td>
                              <td className="px-3 py-2 text-center">
                                <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold
                                  ${v.productive ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-50 text-rose-500'}`}>
                                  {v.productive ? 'Productive' : 'Non-Prod'}
                                </span>
                              </td>
                            </tr>
                          ))}
                          {(detail.visits?.length || 0) === 0 && (
                            <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">No visits recorded</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div className="py-16 text-center text-gray-400">No detail available</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
