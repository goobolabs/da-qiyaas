import { test, expect } from '@playwright/test';

const photo = { name: 'portrait.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64') };

test.beforeEach(async ({ page }) => {
  await page.route('**/api/predict', route => route.fulfill({ json: { estimated_age: 23.8 } }));
});

test('Somali result plays once, replays, cancels and persists sound preference', async ({ page }) => {
  await page.addInitScript(() => {
    const state = { spoken: [] as string[], cancelled: 0 };
    (window as any).voiceTest = state;
    Object.defineProperty(window, 'SpeechSynthesisUtterance', { value: class {
      text: string;
      constructor(text: string) { this.text = text; }
    } });
    Object.defineProperty(window, 'speechSynthesis', { value: {
      getVoices: () => [{ lang: 'so-SO', name: 'Somali test voice' }],
      speak: (utterance: SpeechSynthesisUtterance) => { state.spoken.push(utterance.text); utterance.onend?.(new Event('end') as any); },
      cancel: () => { state.cancelled++; },
    } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Sound off', exact: true }).click();
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect.poll(() => page.evaluate(() => (window as any).voiceTest.spoken)).toEqual(['Da’daada waxaa lagu qiyaasay 24 sano.']);
  await page.getByRole('button', { name: 'Listen again' }).click();
  await expect.poll(() => page.evaluate(() => (window as any).voiceTest.spoken.length)).toBe(2);
  await page.getByRole('button', { name: 'Live camera' }).click();
  await expect(page.getByRole('button', { name: 'Listen again' })).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).voiceTest.cancelled)).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Sound on', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Sound on', exact: true }).click();
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect(page.locator('.age-number')).toHaveText('24years');
  expect(await page.evaluate(() => (window as any).voiceTest.spoken)).toEqual([]);
});

test('missing Somali voice preserves result and never uses an English voice', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'speechSynthesis', { value: {
      getVoices: () => [{ lang: 'en-US' }],
      speak: () => { throw new Error('Wrong voice'); }, cancel: () => {},
    } });
  });
  await page.route('**/api/speech', route => route.fulfill({ status: 503, json: { error: 'Not configured' } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Sound off', exact: true }).click();
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect(page.locator('.voice-notice')).toContainText('Somali audio is unavailable');
  await expect(page.locator('.age-number')).toHaveText('24years');
});

test('a late audio response is cancelled when switching modes', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [], cancel: () => {} } });
    (window as any).audioPlays = 0;
    HTMLMediaElement.prototype.play = async function () { (window as any).audioPlays++; };
  });
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  let requested = false;
  await page.route('**/api/speech', async route => {
    requested = true;
    await waiting;
    await route.fulfill({ contentType: 'audio/mpeg', body: 'fake' }).catch(() => {});
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Sound off', exact: true }).click();
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect.poll(() => requested).toBe(true);
  await page.getByRole('button', { name: 'Live camera' }).click();
  release();
  await expect(page.locator('.age-number')).toHaveText('—');
  expect(await page.evaluate(() => (window as any).audioPlays)).toBe(0);
});

 test('cloud audio can be retried after autoplay is blocked', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [], cancel: () => {} } });
    let attempts = 0;
    HTMLMediaElement.prototype.play = async function () {
      if (++attempts === 1) throw new DOMException('Blocked', 'NotAllowedError');
      this.dispatchEvent(new Event('ended'));
    };
  });
  let calls = 0;
  await page.route('**/api/speech', route => {
    calls++;
    expect(route.request().postDataJSON()).toEqual({ age: 24 });
    return route.fulfill({ contentType: 'audio/mpeg', body: 'fake' });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Sound off', exact: true }).click();
  await page.getByRole('button', { name: 'Upload image' }).click();
  await page.locator('input[type=file]').setInputFiles(photo);
  await expect(page.locator('.voice-notice')).toContainText('could not play');
  await page.getByRole('button', { name: 'Listen again' }).click();
  await expect.poll(() => calls).toBe(2);
  await expect(page.getByRole('button', { name: 'Listen again' })).toBeVisible();
  await expect(page.locator('.age-number')).toHaveText('24years');
});
