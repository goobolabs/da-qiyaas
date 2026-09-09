import { test, expect } from '@playwright/test';

const photo = { name: 'portrait.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64') };

test('upload shows a result and can be replaced', async ({ page }) => {
  let calls = 0;
  await page.route('**/api/predict', route => { calls++; return route.fulfill({ json: { estimated_age: 28.6 } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect(page.locator('.age-number')).toHaveText('29years');
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect.poll(() => calls).toBe(2);
  await page.screenshot({ path: 'test-results/upload-desktop.png', fullPage: true });
});

test('upload error and invalid file have clear messages', async ({ page }) => {
  await page.route('**/api/predict', route => route.fulfill({ status: 422, json: { error: { code: 'NO_FACE', message: 'No clear face found. Face forward and improve the lighting.' } } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect(page.getByRole('status')).toContainText('No clear face found');
  await expect(page.locator('.age-number')).toHaveText('—');
  await page.locator('input[type=file]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') });
  await expect(page.getByRole('status')).toContainText('Choose a JPG');
});

test('camera permission denial offers upload alternative', async ({ page }) => {
  await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }; });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Camera' }).click();
  await expect(page.getByRole('status')).toContainText('Camera access was denied');
});

test('camera auto-analyzes, stops after success, and restarts on retry', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      const context = canvas.getContext('2d')!; context.fillStyle = '#d8e4d7'; context.fillRect(0, 0, 640, 480);
      const stream = canvas.captureStream(10);
      (window as unknown as { testStream: MediaStream }).testStream = stream;
      return stream;
    };
  });
  let calls = 0;
  const face_box = { x: 0.3, y: 0.2, width: 0.3, height: 0.5 };
  await page.route('**/api/scan', route => route.fulfill({ json: { ready: true, face_box } }));
  await page.route('**/api/predict', route => { calls++; return route.fulfill({ json: { estimated_age: 35, face_box } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Camera' }).click();
  await expect(page.getByLabel('Detected face scan')).toBeVisible();
  await expect(page.locator('.age-number')).toHaveText('—');
  await expect(page.locator('.age-number')).toHaveText('35years', { timeout: 15000 });
  expect(await page.evaluate(() => (window as unknown as { testStream: MediaStream }).testStream.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
  await page.waitForTimeout(2000);
  expect(calls).toBe(5);
  await page.getByRole('button', { name: 'Try Again' }).click();
  await expect.poll(() => calls, { timeout: 15000 }).toBe(10);
  await expect(page.locator('.age-number')).toHaveText('35years');
});

test('switching modes discards an old response', async ({ page }) => {
  await page.route('**/api/predict', async route => { await new Promise(resolve => setTimeout(resolve, 600)); await route.fulfill({ json: { estimated_age: 44 } }).catch(() => {}); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await page.getByRole('button', { name: 'Live camera' }).click();
  await page.waitForTimeout(900);
  await expect(page.locator('.age-number')).toHaveText('—');
  await expect(page.getByRole('button', { name: 'Open Camera' })).toBeEnabled();
});

test('mobile layout stays within viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/home-mobile.png', fullPage: true });
});
