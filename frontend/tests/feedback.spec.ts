import { test, expect } from '@playwright/test';

test('optional feedback compares ages, retries, and resets with a new result', async ({ page }) => {
  let attempts = 0;
  const bodies: Record<string, unknown>[] = [];
  await page.route('**/api/predict', route => route.fulfill({ json: { estimated_age: 32, unit: 'years', is_estimate: true } }));
  await page.route('**/api/feedback', route => {
    bodies.push(route.request().postDataJSON());
    attempts++;
    return route.fulfill(attempts === 1
      ? { status: 503, json: { error: { message: 'Feedback could not be saved. Please try again.' } } }
      : { json: { status: 'saved', absolute_error_years: 4 } });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'How close was the estimate?' })).toHaveCount(0);
  await page.getByRole('button', { name: /Upload image/i }).click();
  const upload = () => page.locator('input[type=file]').setInputFiles({ name: 'portrait.png', mimeType: 'image/png', buffer: Buffer.from('fixture') });
  await upload();
  await page.getByLabel('Actual age (years)').fill('28');
  await expect(page.locator('#feedback-comparison')).toContainText('4 years older');
  await expect(page.getByRole('button', { name: 'Share feedback' })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'I agree to save these two ages', exact: false }).check();
  await page.getByRole('button', { name: 'Share feedback' }).click();
  await expect(page.locator('.result-feedback form [role=status]')).toContainText('could not be saved');
  await expect(page.locator('.feedback-toast')).toHaveCount(0);
  await page.getByRole('button', { name: 'Share feedback' }).click();
  await expect(page.getByRole('button', { name: 'Feedback saved' })).toBeDisabled();
  await expect(page.locator('.feedback-toast')).toContainText('saved successfully');
  await page.getByRole('button', { name: 'Dismiss notification' }).click();
  await expect(page.locator('.feedback-toast')).toHaveCount(0);
  expect(bodies[0]).toEqual(bodies[1]);
  expect(bodies[1]).toMatchObject({ actual_age: 28, estimated_age: 32, source: 'upload', consent: true });
  await upload();
  await expect(page.getByLabel('Actual age (years)')).toHaveValue('');
  await expect(page.getByRole('checkbox', { name: 'I agree to save these two ages', exact: false })).not.toBeChecked();
});

test('training contribution attaches the photo only with separate opt-in', async ({ page }) => {
  let requestBody = '';
  let contentType = '';
  await page.route('**/api/predict', route => route.fulfill({ json: { estimated_age: 32 } }));
  await page.route('**/api/feedback', route => {
    requestBody = route.request().postData() || '';
    contentType = route.request().headers()['content-type'];
    return route.fulfill({ json: { status: 'saved', training_saved: true } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: /Upload image/i }).click();
  await page.locator('input[type=file]').setInputFiles({ name: 'portrait.png', mimeType: 'image/png', buffer: Buffer.from('fixture-photo') });
  await page.getByLabel('Actual age (years)').fill('28');
  const training = page.getByRole('checkbox', { name: /I also agree to save this photo/ });
  await expect(training).not.toBeChecked();
  await page.getByRole('checkbox', { name: /I agree to save these two ages/ }).check();
  await training.check();
  await page.getByRole('button', { name: 'Share feedback' }).click();
  await expect(page.locator('.feedback-toast')).toContainText('feedback and photo have been saved');
  await expect(page.locator('.feedback-toast')).toHaveCount(0, { timeout: 8000 });
  expect(contentType).toContain('multipart/form-data');
  expect(requestBody).toContain('"training_consent":true');
  expect(requestBody).toContain('fixture-photo');
  expect(requestBody).not.toContain('portrait.png');
});
