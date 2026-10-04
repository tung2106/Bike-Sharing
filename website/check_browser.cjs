// Optional UI check: npm install playwright, then node check_browser.cjs.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => !document.getElementById('predict-button').disabled);
    assert.equal(await page.locator('#model-status').innerText(), 'Mô hình đã sẵn sàng');
    await page.getByRole('button', { name: 'Tính dự đoán' }).click();
    await page.waitForFunction(() => document.getElementById('result-state').textContent === 'Đã dự đoán');
    assert.notEqual(await page.locator('#prediction-value').innerText(), '—');
    const checks = path.join(__dirname, '.checks');
    fs.mkdirSync(checks, { recursive: true });
    await page.screenshot({ path: path.join(checks, 'desktop.png'), fullPage: true });
    await page.locator('#hour').selectOption('17');
    assert.equal(await page.locator('#result-state').innerText(), 'Cần tính lại');
    await page.locator('#feels_like').fill('');
    await page.getByRole('button', { name: 'Tính dự đoán' }).click();
    await page.waitForFunction(() => document.getElementById('result-state').textContent === 'Đã dự đoán');
    assert.match(await page.locator('#imputation-note').innerText(), /nhiệt độ cảm nhận/);
    await page.locator('#humidity').fill('101');
    assert.equal(await page.locator('#humidity').evaluate(el => el.checkValidity()), false);
    await page.locator('#humidity').fill('65');
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Mobile overflow');
    await page.screenshot({ path: path.join(checks, 'mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.evaluate(() => { document.documentElement.style.fontSize = '32px'; });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Text zoom overflow');
    assert.deepEqual(errors, []);
    console.log('PASS: real prediction, stale result, missing data, validation, mobile layout, 200% text, JS console');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
