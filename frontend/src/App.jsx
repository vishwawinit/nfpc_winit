import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import SalesPerformance from './pages/SalesPerformance';
import TopCustomers from './pages/TopCustomers';
import TopProducts from './pages/TopProducts';
import MarketSales from './pages/MarketSales';
import TargetAchievement from './pages/TargetAchievement';
import Endorsement from './pages/Endorsement';
import DailySalesOverview from './pages/DailySalesOverview';
import MtdWastage from './pages/MtdWastage';
import WeeklySalesReturns from './pages/WeeklySalesReturns';
import BrandWiseSales from './pages/BrandWiseSales';
import MtdSalesOverview from './pages/MtdSalesOverview';
import LogReport from './pages/LogReport';
import TimeManagement from './pages/TimeManagement';
import CustomerAttendance from './pages/CustomerAttendance';
import MtdAttendance from './pages/MtdAttendance';
import JourneyPlanCompliance from './pages/JourneyPlanCompliance';
import OutstandingCollection from './pages/OutstandingCollection';
import EotStatus from './pages/EotStatus';
import ProductivityCoverage from './pages/ProductivityCoverage';
import SalesmanJourney from './pages/SalesmanJourney';
import RevenueDispersion from './pages/RevenueDispersion';
import MonthlySalesStock from './pages/MonthlySalesStock';

function ProtectedRoute({ path, element }) {
  const { user, canAccess } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!canAccess(path)) return <Navigate to="/" replace />;
  return element;
}

function AppShell() {
  const { user } = useAuth();
  const location = useLocation();

  if (!user && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }
  if (user && location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }
  if (!user) return <LoginPage />;

  return (
    <div className="flex h-screen bg-[#f8f9fb]">
      <Sidebar />
      <main className="flex-1 px-8 py-6 overflow-y-auto">
        <Routes>
          <Route path="/" element={<ProtectedRoute path="/" element={<Dashboard />} />} />
          <Route path="/sales-performance" element={<ProtectedRoute path="/sales-performance" element={<SalesPerformance />} />} />
          <Route path="/top-customers" element={<ProtectedRoute path="/top-customers" element={<TopCustomers />} />} />
          <Route path="/top-products" element={<ProtectedRoute path="/top-products" element={<TopProducts />} />} />
          <Route path="/market-sales" element={<ProtectedRoute path="/market-sales" element={<MarketSales />} />} />
          <Route path="/target-achievement" element={<ProtectedRoute path="/target-achievement" element={<TargetAchievement />} />} />
          <Route path="/endorsement" element={<ProtectedRoute path="/endorsement" element={<Endorsement />} />} />
          <Route path="/daily-sales" element={<ProtectedRoute path="/daily-sales" element={<DailySalesOverview />} />} />
          <Route path="/mtd-wastage" element={<ProtectedRoute path="/mtd-wastage" element={<MtdWastage />} />} />
          <Route path="/weekly-sales-returns" element={<ProtectedRoute path="/weekly-sales-returns" element={<WeeklySalesReturns />} />} />
          <Route path="/brand-wise-sales" element={<ProtectedRoute path="/brand-wise-sales" element={<BrandWiseSales />} />} />
          <Route path="/mtd-sales" element={<ProtectedRoute path="/mtd-sales" element={<MtdSalesOverview />} />} />
          <Route path="/log-report" element={<ProtectedRoute path="/log-report" element={<LogReport />} />} />
          <Route path="/time-management" element={<ProtectedRoute path="/time-management" element={<TimeManagement />} />} />
          <Route path="/customer-attendance" element={<ProtectedRoute path="/customer-attendance" element={<CustomerAttendance />} />} />
          <Route path="/mtd-attendance" element={<ProtectedRoute path="/mtd-attendance" element={<MtdAttendance />} />} />
          <Route path="/journey-plan" element={<ProtectedRoute path="/journey-plan" element={<JourneyPlanCompliance />} />} />
          <Route path="/outstanding" element={<ProtectedRoute path="/outstanding" element={<OutstandingCollection />} />} />
          <Route path="/eot-status" element={<ProtectedRoute path="/eot-status" element={<EotStatus />} />} />
          <Route path="/productivity" element={<ProtectedRoute path="/productivity" element={<ProductivityCoverage />} />} />
          <Route path="/salesman-journey" element={<ProtectedRoute path="/salesman-journey" element={<SalesmanJourney />} />} />
          <Route path="/revenue-dispersion" element={<ProtectedRoute path="/revenue-dispersion" element={<RevenueDispersion />} />} />
          <Route path="/monthly-sales-stock" element={<ProtectedRoute path="/monthly-sales-stock" element={<MonthlySalesStock />} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<AppShell />} />
      </Routes>
    </AuthProvider>
  );
}
