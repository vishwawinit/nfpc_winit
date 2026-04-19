import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, TrendingUp, Users, Package, BarChart3, Target,
  FileText, Clock, MapPin, Wallet, Activity, Route, PieChart,
  ShoppingCart, CalendarCheck, ClipboardList, RotateCcw, Layers,
  UserCheck, Compass, CirclePercent, Truck, LogOut, ChevronRight,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const ALL_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    ],
  },
  {
    label: 'Sales',
    items: [
      { path: '/sales-performance',    label: 'Sales Performance',       icon: TrendingUp },
      { path: '/daily-sales',          label: 'Daily Sales Overview',    icon: BarChart3 },
      { path: '/mtd-sales',            label: 'MTD Sales Overview',      icon: Activity },
      { path: '/weekly-sales-returns', label: 'Weekly Sales/Returns',    icon: RotateCcw },
      { path: '/brand-wise-sales',     label: 'Brand Wise Sales',        icon: Layers },
      { path: '/market-sales',         label: 'Market Sales',            icon: PieChart },
      { path: '/monthly-sales-stock',  label: 'Monthly Sales By Channel',icon: Package },
      { path: '/revenue-dispersion',   label: 'Revenue Dispersion',      icon: CirclePercent },
    ],
  },
  {
    label: 'Customers & Products',
    items: [
      { path: '/top-customers', label: 'Top Customers', icon: Users },
      { path: '/top-products',  label: 'Top Products',  icon: ShoppingCart },
      { path: '/endorsement',   label: 'Endorsement',   icon: ClipboardList },
      { path: '/mtd-wastage',   label: 'MTD Wastage',   icon: FileText },
    ],
  },
  {
    label: 'Targets & Productivity',
    items: [
      { path: '/target-achievement', label: 'Target vs Achievement',  icon: Target },
      { path: '/productivity',       label: 'Productivity & Coverage', icon: Compass },
      { path: '/outstanding',        label: 'Outstanding Collection',  icon: Wallet },
      { path: '/eot-status',         label: 'EOT Status',             icon: FileText },
    ],
  },
  {
    label: 'Attendance & Routes',
    items: [
      { path: '/customer-attendance', label: 'Customer Attendance',     icon: UserCheck },
      { path: '/mtd-attendance',      label: 'MTD Attendance',          icon: CalendarCheck },
      { path: '/journey-plan',        label: 'Journey Plan Compliance', icon: MapPin },
      { path: '/salesman-journey',    label: 'Salesman Journey',        icon: Truck },
    ],
  },
  {
    label: 'Logs & Time',
    items: [
      { path: '/log-report',      label: 'Log Report',      icon: ClipboardList },
      { path: '/time-management', label: 'Time Management', icon: Clock },
    ],
  },
];

const ROLE_BADGE = {
  GCD:                 { label: 'GCD',        color: 'bg-violet-500/20 text-violet-300' },
  HOS:                 { label: 'HOS',        color: 'bg-indigo-500/20 text-indigo-300' },
  NSM:                 { label: 'NSM',        color: 'bg-sky-500/20 text-sky-300' },
  ASM:                 { label: 'ASM',        color: 'bg-blue-500/20 text-blue-300' },
  C_SALES_SUPERVISOR:  { label: 'Supervisor', color: 'bg-teal-500/20 text-teal-300' },
  FreshSup:            { label: 'Supervisor', color: 'bg-teal-500/20 text-teal-300' },
  AMBIENTSUP:          { label: 'Supervisor', color: 'bg-teal-500/20 text-teal-300' },
  C_PRESALES_VANSALES: { label: 'Salesman',   color: 'bg-emerald-500/20 text-emerald-300' },
  Vansales:            { label: 'Salesman',   color: 'bg-emerald-500/20 text-emerald-300' },
  Storekeeper:         { label: 'Storekeeper',color: 'bg-amber-500/20 text-amber-300' },
};

export default function Sidebar() {
  const { user, logout } = useAuth();

  const sections = ALL_SECTIONS;

  const badge = ROLE_BADGE[user?.role_code] || { label: user?.role_name || user?.role_code || '', color: 'bg-slate-500/20 text-slate-300' };

  return (
    <aside className="w-[244px] bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white min-h-screen flex-shrink-0 flex flex-col border-r border-slate-700/30">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-slate-700/40">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <span className="text-[13px] font-bold text-white">N</span>
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-white">NFPC Reports</div>
            <div className="text-[10px] text-slate-400 font-medium tracking-wide">Enterprise Dashboard</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5 scrollbar-thin">
        {sections.map((section) => (
          <div key={section.label}>
            <div className="px-2.5 mb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-[0.08em]">
              {section.label}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === '/'}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[13px] transition-all duration-150 ${
                        isActive
                          ? 'bg-indigo-500/15 text-white font-medium border-l-[3px] border-indigo-400 pl-[7px]'
                          : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
                      }`
                    }
                  >
                    <Icon className="w-[15px] h-[15px] flex-shrink-0" strokeWidth={1.75} />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User Info + Logout */}
      <div className="px-3 py-3 border-t border-slate-700/40">
        <div className="flex items-center gap-2.5 px-2.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.05]">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 flex items-center justify-center flex-shrink-0">
            <span className="text-[12px] font-bold text-indigo-300">
              {user?.user_name?.[0]?.toUpperCase() || 'U'}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-semibold text-slate-200 truncate">{user?.user_name}</div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${badge.color}`}>
                {badge.label}
              </span>
              <span className="text-[10px] text-slate-500 font-mono truncate">{user?.user_code}</span>
            </div>
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors flex-shrink-0"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
