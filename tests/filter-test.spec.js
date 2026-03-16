// @ts-check
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'https://nfpc-app-production.up.railway.app';
const API = `${BASE}/api`;

// ── Helpers ──────────────────────────────────────────────────────────────────

async function apiFetch(request, path, params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  }
  const url = `${API}${path}?${qs}`;
  const res = await request.get(url, { timeout: 30000 });
  expect(res.ok(), `API ${url} returned ${res.status()}`).toBeTruthy();
  return res.json();
}

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

async function selectByLabel(page, labelText, value) {
  const label = page.locator('label', { hasText: labelText });
  const select = label.locator('..').locator('select');
  await select.selectOption(value);
}

async function setDate(page, labelText, value) {
  const label = page.locator('label', { hasText: labelText });
  const input = label.locator('..').locator('input[type="date"]');
  await input.fill(value);
}

async function waitForData(page) {
  await page.waitForLoadState('networkidle', { timeout: 30000 });
  await page.waitForTimeout(500);
}

// ── Filter options (loaded once) ─────────────────────────────────────────────

let filterOptions = {};

test.beforeAll(async ({ request }) => {
  const [salesOrgs, routes, users, channels, brands, categories] = await Promise.all([
    apiFetch(request, '/filters/sales-orgs'),
    apiFetch(request, '/filters/routes'),
    apiFetch(request, '/filters/users'),
    apiFetch(request, '/filters/channels'),
    apiFetch(request, '/filters/brands'),
    apiFetch(request, '/filters/categories'),
  ]);
  filterOptions = { salesOrgs, routes, users, channels, brands, categories };
  console.log(`Loaded: ${salesOrgs.length} orgs, ${routes.length} routes, ${users.length} users, ${channels.length} channels, ${brands.length} brands, ${categories.length} categories`);
});

// ── Report definitions with CORRECT response shapes ──────────────────────────

