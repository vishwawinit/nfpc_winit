import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

export const fetchFilters = {
  salesOrgs: () => api.get('/filters/sales-orgs').then(r => r.data),
  asms: (salesOrg) => api.get('/filters/asms', { params: { sales_org: salesOrg } }).then(r => r.data),
  routes: (params) => api.get('/filters/routes', { params }).then(r => r.data),
  users: (params) => api.get('/filters/users', { params }).then(r => r.data),
  customers: (salesOrg) => api.get('/filters/customers', { params: { sales_org: salesOrg } }).then(r => r.data),
  items: () => api.get('/filters/items').then(r => r.data),
  brands: () => api.get('/filters/brands').then(r => r.data),
  channels: () => api.get('/filters/channels').then(r => r.data),
  categories: () => api.get('/filters/categories').then(r => r.data),
  depots: (params) => api.get('/filters/depots', { params }).then(r => r.data),
  supervisors: (params) => api.get('/filters/supervisors', { params }).then(r => r.data),
};

export const fetchDashboard = (params) => api.get('/dashboard', { params }).then(r => r.data);
export const fetchSalesPerformance = (params) => api.get('/sales-performance', { params }).then(r => r.data);
export const fetchTopCustomers = (params) => api.get('/top-customers', { params }).then(r => r.data);
export const fetchTopProducts = (params) => api.get('/top-products', { params }).then(r => r.data);
export const fetchMarketSales = (params) => api.get('/market-sales-performance', { params }).then(r => r.data);
export const fetchTargetAchievement = (params) => api.get('/target-vs-achievement', { params }).then(r => r.data);
export const fetchEndorsement = (params) => api.get('/endorsement', { params }).then(r => r.data);
export const fetchDailySalesOverview = (params) => api.get('/daily-sales-overview', { params }).then(r => r.data);
export const fetchMtdWastage = (params) => api.get('/mtd-wastage-summary', { params }).then(r => r.data);
export const fetchWeeklySalesReturns = (params) => api.get('/weekly-sales-returns', { params }).then(r => r.data);
export const fetchBrandWiseSales = (params) => api.get('/brand-wise-sales', { params }).then(r => r.data);
export const fetchBrandItems = (params) => api.get('/brand-wise-sales/items', { params }).then(r => r.data);
export const fetchMtdSalesOverview = (params) => api.get('/mtd-sales-overview', { params }).then(r => r.data);
export const fetchLogReport = (params) => api.get('/log-report', { params }).then(r => r.data);
export const fetchTimeManagement = (params) => api.get('/time-management', { params }).then(r => r.data);
export const fetchCustomerAttendance = (params) => api.get('/customer-attendance', { params }).then(r => r.data);
export const fetchMtdAttendance = (params) => api.get('/mtd-attendance', { params }).then(r => r.data);
export const fetchJourneyPlanCompliance = (params) => api.get('/journey-plan-compliance', { params }).then(r => r.data);
export const fetchOutstandingCollection = (params) => api.get('/outstanding-collection', { params }).then(r => r.data);
export const fetchOutstandingInvoices = (params) => api.get('/outstanding-collection/invoices', { params }).then(r => r.data);
export const fetchEotStatus = (params) => api.get('/eot-status', { params }).then(r => r.data);
export const fetchProductivityCoverage = (params) => api.get('/productivity-coverage', { params }).then(r => r.data);
export const fetchSalesmanJourney = (params) => api.get('/salesman-journey', { params }).then(r => r.data);
export const fetchRevenueDispersion = (params) => api.get('/revenue-dispersion', { params }).then(r => r.data);
export const fetchMonthlySalesStock = (params) => api.get('/monthly-sales-stock', { params }).then(r => r.data);

export default api;
