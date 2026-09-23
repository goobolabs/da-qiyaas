import { test, expect } from '@playwright/test';

test('feedback summary handles empty data, refresh, and server failures', async ({ page }) => {
  let state = 'empty';
  await page.route('**/api/feedback/summary', route => route.fulfill(state === 'error'
    ? { status: 503, json: { error: { message: 'Unavailable' } } }
    : { json: state === 'empty'
      ? { count: 0, mean_absolute_error_years: null, self_reported: true, by_source: { camera: { count: 0, mean_absolute_error_years: null }, upload: { count: 0, mean_absolute_error_years: null } } }
      : { count: 3, mean_absolute_error_years: 4, self_reported: true, by_source: { camera: { count: 1, mean_absolute_error_years: 10 }, upload: { count: 2, mean_absolute_error_years: 1 } } } }));
  await page.goto('/accuracy#feedback');
  const section = page.getByRole('region', { name: 'What users shared' });
  await expect(section).toContainText('No feedback yet');
  await expect(section.getByRole('row', { name: 'Camera No data 0' })).toBeVisible();
  state = 'populated';
  await section.getByRole('button', { name: 'Refresh feedback' }).click();
  await expect(section.getByRole('row', { name: 'Camera 10.00 years 1' })).toBeVisible();
  await expect(section.getByRole('row', { name: 'Upload 1.00 years 2' })).toBeVisible();
  await expect(section.locator('.feedback-metrics')).toContainText('4.00');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  state = 'error';
  await section.getByRole('button', { name: 'Refresh feedback' }).click();
  await expect(section.getByRole('status')).toContainText('unavailable');
  await expect(section.getByRole('table')).toHaveCount(0);
  state = 'populated';
  await section.getByRole('button', { name: 'Refresh feedback' }).click();
  await expect(section.getByRole('table')).toBeVisible();
});
