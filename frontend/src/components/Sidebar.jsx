import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, TrendingUp, Users, Package, BarChart3, Target,
  FileText, Clock, MapPin, Wallet, Activity, Route, PieChart,
  ShoppingCart, CalendarCheck, ClipboardList, RotateCcw, Layers,
  UserCheck, Compass, CirclePercent, WarehouseIcon, Truck
} from 'lucide-react';

const sections = [
  {
    label: 'Overview',
    items: [
      { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    ],
  },
  {
    label: 'Sales',
    items: [
      { path: '/sales-performance', label: 'Sales Performance', icon: TrendingUp },
      { path: '/daily-sales', label: 'Daily Sales Overview', icon: BarChart3 },
      { path: '/mtd-sales', label: 'MTD Sales Overview', icon: Activity },
      { path: '/weekly-sales-returns', label: 'Weekly Sales/Returns', icon: RotateCcw },
      { path: '/brand-wise-sales', label: 'Brand Wise Sales', icon: Layers },
      { path: '/market-sales', label: 'Market Sales', icon: PieChart },
      { path: '/monthly-sales-stock', label: 'Monthly Sales Stock', icon: Package },
      { path: '/revenue-dispersion', label: 'Revenue Dispersion', icon: CirclePercent },
    ],
  },
  {
    label: 'Customers & Products',
    items: [
      { path: '/top-customers', label: 'Top Customers', icon: Users },
      { path: '/top-products', label: 'Top Products', icon: ShoppingCart },
      { path: '/endorsement', label: 'Endorsement', icon: ClipboardList },
      { path: '/mtd-wastage', label: 'MTD Wastage', icon: FileText },
    ],
  },
  {
    label: 'Targets & Productivity',
    items: [
      { path: '/target-achievement', label: 'Target vs Achievement', icon: Target },
      { path: '/productivity', label: 'Productivity & Coverage', icon: Compass },
      { path: '/outstanding', label: 'Outstanding Collection', icon: Wallet },
      { path: '/eot-status', label: 'EOT Status', icon: FileText },
    ],
  },
  {
    label: 'Attendance & Routes',
    items: [
      { path: '/customer-attendance', label: 'Customer Attendance', icon: UserCheck },
      { path: '/mtd-attendance', label: 'MTD Attendance', icon: CalendarCheck },
      { path: '/journey-plan', label: 'Journey Plan Compliance', icon: MapPin },
      { path: '/salesman-journey', label: 'Salesman Journey', icon: Truck },
    ],
  },
  {
    label: 'Logs & Time',
    items: [
      { path: '/log-report', label: 'Log Report', icon: ClipboardList },
      { path: '/time-management', label: 'Time Management', icon: Clock },
    ],
  },
];

export default function Sidebar() {
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

      {/* Footer */}
      <div className="px-5 py-3.5 border-t border-slate-700/40 text-[11px] text-slate-500 font-medium">
        v1.0 &middot; NFPC UAE
      </div>
    </aside>
  );
}
