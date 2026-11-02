// Run against a running website. BIKE_TEST_URL can point to the previous-day demo.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.BIKE_TEST_URL || 'http://127.0.0.1:8001';

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {})
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1080 },
      deviceScaleFactor: 1
    });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('.rail-menu a[href="#du-doan"]').click();
    const info = await (await page.request.get(new URL('/api/model', base).href)).json();
    await page.waitForFunction(
      () => !document.getElementById('predict-button').disabled
    );
    assert.equal(
      await page.locator('#model-status').innerText(),
      info.uses_previous_day ? 'RF 85% · có lượt ngày trước' : 'Mô hình đã sẵn sàng'
    );
    await page.getByRole('button', { name: 'Tính dự đoán' }).click();
    await page.waitForFunction(
      () => document.getElementById('result-state').textContent === 'Đã dự đoán'
    );
    assert.notEqual(await page.locator('#prediction-value').innerText(), '—');
    assert.equal(await page.locator('#hourly-rows tr').count(), 24);
    await page.locator('.rail-menu a[href="#cao-diem"]').click();
    await page.locator('#peak-list:visible').waitFor();
    assert.equal(await page.locator('#peak-list li:visible').count(), 3);
    await page.locator('.rail-menu a[href="#du-doan"]').click();
    await page.locator('#hour').selectOption('17');
    assert.equal(
      await page.locator('#result-state').innerText(),
      'Cần tính lại'
    );
    await page.locator('#feels_like').fill('');
    await page.getByRole('button', { name: 'Tính dự đoán' }).click();
    await page.waitForFunction(
      () => document.getElementById('result-state').textContent === 'Đã dự đoán'
    );
    assert.match(
      await page.locator('#imputation-note').innerText(),
      /nhiệt độ cảm nhận/
    );
    await page.locator('#humidity').fill('101');
    await page.getByRole('button', { name: 'Tính dự đoán' }).click();
    assert.equal(
      await page.locator('#humidity').getAttribute('aria-invalid'),
      'true'
    );
    await page.locator('#humidity').fill('65');
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth
      ),
      true,
      'Mobile overflow'
    );
    await page.locator('.rail-menu a[href="#danh-gia"]').click();
    await page.locator('#eval-content:visible').waitFor();
    assert.equal(await page.locator('#eval-model').inputValue(), info.uses_previous_day ? 'rf85_previous_day' : 'rf85');
    await page.locator('input[name="eval-metric"][value="r2"]').check();
    assert.ok(await page.locator('#eval-time-pickers').isHidden());
    await page.locator('.rail-menu a[href="#doi-chieu"]').click();
    await page.locator('#rf-results:visible').waitFor();
    await page.locator('#rf-day').selectOption('2012-12-31');
    assert.equal(await page.locator('#rf-rows tr').count(), 24);
    await page.locator('.rail-menu a[href="#lich-su"]').click();
    await page.locator('#heat-grid button').first().click();
    await page.locator('#slot-results:visible').waitFor();
    assert.ok(await page.locator('#slot-rows tr').count() > 0);
    await page.locator('.rail-menu a[href="#du-doan"]').click();
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '32px';
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth
      ),
      true,
      'Text zoom overflow'
    );
    assert.deepEqual(errors, []);
    console.log(
      'PASS: forecast, peaks, stale result, missing/invalid input, evaluation, history, heatmap, mobile, text zoom and console'
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
