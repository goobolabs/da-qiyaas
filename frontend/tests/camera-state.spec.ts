import { test, expect } from '@playwright/test';
import { isStable, median } from '../app/camera-scan';

test('movement or distance change invalidates stability, median resists one outlier', () => {
  const box = { x: .2, y: .2, width: .3, height: .4 };
  expect(isStable(null, box)).toBe(false);
  expect(isStable(box, { ...box, x: .205 })).toBe(true);
  expect(isStable(box, { ...box, x: .4 })).toBe(false);
  expect(isStable(box, { ...box, width: .5 })).toBe(false);
  expect(median([31, 30, 14, 32, 33])).toBe(31);
});

test('poor camera frames never trigger age prediction; cancel stops scans', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      canvas.getContext('2d')!.fillRect(0, 0, 640, 480);
      return canvas.captureStream(10);
    };
  });
  let scans = 0, predictions = 0;
  await page.route('**/api/scan', route => {
    scans++;
    return route.fulfill({ status: 422, json: { error: { code: 'BLURRY_FACE', message: 'Hold still and let the camera focus on your face.' }, face_box: { x: .2, y: .2, width: .4, height: .5 } } });
  });
  await page.route('**/api/predict', route => { predictions++; return route.fulfill({ json: { estimated_age: 14 } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Camera' }).click();
  await expect(page.getByRole('status')).toContainText('let the camera focus');
  await expect.poll(() => scans).toBeGreaterThanOrEqual(2);
  expect(predictions).toBe(0);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  const count = scans;
  await page.waitForTimeout(1000);
  expect(scans).toBe(count);
  await expect(page.locator('.age-number')).toHaveText('—');
});
