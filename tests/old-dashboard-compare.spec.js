// @ts-check
/**
 * Old ASP.NET Dashboard — login and capture sales data
 * Compare against local implementation for Mar 1, Mar 2, Mar 3
 */
const { test, expect } = require('@playwright/test');

// Run with visible browser
test.use({ headless: false });

const OLD_URL = 'https://nfpcsfalive.winitsoftware.com/nfpcsfa-92/pages/ClientDashBoard.aspx';
const LOCAL_API = 'http://localhost:8000/api';

async function apiFetch(request, path, params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  }
  const res = await request.get(`${LOCAL_API}${path}?${qs}`, { timeout: 30000 });
  return res.json();
}

test.describe('Old Dashboard — Live Page Inspection', () => {
  test.setTimeout(120000);

  async function loginAndGoToDashboard(page) {
    const loginUrl = 'https://nfpcsfalive.winitsoftware.com/nfpcsfa-92/pages/Login.aspx';
    await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.screenshot({ path: 'test-results/old-dash-01-login.png', fullPage: true });
    console.log('Login page:', page.url());

    // Fill credentials
    await page.locator('input[type="text"]').first().fill('admin');
    await page.locator('input[type="password"]').fill('SFA@@25@@');

    // Select role if dropdown exists (Admin / Customer / Market Planner)
    const roleSelect = page.locator('select').first();
    if (await roleSelect.isVisible().catch(() => false)) {
      await roleSelect.selectOption({ label: 'Admin' }).catch(() =>
        roleSelect.selectOption({ index: 0 })
      );
      console.log('Role selected');
    }
    await page.screenshot({ path: 'test-results/old-dash-02-filled.png' });

    // Submit
    const submitBtn = page.locator('input[type="submit"], button[type="submit"]').first();
    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
    } else {
      await page.locator('input[type="password"]').press('Enter');
    }
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    console.log('After login:', page.url());

    // Navigate to dashboard — use domcontentloaded, heavy page
    await page.goto(OLD_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForTimeout(5000); // let AJAX / SP calls finish
    await page.screenshot({ path: 'test-results/old-dash-03-dashboard.png', fullPage: true });
    console.log('Dashboard URL:', page.url());
  }

  test('Login and capture ClientDashBoard data', async ({ page }) => {
    await loginAndGoToDashboard(page);

    await page.screenshot({ path: 'test-results/old-dash-04-dashboard.png', fullPage: true });
    console.log('4. Dashboard URL:', page.url());

    // ── 4. Capture page text / KPIs
    const bodyText = await page.textContent('body');
    console.log('\n=== PAGE TEXT SAMPLE (first 3000 chars) ===');
    console.log(bodyText?.slice(0, 3000));

    // ── 5. Look for sales numbers
    const numbers = bodyText?.match(/[\d,]+\.\d{2}/g) || [];
    console.log('\n=== NUMERIC VALUES FOUND ===', numbers.slice(0, 20));

    // ── 6. Look for date filter / dropdowns
    const selects = await page.locator('select').all();
    console.log(`\nDropdowns found: ${selects.length}`);
    for (let i = 0; i < Math.min(selects.length, 5); i++) {
      const opts = await selects[i].locator('option').allTextContents();
      console.log(`  Select ${i}: ${opts.slice(0, 5).join(', ')}`);
    }

    // ── 7. Look for date inputs
    const dateInputs = await page.locator('input[type="text"][id*="Date"], input[type="date"]').all();
    console.log(`Date inputs found: ${dateInputs.length}`);

    // ── 8. Try to set Mar 1 date if filter exists
    if (dateInputs.length > 0) {
      try {
        await dateInputs[0].fill('03/01/2026');
        if (dateInputs.length > 1) await dateInputs[1].fill('03/01/2026');
        // Click apply/search/filter button
        const applyBtn = page.locator('input[type="button"][value*="Search"], input[type="submit"][value*="Search"], button:has-text("Search"), button:has-text("Go"), input[value*="Go"]').first();
        if (await applyBtn.isVisible()) await applyBtn.click();
        await page.waitForLoadState('networkidle', { timeout: 20000 });
        await page.screenshot({ path: 'test-results/old-dash-05-mar1.png', fullPage: true });
        console.log('5. Mar 1 screenshot saved');
      } catch (e) {
        console.log('Date filter error:', e.message);
      }
    }

    // ── 9. Compare with local API Mar 1
    const localMar1 = await apiFetch(page.request, '/sales-performance', { day: 1, month: 3, year: 2026 });
    console.log(`\n=== LOCAL API Mar 1 ===`);
    console.log(`  MTD Sales:  AED ${localMar1.mtd_sales?.toFixed(0)}`);
    console.log(`  LMTD Sales: AED ${localMar1.lmtd_sales?.toFixed(0)}`);
    console.log(`  SKUs today: ${localMar1.sku_counts?.today}`);
    console.log(`  SKUs MTD:   ${localMar1.sku_counts?.mtd}`);
    console.log(`  ROS%:       ${localMar1.return_on_sales?.ros_pct}%`);
    console.log(`  SKU rows:   ${localMar1.sku_table?.length}`);

    await page.screenshot({ path: 'test-results/old-dash-06-final.png', fullPage: true });
    expect(page.url()).toBeTruthy();
  });

  test('Capture all visible KPI text from dashboard', async ({ page }) => {
    await loginAndGoToDashboard(page);

    // Find table cells with numbers — these are KPI values
    const cells = await page.locator('td, th, span, label, div').all();
    const kpis = [];
    for (const cell of cells.slice(0, 200)) {
      const txt = await cell.textContent().catch(() => '');
      if (txt && /[\d,]+/.test(txt) && txt.trim().length < 50) {
        kpis.push(txt.trim());
      }
    }
    console.log('\n=== KPI CELLS (first 40) ===');
    console.log(kpis.slice(0, 40).join('\n'));

    await page.screenshot({ path: 'test-results/old-dash-kpis.png', fullPage: true });
  });
});
