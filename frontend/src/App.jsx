import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
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

export default function App() {
  return (
    <div className="flex h-screen bg-[#f8f9fb]">
      <Sidebar />
      <main className="flex-1 px-8 py-6 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sales-performance" element={<SalesPerformance />} />
          <Route path="/top-customers" element={<TopCustomers />} />
          <Route path="/top-products" element={<TopProducts />} />
          <Route path="/market-sales" element={<MarketSales />} />
          <Route path="/target-achievement" element={<TargetAchievement />} />
          <Route path="/endorsement" element={<Endorsement />} />
          <Route path="/daily-sales" element={<DailySalesOverview />} />
          <Route path="/mtd-wastage" element={<MtdWastage />} />
          <Route path="/weekly-sales-returns" element={<WeeklySalesReturns />} />
          <Route path="/brand-wise-sales" element={<BrandWiseSales />} />
          <Route path="/mtd-sales" element={<MtdSalesOverview />} />
          <Route path="/log-report" element={<LogReport />} />
          <Route path="/time-management" element={<TimeManagement />} />
          <Route path="/customer-attendance" element={<CustomerAttendance />} />
          <Route path="/mtd-attendance" element={<MtdAttendance />} />
          <Route path="/journey-plan" element={<JourneyPlanCompliance />} />
          <Route path="/outstanding" element={<OutstandingCollection />} />
          <Route path="/eot-status" element={<EotStatus />} />
          <Route path="/productivity" element={<ProductivityCoverage />} />
          <Route path="/salesman-journey" element={<SalesmanJourney />} />
          <Route path="/revenue-dispersion" element={<RevenueDispersion />} />
          <Route path="/monthly-sales-stock" element={<MonthlySalesStock />} />
        </Routes>
      </main>
    </div>
  );
}
