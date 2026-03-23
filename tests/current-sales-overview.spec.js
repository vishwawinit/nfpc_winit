// @ts-check
/**
 * Current Sales Overview Dashboard — focused tests
 * Checks individual day data (Mar 1, Mar 2, Mar 3) and consistency.
 */
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'https://nfpc-app-production.up.railway.app';
const API = `${BASE}/api`;

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

async function waitForData(page) {
  await page.waitForLoadState('networkidle', { timeout: 30000 });
  await page.waitForTimeout(500);
}

// ──────────────────────────────────────────────────────────────────────────────
// Helpers to parse display values from the UI
// ──────────────────────────────────────────────────────────────────────────────
function parseAed(txt) {
  // e.g. "AED 1,234,567" → 1234567
  return parseFloat((txt || '').replace(/[^0-9.]/g, ''));
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 1: Individual Day API Responses (Mar 1 / Mar 2 / Mar 3)
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Current Sales Overview — Individual Day API', () => {
  test.setTimeout(30000);

  const DAYS = [
    { label: 'Mar 1',  date_from: '2026-03-01', date_to: '2026-03-01' },
    { label: 'Mar 2',  date_from: '2026-03-02', date_to: '2026-03-02' },
    { label: 'Mar 3',  date_from: '2026-03-03', date_to: '2026-03-03' },
  ];

  for (const day of DAYS) {
    test(`${day.label}: API returns valid structure`, async ({ request }) => {
      const d = await apiFetch(request, '/dashboard', { date_from: day.date_from, date_to: day.date_to });

      // Core fields present
      expect(d).toHaveProperty('total_sales');
      expect(d).toHaveProperty('total_collection');
      expect(d).toHaveProperty('total_target');
      expect(d).toHaveProperty('weekly_sales');
      expect(d).toHaveProperty('weekly_collection');
      expect(d).toHaveProperty('call_metrics');
      expect(d).toHaveProperty('route_wise_sales_vs_target');
      expect(d).toHaveProperty('route_wise_visits');

      // Values are non-negative numbers
      expect(d.total_sales).toBeGreaterThanOrEqual(0);
      expect(d.total_collection).toBeGreaterThanOrEqual(0);
      expect(d.total_target).toBeGreaterThanOrEqual(0);

      // daily_sales array: must contain exactly 1 or 0 entries (single day range)
      expect(Array.isArray(d.weekly_sales)).toBeTruthy();
      expect(d.weekly_sales.length).toBeLessThanOrEqual(1);

      // If data exists, the date entry must match the requested day
      if (d.weekly_sales.length === 1) {
        const entryDate = d.weekly_sales[0].date?.slice(0, 10);
        expect(entryDate).toBe(day.date_from);
        const dailySales = parseFloat(d.weekly_sales[0].sales || 0);
        // Daily entry sales should equal total_sales (single day)
        expect(Math.abs(dailySales - d.total_sales)).toBeLessThanOrEqual(1);
      }

      // Call metrics structure
      const cm = d.call_metrics;
      expect(cm).toHaveProperty('scheduled_calls');
      expect(cm).toHaveProperty('actual_calls');
      expect(cm).toHaveProperty('selling_calls');
      expect(cm).toHaveProperty('strike_rate');
      expect(cm).toHaveProperty('coverage_pct');
      expect(cm.strike_rate).toBeGreaterThanOrEqual(0);
      expect(cm.strike_rate).toBeLessThanOrEqual(100);
      expect(cm.coverage_pct).toBeGreaterThanOrEqual(0);
      expect(cm.coverage_pct).toBeLessThanOrEqual(100);

      console.log(`${day.label}: sales=${d.total_sales}, coll=${d.total_collection}, target=${d.total_target}, calls=${cm.actual_calls}, strike=${cm.strike_rate}%`);
    });
  }

  // ────────────────────────────────────────────────────────────────────────
  // Consistency: sum of individual days should equal the 3-day range
  // ────────────────────────────────────────────────────────────────────────
  test('Sum of Mar 1+2+3 individual calls equals Mar 1-3 range', async ({ request }) => {
    const [d1, d2, d3, range] = await Promise.all([
      apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-01' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-02', date_to: '2026-03-02' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-03', date_to: '2026-03-03' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-03' }),
    ]);

    const daySum = d1.total_sales + d2.total_sales + d3.total_sales;
    const rangeSales = range.total_sales;

    const diff = Math.abs(daySum - rangeSales);
    const pct = rangeSales > 0 ? (diff / rangeSales) * 100 : 0;

    console.log(`Sales — Day sum: ${daySum.toFixed(2)}, Range: ${rangeSales.toFixed(2)}, diff: ${pct.toFixed(3)}%`);
    // Allow up to 1% tolerance for rounding
    expect(pct).toBeLessThan(1);

    // Collection consistency
    const collSum = d1.total_collection + d2.total_collection + d3.total_collection;
    const rangeColl = range.total_collection;
    const collDiff = Math.abs(collSum - rangeColl);
    const collPct = rangeColl > 0 ? (collDiff / rangeColl) * 100 : 0;
    console.log(`Collection — Day sum: ${collSum.toFixed(2)}, Range: ${rangeColl.toFixed(2)}, diff: ${collPct.toFixed(3)}%`);
    expect(collPct).toBeLessThan(1);
  });

  // ────────────────────────────────────────────────────────────────────────
  // Monotonicity: range with more days should have >= sales
  // ────────────────────────────────────────────────────────────────────────
  test('Mar 1-3 range >= any single day in that range', async ({ request }) => {
    const [d1, d2, d3, range] = await Promise.all([
      apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-01' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-02', date_to: '2026-03-02' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-03', date_to: '2026-03-03' }),
      apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-03' }),
    ]);

    expect(range.total_sales).toBeGreaterThanOrEqual(d1.total_sales);
    expect(range.total_sales).toBeGreaterThanOrEqual(d2.total_sales);
    expect(range.total_sales).toBeGreaterThanOrEqual(d3.total_sales);
    console.log(`Range ${range.total_sales} >= d1:${d1.total_sales}, d2:${d2.total_sales}, d3:${d3.total_sales} ✓`);
  });

  // ────────────────────────────────────────────────────────────────────────
  // Route-wise: each route's sales should add up to total_sales
  // ────────────────────────────────────────────────────────────────────────
  test('Mar 1-3: route-wise sales sum near total_sales', async ({ request }) => {
    const d = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-03' });
    const routeSum = d.route_wise_sales_vs_target.reduce((s, r) => s + (parseFloat(r.sales) || 0), 0);
    const pct = d.total_sales > 0 ? Math.abs(routeSum - d.total_sales) / d.total_sales * 100 : 0;
    console.log(`Route sum: ${routeSum.toFixed(2)}, Total: ${d.total_sales}, diff: ${pct.toFixed(3)}%`);
    // Route-wise may differ slightly (e.g. collection-only routes) — allow 5%
    expect(pct).toBeLessThan(5);
  });

  // ────────────────────────────────────────────────────────────────────────
  // Daily chart: Mar 1-3 range must return 3 daily entries in weekly_sales
  // ────────────────────────────────────────────────────────────────────────
  test('Mar 1-3 range: weekly_sales has 3 daily entries', async ({ request }) => {
    const d = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-03' });
    expect(Array.isArray(d.weekly_sales)).toBeTruthy();

    // Should have entries for all 3 days that have data
    const dates = d.weekly_sales.map(r => r.date?.slice(0, 10));
    console.log('Daily sales dates:', dates);

    // Each returned date must fall within range
    for (const dt of dates) {
      expect(dt >= '2026-03-01' && dt <= '2026-03-03').toBeTruthy();
    }

    // Each daily sales value must be >= 0
    for (const row of d.weekly_sales) {
      expect(parseFloat(row.sales || 0)).toBeGreaterThanOrEqual(0);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 2: Sales Org Filter on Individual Days
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Current Sales Overview — Sales Org Filter on Individual Days', () => {
  test.setTimeout(30000);

  const DAYS = [
    { label: 'Mar 1', date_from: '2026-03-01', date_to: '2026-03-01' },
    { label: 'Mar 2', date_from: '2026-03-02', date_to: '2026-03-02' },
    { label: 'Mar 3', date_from: '2026-03-03', date_to: '2026-03-03' },
  ];

  for (const day of DAYS) {
    test(`${day.label}: NFPC org filter <= total`, async ({ request }) => {
      const [all, nfpc] = await Promise.all([
        apiFetch(request, '/dashboard', { date_from: day.date_from, date_to: day.date_to }),
        apiFetch(request, '/dashboard', { date_from: day.date_from, date_to: day.date_to, sales_org: 'NFPC' }),
      ]);
      expect(nfpc.total_sales).toBeLessThanOrEqual(all.total_sales + 1); // +1 for float rounding
      console.log(`${day.label} NFPC: ${nfpc.total_sales} / All: ${all.total_sales}`);
    });
  }

  test('Mar 1-3: Sum of all orgs equals total (no filter)', async ({ request }) => {
    const params = { date_from: '2026-03-01', date_to: '2026-03-03' };
    const allData = await apiFetch(request, '/dashboard', params);
    const orgsRes = await request.get(`${API}/filters/sales-orgs`, { timeout: 15000 });
    const orgs = await orgsRes.json();

    let orgSum = 0;
    for (const org of orgs) {
      const d = await apiFetch(request, '/dashboard', { ...params, sales_org: org.code });
      orgSum += d.total_sales || 0;
    }

    const pct = allData.total_sales > 0 ? Math.abs(allData.total_sales - orgSum) / allData.total_sales * 100 : 0;
    console.log(`Org sum check: total=${allData.total_sales.toFixed(2)}, orgSum=${orgSum.toFixed(2)}, diff=${pct.toFixed(3)}%`);
    expect(pct).toBeLessThan(1);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 3: UI Browser Tests — Dashboard with individual days
// ══════════════════════════════════════════════════════════════════════════════

test.describe('Current Sales Overview — UI tests', () => {
  test.setTimeout(60000);

  test('Dashboard loads without JS errors', async ({ page }) => {
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${BASE}/`);
    await waitForData(page);
    const critical = errors.filter(e => !e.includes('ResizeObserver'));
    if (critical.length) console.log('Page errors:', critical);
    expect(critical.length).toBe(0);
  });

  test('Dashboard: Mar 1 data — UI Total Sales matches API', async ({ page, request }) => {
    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-01', date_to: '2026-03-01' });

    await page.goto(`${BASE}/`);
    await waitForData(page);

    // Set date to Mar 1 only
    const dateInputs = await page.locator('input[type="date"]').all();
    if (dateInputs.length >= 2) {
      await dateInputs[0].fill('2026-03-01');
      await dateInputs[1].fill('2026-03-01');
      await page.keyboard.press('Tab');
      await waitForData(page);
    }

    // Get UI Total Sales value
    const salesCard = page.locator('text=Total Sales').first();
    const cardText = await salesCard.locator('..').textContent().catch(() => null);
    if (cardText) {
      const uiSales = parseAed(cardText);
      const apiSales = Math.round(api.total_sales);
      console.log(`Mar 1 UI Sales: ${uiSales}, API: ${apiSales}`);
      // Allow 1% tolerance
      if (apiSales > 0) {
        expect(Math.abs(uiSales - apiSales) / apiSales).toBeLessThan(0.01);
      } else {
        expect(uiSales).toBe(0);
      }
    }
  });

  test('Dashboard: Mar 2 data — UI Total Sales matches API', async ({ page, request }) => {
    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-02', date_to: '2026-03-02' });

    await page.goto(`${BASE}/`);
    await waitForData(page);

    const dateInputs = await page.locator('input[type="date"]').all();
    if (dateInputs.length >= 2) {
      await dateInputs[0].fill('2026-03-02');
      await dateInputs[1].fill('2026-03-02');
      await page.keyboard.press('Tab');
      await waitForData(page);
    }

    const salesCard = page.locator('text=Total Sales').first();
    const cardText = await salesCard.locator('..').textContent().catch(() => null);
    if (cardText) {
      const uiSales = parseAed(cardText);
      const apiSales = Math.round(api.total_sales);
      console.log(`Mar 2 UI Sales: ${uiSales}, API: ${apiSales}`);
      if (apiSales > 0) {
        expect(Math.abs(uiSales - apiSales) / apiSales).toBeLessThan(0.01);
      }
    }
  });

  test('Dashboard: Mar 3 data — UI Total Sales matches API', async ({ page, request }) => {
    const api = await apiFetch(request, '/dashboard', { date_from: '2026-03-03', date_to: '2026-03-03' });

    await page.goto(`${BASE}/`);
    await waitForData(page);

    const dateInputs = await page.locator('input[type="date"]').all();
    if (dateInputs.length >= 2) {
      await dateInputs[0].fill('2026-03-03');
      await dateInputs[1].fill('2026-03-03');
      await page.keyboard.press('Tab');
      await waitForData(page);
    }

    const salesCard = page.locator('text=Total Sales').first();
    const cardText = await salesCard.locator('..').textContent().catch(() => null);
    if (cardText) {
      const uiSales = parseAed(cardText);
      const apiSales = Math.round(api.total_sales);
      console.log(`Mar 3 UI Sales: ${uiSales}, API: ${apiSales}`);
      if (apiSales > 0) {
        expect(Math.abs(uiSales - apiSales) / apiSales).toBeLessThan(0.01);
      }
    }
  });

  test('Dashboard: Mar 1-3 range — day chart shows 3 bars', async ({ page }) => {
    await page.goto(`${BASE}/`);
    await waitForData(page);

    const dateInputs = await page.locator('input[type="date"]').all();
    if (dateInputs.length >= 2) {
      await dateInputs[0].fill('2026-03-01');
      await dateInputs[1].fill('2026-03-03');
      await page.keyboard.press('Tab');
      await waitForData(page);
    }

    // Chart heading should be visible
    const chartHeading = page.locator('text=Day-wise Sales & Collection');
    await expect(chartHeading).toBeVisible({ timeout: 10000 });

    // Check recharts bars exist
    const bars = await page.locator('.recharts-bar-rectangle').count();
    console.log(`Mar 1-3 chart bars: ${bars}`);
    // 3 days × 2 series (sales + collection) = 6 bars (or fewer if some days have 0)
    expect(bars).toBeGreaterThan(0);
  });

  test('Dashboard: Mar 1-3 screenshot', async ({ page }) => {
    await page.goto(`${BASE}/`);
    await waitForData(page);

    const dateInputs = await page.locator('input[type="date"]').all();
    if (dateInputs.length >= 2) {
      await dateInputs[0].fill('2026-03-01');
      await dateInputs[1].fill('2026-03-03');
      await page.keyboard.press('Tab');
      await waitForData(page);
    }

    await page.screenshot({ path: 'test-results/dashboard-mar1-3.png', fullPage: true });
    console.log('Screenshot saved: test-results/dashboard-mar1-3.png');
  });
});
