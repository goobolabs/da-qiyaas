import { test, expect } from '@playwright/test';

test('dark mode is persisted and can return to light mode', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.getByRole('button', { name: 'Switch to light mode' })).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(16, 18, 16)');
  await page.screenshot({ path: 'test-results/dark-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/dark-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Switch to light mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('camera indicators display measured guidance and clear when cancelled', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      canvas.getContext('2d')!.fillRect(0, 0, 640, 480);
      return canvas.captureStream(10);
    };
  });
  await page.route('**/api/scan', route => route.fulfill({ status: 422, json: {
    error: { code: 'LOW_LIGHT', message: 'Add light in front of your face.' },
    face_box: { x: .2, y: .2, width: .4, height: .5 },
    quality: { lighting: 'low', face_size: 'good', sharpness: 'blurry' },
  } }));
  await page.goto('/');
  const indicators = page.getByLabel('Camera capture quality');
  await expect(indicators).toContainText('Waiting');
  await page.getByRole('button', { name: 'Open Camera' }).click();
  await expect(indicators).toContainText('Add light');
  await expect(indicators).toContainText('Focus needed');
  await expect(indicators).toContainText('Hold still');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(indicators).not.toContainText('Add light');
  await expect(indicators).toContainText('Waiting');
});