const REPORTS = [
  {
    name: 'Dashboard',
    apiPath: '/dashboard',
    uiPath: '/',
    filters: ['date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-07' },
      { date_from: '2026-02-15', date_to: '2026-03-01' },
      { date_from: '2026-03-01', date_to: '2026-03-07', sales_org: 'NFPC' },
      { date_from: '2026-02-20', date_to: '2026-03-05', sales_org: '00010' },
    ],
    validate: (d) => { expect(d).toHaveProperty('total_sales'); expect(d).toHaveProperty('total_collection'); },
  },
  {
    name: 'Sales Performance',
    apiPath: '/sales-performance',
    uiPath: '/sales-performance',
    filters: ['route', 'month', 'year', 'sales_org'],
    combos: [
      { month: 3, year: 2026 },
      { month: 2, year: 2026 },
      { month: 3, year: 2026, sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('sku_table'); },
  },
  {
    name: 'Top Customers',
    apiPath: '/top-customers',
    uiPath: '/top-customers',
    filters: ['sales_org', 'user_code', 'channel', 'month', 'year'],
    combos: [
      { month: 3, year: 2026 },
      { month: 3, year: 2026, sales_org: 'NFPC' },
      { month: 2, year: 2026 },
    ],
    validate: (d) => { expect(d).toHaveProperty('data'); expect(Array.isArray(d.data)).toBeTruthy(); },
  },
  {
    name: 'Top Products',
    apiPath: '/top-products',
    uiPath: '/top-products',
    filters: ['sales_org', 'user_code', 'month', 'year'],
    combos: [
      { month: 3, year: 2026 },
      { month: 3, year: 2026, sales_org: 'NFPC' },
      { month: 2, year: 2026 },
    ],
    validate: (d) => { expect(d).toHaveProperty('data'); expect(Array.isArray(d.data)).toBeTruthy(); },
  },
  {
    name: 'Market Sales',
    apiPath: '/market-sales-performance',
    uiPath: '/market-sales',
    filters: ['sales_org', 'year'],
    combos: [
      { year: 2026 },
      { year: 2026, sales_org: 'NFPC' },
      { year: 2026, sales_org: '00010' },
    ],
    validate: (d) => { expect(d).toHaveProperty('monthly_data'); },
  },
  {
    name: 'Target vs Achievement',
    apiPath: '/target-vs-achievement',
    uiPath: '/target-vs-achievement',
    filters: ['sales_org', 'route', 'month', 'year'],
    combos: [
      { year: 2026, month: 3 },
      { year: 2026, month: 2 },
      { year: 2026, month: 3, sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('total_target'); },
  },
  {
    name: 'Endorsement',
    apiPath: '/endorsement',
    uiPath: '/endorsement',
    filters: ['route', 'date_from', 'date_to', 'sales_org', 'user_code'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('header'); expect(d).toHaveProperty('customers'); },
  },
  {
    name: 'Daily Sales Overview',
    apiPath: '/daily-sales-overview',
    uiPath: '/daily-sales-overview',
    filters: ['date_from', 'date_to', 'sales_org', 'route', 'user_code'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
      { date_from: '2026-02-15', date_to: '2026-03-01' },
    ],
    validate: (d) => { expect(d).toHaveProperty('sales_details'); expect(d).toHaveProperty('item_table'); },
  },
  {
    name: 'MTD Wastage',
    apiPath: '/mtd-wastage-summary',
    uiPath: '/mtd-wastage',
    filters: ['route', 'date_from', 'date_to', 'sales_org', 'user_code'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('summary'); expect(d).toHaveProperty('details'); },
  },
  {
    name: 'Weekly Sales Returns',
    apiPath: '/weekly-sales-returns',
    uiPath: '/weekly-sales-returns',
    filters: ['sales_org', 'user_code', 'date_from', 'date_to', 'route'],
    combos: [
      { date_from: '2026-02-11', date_to: '2026-03-12' },
      { date_from: '2026-02-11', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('weekly_data'); expect(d).toHaveProperty('totals'); },
  },
  {
    name: 'Brand Wise Sales',
    apiPath: '/brand-wise-sales',
    uiPath: '/brand-wise-sales',
    filters: ['sales_org', 'brand', 'user_code', 'date_from', 'date_to', 'route'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('summary'); expect(d).toHaveProperty('brands'); },
  },
  {
    name: 'MTD Sales Overview',
    apiPath: '/mtd-sales-overview',
    uiPath: '/mtd-sales-overview',
    filters: ['route', 'user_code', 'date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toBeDefined(); },
  },
  {
    name: 'Log Report',
    apiPath: '/log-report',
    uiPath: '/log-report',
    filters: ['sales_org', 'user_code', 'date_from', 'date_to'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('call_summary'); expect(d).toHaveProperty('user_data'); },
  },
  {
    name: 'Time Management',
    apiPath: '/time-management',
    uiPath: '/time-management',
    filters: ['user_code', 'date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(Array.isArray(d)).toBeTruthy(); },
  },
  {
    name: 'Customer Attendance',
    apiPath: '/customer-attendance',
    uiPath: '/customer-attendance',
    filters: ['user_code', 'date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(Array.isArray(d)).toBeTruthy(); },
  },
  {
    name: 'MTD Attendance',
    apiPath: '/mtd-attendance',
    uiPath: '/mtd-attendance',
    filters: ['user_code', 'date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(Array.isArray(d)).toBeTruthy(); },
  },
  {
    name: 'Journey Plan Compliance',
    apiPath: '/journey-plan-compliance',
    uiPath: '/journey-plan-compliance',
    filters: ['user_code', 'date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('summary'); expect(d).toHaveProperty('drill_down'); },
  },
  {
    name: 'Outstanding Collection',
    apiPath: '/outstanding-collection',
    uiPath: '/outstanding-collection',
    filters: ['sales_org', 'user_code', 'route'],
    combos: [
      { sales_org: 'NFPC' },
      { sales_org: '00010' },
    ],
    validate: (d) => { expect(d).toHaveProperty('aging_buckets'); expect(d).toHaveProperty('customers'); },
  },
  {
    name: 'EOT Status',
    apiPath: '/eot-status',
    uiPath: '/eot-status',
    filters: ['route', 'date_from', 'date_to', 'user_code', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('user_info'); expect(d).toHaveProperty('kpis'); },
  },
  {
    name: 'Productivity & Coverage',
    apiPath: '/productivity-coverage',
    uiPath: '/productivity-coverage',
    filters: ['date_from', 'date_to', 'sales_org'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('summary'); expect(d).toHaveProperty('users'); },
  },
  {
    name: 'Revenue Dispersion',
    apiPath: '/revenue-dispersion',
    uiPath: '/revenue-dispersion',
    filters: ['sales_org', 'user_code', 'date_from', 'date_to'],
    combos: [
      { date_from: '2026-02-11', date_to: '2026-03-12' },
      { date_from: '2026-02-11', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('revenue_dispersion'); expect(d).toHaveProperty('sku_dispersion'); },
  },
  {
    name: 'Monthly Sales Stock',
    apiPath: '/monthly-sales-stock',
    uiPath: '/monthly-sales-stock',
    filters: ['sales_org', 'brand', 'category', 'date_from', 'date_to'],
    combos: [
      { date_from: '2026-03-01', date_to: '2026-03-12' },
      { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' },
    ],
    validate: (d) => { expect(d).toHaveProperty('items'); },
  },
];

// ══════════════════════════════════════════════════════════════════════════════
// PHASE 1: API Filter Combinations (all 22 reports x multiple combos + random)
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Phase 1: API Filter Combinations', () => {
  test.setTimeout(30000);

  for (const report of REPORTS) {
    test.describe(report.name, () => {
      // Fixed combos
      for (let i = 0; i < report.combos.length; i++) {
        const combo = report.combos[i];
        test(`combo ${i + 1}: ${JSON.stringify(combo)}`, async ({ request }) => {
          const data = await apiFetch(request, report.apiPath, combo);
          expect(data).toBeDefined();
          report.validate(data);
        });
      }

      // Random combos per filter type
      if (report.filters.includes('sales_org')) {
        test('+ random sales_org', async ({ request }) => {
          const org = pick(filterOptions.salesOrgs);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], sales_org: org.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + org=${org.code}: OK`);
        });
      }
      if (report.filters.includes('route')) {
        test('+ random route', async ({ request }) => {
          const r = pick(filterOptions.routes);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], route: r.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + route=${r.code}: OK`);
        });
      }
      if (report.filters.includes('user_code')) {
        test('+ random user', async ({ request }) => {
          const u = pick(filterOptions.users);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], user_code: u.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + user=${u.code}: OK`);
        });
      }
      if (report.filters.includes('channel')) {
        test('+ random channel', async ({ request }) => {
          const c = pick(filterOptions.channels);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], channel: c.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + channel=${c.code}: OK`);
        });
      }
      if (report.filters.includes('brand')) {
        test('+ random brand', async ({ request }) => {
          const b = pick(filterOptions.brands);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], brand: b.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + brand=${b.code}: OK`);
        });
      }
      if (report.filters.includes('category')) {
        test('+ random category', async ({ request }) => {
          const c = pick(filterOptions.categories);
          const data = await apiFetch(request, report.apiPath, { ...report.combos[0], category: c.code });
          expect(data).toBeDefined();
          console.log(`  ${report.name} + category=${c.code}: OK`);
        });
      }
    });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// PHASE 2: Cross-Filter Data Consistency
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Phase 2: Cross-Filter Data Consistency', () => {
  test.setTimeout(60000);

  test('Dashboard: sum of all orgs equals total', async ({ request }) => {
    const params = { date_from: '2026-03-01', date_to: '2026-03-07' };
    const allData = await apiFetch(request, '/dashboard', params);
    let orgSum = 0;
    for (const org of filterOptions.salesOrgs) {
      const d = await apiFetch(request, '/dashboard', { ...params, sales_org: org.code });
      orgSum += d.total_sales || 0;
    }
    const pct = allData.total_sales > 0 ? Math.abs(allData.total_sales - orgSum) / allData.total_sales * 100 : 0;
    console.log(`Dashboard sum check: total=${allData.total_sales}, orgSum=${orgSum}, diff=${pct.toFixed(4)}%`);
    expect(pct).toBeLessThan(1);
  });

  test('Top Customers: org filter returns subset', async ({ request }) => {
    const all = await apiFetch(request, '/top-customers', { month: 3, year: 2026 });
    const nfpc = await apiFetch(request, '/top-customers', { month: 3, year: 2026, sales_org: 'NFPC' });
    expect(nfpc.data.length).toBeLessThanOrEqual(all.data.length);
    console.log(`Top Customers: All=${all.data.length}, NFPC=${nfpc.data.length}`);
  });

  test('Top Products: org filter returns subset', async ({ request }) => {
    const all = await apiFetch(request, '/top-products', { month: 3, year: 2026 });
    const nfpc = await apiFetch(request, '/top-products', { month: 3, year: 2026, sales_org: 'NFPC' });
    expect(nfpc.data.length).toBeLessThanOrEqual(all.data.length);
    console.log(`Top Products: All=${all.data.length}, NFPC=${nfpc.data.length}`);
  });

  test('Future dates return zero', async ({ request }) => {
    const d = await apiFetch(request, '/dashboard', { date_from: '2027-01-01', date_to: '2027-01-31' });
    expect(d.total_sales).toBe(0);
    console.log('Future dates: zero sales PASS');
  });

  test('Narrow date range <= wide date range', async ({ request }) => {
    const narrow = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-03' });
    const wide = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-07' });
    expect(wide.total_sales).toBeGreaterThanOrEqual(narrow.total_sales);
    console.log(`Narrow=${narrow.total_sales}, Wide=${wide.total_sales}: OK`);
  });

  test('Brand Wise Sales: org filter reduces brands', async ({ request }) => {
    const all = await apiFetch(request, '/brand-wise-sales', { date_from: '2026-03-01', date_to: '2026-03-12' });
    const nfpc = await apiFetch(request, '/brand-wise-sales', { date_from: '2026-03-01', date_to: '2026-03-12', sales_org: 'NFPC' });
    expect(nfpc.brands.length).toBeLessThanOrEqual(all.brands.length);
    console.log(`Brands: All=${all.brands.length}, NFPC=${nfpc.brands.length}`);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// PHASE 3: Browser UI vs API Data Comparison
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Phase 3: Browser UI vs API', () => {
  test.setTimeout(60000);

  test('Dashboard: UI total matches API', async ({ page, request }) => {
    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-07' });
    await page.goto(`${BASE}/`);
    await waitForData(page);
    const txt = await page.locator('text=TOTAL SALES').locator('..').textContent();
    const ui = parseFloat(txt.replace(/[^0-9.]/g, ''));
    console.log(`Dashboard: UI=${ui}, API=${Math.round(api.total_sales)}`);
    expect(Math.abs(ui - Math.round(api.total_sales))).toBeLessThan(Math.round(api.total_sales) * 0.01);
  });

  test('Dashboard: sales_org filter changes data', async ({ page, request }) => {
    await page.goto(`${BASE}/`);
    await waitForData(page);
    const beforeTxt = await page.locator('text=TOTAL SALES').locator('..').textContent();
    const before = parseFloat(beforeTxt.replace(/[^0-9.]/g, ''));

    await selectByLabel(page, 'Sales Org', 'NFPC');
    await waitForData(page);
    const afterTxt = await page.locator('text=TOTAL SALES').locator('..').textContent();
    const after = parseFloat(afterTxt.replace(/[^0-9.]/g, ''));

    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-07', sales_org: 'NFPC' });
    console.log(`Dashboard NFPC: UI=${after}, API=${Math.round(api.total_sales)}, was=${before}`);
    expect(after).toBeLessThanOrEqual(before);
    expect(Math.abs(after - Math.round(api.total_sales))).toBeLessThan(Math.max(Math.round(api.total_sales) * 0.01, 1));
  });

  test('Dashboard: date change updates data', async ({ page, request }) => {
    await page.goto(`${BASE}/`);
    await waitForData(page);
    await setDate(page, 'From', '2026-03-05');
    await setDate(page, 'To', '2026-03-07');
    await waitForData(page);
    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-05', date_to: '2026-03-07' });
    const txt = await page.locator('text=TOTAL SALES').locator('..').textContent();
    const ui = parseFloat(txt.replace(/[^0-9.]/g, ''));
    console.log(`Dashboard narrow: UI=${ui}, API=${Math.round(api.total_sales)}`);
    expect(Math.abs(ui - Math.round(api.total_sales))).toBeLessThan(Math.max(Math.round(api.total_sales) * 0.01, 1));
  });

  test('Sales Performance: table rows match API', async ({ page, request }) => {
    const api = await apiFetch(request, '/sales-performance', { month: 3, year: 2026 });
    await page.goto(`${BASE}/sales-performance`);
    await waitForData(page);
    const rows = await page.locator('table tbody tr').count();
    console.log(`Sales Perf: API=${api.sku_table?.length}, UI=${rows}`);
    expect(rows).toBeGreaterThan(0);
    if (api.sku_table) expect(rows).toBe(api.sku_table.length);
  });

  test('Outstanding Collection: loads with NFPC', async ({ page, request }) => {
    const api = await apiFetch(request, '/outstanding-collection', { sales_org: 'NFPC' });
    await page.goto(`${BASE}/outstanding-collection`);
    await waitForData(page);
    await selectByLabel(page, 'Sales Org', 'NFPC');
    await waitForData(page);
    const body = await page.textContent('body');
    expect(body.length).toBeGreaterThan(100);
    console.log(`Outstanding NFPC: API buckets=${api.aging_buckets?.length}, page loaded`);
  });

  // Quick load test for all remaining pages
  const PAGES = [
    '/top-customers', '/top-products', '/market-sales', '/target-vs-achievement',
    '/daily-sales-overview', '/mtd-wastage', '/weekly-sales-returns', '/brand-wise-sales',
    '/mtd-sales-overview', '/log-report', '/time-management', '/customer-attendance',
    '/mtd-attendance', '/journey-plan-compliance', '/eot-status', '/productivity-coverage',
    '/revenue-dispersion', '/monthly-sales-stock',
  ];

  for (const path of PAGES) {
    test(`${path} loads without crash`, async ({ page }) => {
      const errors = [];
      page.on('pageerror', err => errors.push(err.message));
      await page.goto(`${BASE}${path}`);
      await waitForData(page);
      const body = await page.textContent('body');
      expect(body.length).toBeGreaterThan(50);
      const critical = errors.filter(e => !e.includes('ResizeObserver'));
      if (critical.length) console.log(`  ${path} errors:`, critical);
      console.log(`  ${path}: OK (${body.length} chars)`);
    });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// PHASE 4: Filter Dropdown Population
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Phase 4: Filter Dropdowns', () => {
  test('Sales org dropdown populates', async ({ page }) => {
    await page.goto(`${BASE}/`);
    await waitForData(page);
    const opts = await page.locator('select').first().locator('option').count();
    expect(opts).toBeGreaterThan(1);
    console.log(`Sales org dropdown: ${opts} options`);
  });

  test('Routes filter by sales_org', async ({ request }) => {
    const all = await apiFetch(request, '/filters/routes');
    const nfpc = await apiFetch(request, '/filters/routes', { sales_org: 'NFPC' });
    expect(nfpc.length).toBeLessThanOrEqual(all.length);
    expect(nfpc.length).toBeGreaterThan(0);
    console.log(`Routes: all=${all.length}, NFPC=${nfpc.length}`);
  });

  test('Users filter by sales_org', async ({ request }) => {
    const all = await apiFetch(request, '/filters/users');
    const nfpc = await apiFetch(request, '/filters/users', { sales_org: 'NFPC' });
    expect(nfpc.length).toBeLessThanOrEqual(all.length);
    expect(nfpc.length).toBeGreaterThan(0);
    console.log(`Users: all=${all.length}, NFPC=${nfpc.length}`);
  });

  test('All filter endpoints valid', async ({ request }) => {
    for (const ep of ['/filters/sales-orgs', '/filters/routes', '/filters/users', '/filters/channels', '/filters/brands', '/filters/categories']) {
      const data = await apiFetch(request, ep);
      expect(Array.isArray(data)).toBeTruthy();
      expect(data.length).toBeGreaterThan(0);
      expect(data[0]).toHaveProperty('code');
      expect(data[0]).toHaveProperty('name');
      console.log(`  ${ep}: ${data.length}`);
    }
  });
});
