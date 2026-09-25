import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('real Next.js proxy, Flask detector and trained model return an age', async ({ page, request }) => {
  test.skip(process.env.RUN_INTEGRATION !== '1', 'Start Flask and set RUN_INTEGRATION=1 for the real model test.');
  const health = await request.get('/api/health');
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).model_ready).toBe(true);
  const root = resolve(process.cwd(), '..');
  const rows = JSON.parse(readFileSync(resolve(root, 'data/processed/validation.json'), 'utf-8')) as { path: string }[];
  let portrait: string | undefined;
  for (const row of rows.slice(0, 30)) {
    const path = resolve(root, row.path);
    const response = await request.post('/api/predict', { multipart: { image: { name: 'portrait.jpg', mimeType: 'image/jpeg', buffer: readFileSync(path) } } });
    if (response.ok()) { portrait = path; break; }
  }
  expect(portrait).toBeTruthy();
  await page.goto('/');
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(portrait!);
  await expect(page.locator('.status[role="status"]')).toHaveText('Your estimate is ready.');
  await expect(page.locator('.age-number')).toHaveText(/\d+years/);
});
