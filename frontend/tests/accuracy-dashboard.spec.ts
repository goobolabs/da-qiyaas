import { test, expect } from '@playwright/test';

test('accuracy dashboard shows recorded metrics and switches evaluation splits', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'View accuracy dashboard' }).click();
  await expect(page.getByRole('heading', { name: 'Mean absolute error' })).toBeVisible();
  const recordedMetrics = page.locator('.accuracy-metrics').filter({
    has: page.getByRole('heading', { name: 'Mean absolute error', exact: true }),
  });
  await expect(recordedMetrics).toContainText('5.68');
  await expect(recordedMetrics).toContainText('3,465');
  await expect(page.getByRole('row', { name: '80-120 10.65 97' })).toBeVisible();
  await page.getByRole('button', { name: 'Validation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Validation', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(recordedMetrics).toContainText('3,464');
  await expect(page.getByRole('row', { name: '80-120 10.64 98' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ colorScheme: 'light' });
  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.screenshot({ path: 'test-results/accuracy-mobile.png', fullPage: true });
  await page.getByRole('link', { name: 'Try the model', exact: true }).click();
  await expect(page.getByRole('button', { name: /Open Camera/ })).toBeVisible();
});
