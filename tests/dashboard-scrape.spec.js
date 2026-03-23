// @ts-check
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const LOGIN_URL = 'https://nfpcsfalive.winitsoftware.com/nfpcsfa-92/Pages/Login.aspx';
const TARGET_URL = 'https://nfpcsfalive.winitsoftware.com/nfpcsfa-92/pages/ClientDashBoard.aspx';
const USERNAME = 'admin';
const PASSWORD = 'SFA@@25@@';

const screenshotDir = path.join(__dirname, '..', 'test-results', 'dashboard-scrape');
if (!fs.existsSync(screenshotDir)) {
  fs.mkdirSync(screenshotDir, { recursive: true });
}

test.use({
  headless: true,
  viewport: { width: 1400, height: 900 },
  navigationTimeout: 120000,
  actionTimeout: 30000,
});

test('Scrape ClientDashBoard - login and collect KPIs', async ({ page }) => {
  test.setTimeout(300000); // 5 minutes total

  // Step 1: Navigate to login page
  console.log('Navigating to login page:', LOGIN_URL);
  await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('load', { timeout: 30000 });
  console.log('Login page title:', await page.title());

  // Step 2: Screenshot the login page
  await page.screenshot({ path: path.join(screenshotDir, '01-login-page.png'), fullPage: true });
  console.log('Screenshot saved: 01-login-page.png');

  // Fill username - we know the ID is txtUsername
  await page.fill('#txtUsername', USERNAME);
  console.log('Filled username:', USERNAME);

  // Fill password
  await page.fill('#txtPassword', PASSWORD);
  console.log('Filled password');

  // Screenshot before submit
  await page.screenshot({ path: path.join(screenshotDir, '02-login-filled.png'), fullPage: true });

  // Click the login button (btnNavigate is the login button based on discovered inputs)
  // Wait for navigation after click
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 60000 }),
    page.click('#btnNavigate'),
  ]);

  console.log('After login click - URL:', page.url());
  await page.waitForLoadState('load', { timeout: 30000 });
  console.log('After load - URL:', page.url());
  console.log('After load - Title:', await page.title());

  // Step 3: Screenshot after login
  await page.screenshot({ path: path.join(screenshotDir, '03-after-login.png'), fullPage: true });
  console.log('Screenshot saved: 03-after-login.png');

  // Navigate to dashboard
  console.log('Navigating to dashboard:', TARGET_URL);
  await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });

  // Wait a bit for JS to render
  await page.waitForTimeout(5000);

  console.log('Dashboard URL:', page.url());
  console.log('Dashboard Title:', await page.title());

  // Screenshot dashboard
  await page.screenshot({ path: path.join(screenshotDir, '03b-dashboard-initial.png'), fullPage: true });
  console.log('Screenshot saved: 03b-dashboard-initial.png');

  // Wait longer for dynamic content
  await page.waitForTimeout(5000);
  await page.screenshot({ path: path.join(screenshotDir, '03c-dashboard-loaded.png'), fullPage: true });

  // Print full body text
  const bodyText = await page.locator('body').innerText().catch(() => '');
  console.log('\n=== DASHBOARD BODY TEXT (first 10000 chars) ===');
  console.log(bodyText.substring(0, 10000));
  console.log('=== END ===\n');

  // Print page HTML structure (first 5000 chars)
  const bodyHTML = await page.locator('body').innerHTML().catch(() => '');
  console.log('\n=== DASHBOARD HTML (first 5000 chars) ===');
  console.log(bodyHTML.substring(0, 5000));
  console.log('=== END HTML ===\n');

  // Find all tables
  console.log('\n=== TABLE DATA ===');
  const tables = page.locator('table');
  const tableCount = await tables.count();
  console.log(`Tables: ${tableCount}`);
  for (let t = 0; t < Math.min(tableCount, 20); t++) {
    const txt = await tables.nth(t).innerText().catch(() => '');
    const id = await tables.nth(t).getAttribute('id').catch(() => '');
    if (txt.trim()) {
      console.log(`\nTable[${t}] id="${id}":\n${txt.substring(0, 2000)}`);
    }
  }

  // All dropdowns/selects
  console.log('\n=== DROPDOWNS ===');
  const selects = page.locator('select');
  const selectCount = await selects.count();
  console.log(`Selects: ${selectCount}`);
  for (let i = 0; i < selectCount; i++) {
    const id = await selects.nth(i).getAttribute('id');
    const options = await selects.nth(i).locator('option').allInnerTexts();
    const selected = await selects.nth(i).inputValue().catch(() => '');
    console.log(`  Select[${i}] id="${id}" selected="${selected}": ${JSON.stringify(options.slice(0, 30))}`);
  }

  // All visible inputs
  console.log('\n=== ALL VISIBLE INPUTS ===');
  const allInputs = page.locator('input:not([type="hidden"])');
  const inputCount = await allInputs.count();
  for (let i = 0; i < inputCount; i++) {
    const type = await allInputs.nth(i).getAttribute('type');
    const id = await allInputs.nth(i).getAttribute('id');
    const value = await allInputs.nth(i).inputValue().catch(() => '');
    console.log(`  Input[${i}] type="${type}" id="${id}" value="${value}"`);
  }

  // All links/buttons
  console.log('\n=== LINKS AND BUTTONS ===');
  const allLinks = page.locator('a, button');
  const linkCount = await allLinks.count();
  console.log(`Total: ${linkCount}`);
  for (let i = 0; i < Math.min(linkCount, 100); i++) {
    const text = await allLinks.nth(i).innerText().catch(() => '');
    const href = await allLinks.nth(i).getAttribute('href').catch(() => '');
    const id = await allLinks.nth(i).getAttribute('id').catch(() => '');
    if (text.trim()) {
      console.log(`  [${i}] id="${id}" href="${href}": "${text.trim().substring(0, 100)}"`);
    }
  }

  // Check for iframes
  const iframes = page.locator('iframe');
  const iframeCount = await iframes.count();
  console.log(`\nIframes: ${iframeCount}`);
  for (let i = 0; i < iframeCount; i++) {
    const src = await iframes.nth(i).getAttribute('src').catch(() => '');
    const id = await iframes.nth(i).getAttribute('id').catch(() => '');
    console.log(`  iframe[${i}] id="${id}" src="${src}"`);
  }

  // Check for date-related elements
  console.log('\n=== DATE-RELATED ELEMENTS ===');
  const dateEls = page.locator('[id*="date" i], [id*="Date"], [name*="date" i], [class*="date" i], [class*="datepicker" i]');
  const dateElCount = await dateEls.count();
  console.log(`Date elements: ${dateElCount}`);
  for (let i = 0; i < Math.min(dateElCount, 20); i++) {
    const tag = await dateEls.nth(i).evaluate(el => el.tagName).catch(() => '');
    const id = await dateEls.nth(i).getAttribute('id').catch(() => '');
    const val = await dateEls.nth(i).inputValue().catch(() => '');
    const text = await dateEls.nth(i).innerText().catch(() => '');
    console.log(`  [${i}] <${tag}> id="${id}" value="${val}" text="${text.trim().substring(0, 50)}"`);
  }

  // Look for numeric data
  console.log('\n=== NUMERIC VALUES (span, div, td with numbers) ===');
  const numEls = page.locator('span, div, td, label').filter({ hasText: /^\s*[\d,]+\.?\d*\s*$/ });
  const numElCount = await numEls.count();
  console.log(`Numeric elements: ${numElCount}`);
  for (let i = 0; i < Math.min(numElCount, 50); i++) {
    const text = await numEls.nth(i).innerText().catch(() => '');
    const id = await numEls.nth(i).getAttribute('id').catch(() => '');
    const cls = await numEls.nth(i).getAttribute('class').catch(() => '');
    if (text.trim()) console.log(`  [${i}] id="${id}" class="${cls}": "${text.trim()}"`);
  }

  // === Try Mar 1, 2, 3 ===
  // First, look for any date filter/search inputs that are visible
  const fromDateInput = page.locator('input[id*="from" i], input[id*="FromDate" i], input[id*="startDate" i], input[id*="txtFrom" i]').first();
  const toDateInput = page.locator('input[id*="to" i], input[id*="ToDate" i], input[id*="endDate" i], input[id*="txtTo" i]').first();
  const hasFromDate = await fromDateInput.count() > 0;
  const hasToDate = await toDateInput.count() > 0;
  console.log(`\nHas from-date input: ${hasFromDate}, has to-date input: ${hasToDate}`);

  for (const { date, label, displayDate } of [
    { date: '01/03/2026', label: 'Mar1', displayDate: 'March 1, 2026' },
    { date: '02/03/2026', label: 'Mar2', displayDate: 'March 2, 2026' },
    { date: '03/03/2026', label: 'Mar3', displayDate: 'March 3, 2026' },
  ]) {
    console.log(`\n\n=== ATTEMPTING DATE: ${displayDate} ===`);

    if (hasFromDate) {
      try {
        await fromDateInput.fill(date);
        console.log('Set from-date to:', date);
      } catch (e) {
        console.log('Error setting from-date:', e.message);
      }
    }
    if (hasToDate) {
      try {
        await toDateInput.fill(date);
        console.log('Set to-date to:', date);
      } catch (e) {
        console.log('Error setting to-date:', e.message);
      }
    }

    // Try to submit/search
    const searchBtn = page.locator('input[type="submit"], button[type="submit"], button:has-text("Search"), button:has-text("Go"), button:has-text("Filter"), input[value*="search" i], input[value*="filter" i]').first();
    if (await searchBtn.count() > 0) {
      await searchBtn.click().catch(() => {});
      await page.waitForTimeout(3000);
    }

    await page.screenshot({ path: path.join(screenshotDir, `05-${label}.png`), fullPage: true });
    console.log(`Screenshot: 05-${label}.png`);

    const txt = await page.locator('body').innerText().catch(() => '');
    console.log(`Page text for ${label}:\n${txt.substring(0, 3000)}`);

    const tabs2 = page.locator('table');
    const tc2 = await tabs2.count();
    for (let t = 0; t < Math.min(tc2, 5); t++) {
      const tTxt = await tabs2.nth(t).innerText().catch(() => '');
      if (tTxt.trim()) console.log(`Table[${t}] for ${label}:\n${tTxt.substring(0, 2000)}`);
    }
  }

  // Final full screenshot
  await page.screenshot({ path: path.join(screenshotDir, '06-final.png'), fullPage: true });
  console.log('\nFinal screenshot: 06-final.png');
  console.log('\nScreenshot directory:', screenshotDir);
});
