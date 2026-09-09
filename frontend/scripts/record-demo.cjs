// Run from frontend/: node scripts/record-demo.cjs
// Both local services must be running. No API responses are mocked.
const { chromium, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const frames = path.join(root, '.run/demo-frames');
  const assets = path.join(root, 'docs/assets');
  fs.mkdirSync(frames, { recursive: true });
  fs.mkdirSync(assets, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  let recording = false, captureTask;
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 1100 }, colorScheme: 'light' });
    const page = await context.newPage();
    const health = await context.request.get('http://127.0.0.1:3000/api/health');
    if (!health.ok()) throw new Error('Start Flask with a trained model before recording.');
    const rows = JSON.parse(fs.readFileSync(path.join(root, 'data/processed/test.json'), 'utf8'));
    let selected;
    // Choose by input validity, never by agreement with the age label.
    for (const row of rows.filter(row => row.age >= 20 && row.age <= 39).slice(0, 50)) {
      const response = await context.request.post('http://127.0.0.1:3000/api/scan', {
        multipart: { image: { name: 'portrait.jpg', mimeType: 'image/jpeg', buffer: fs.readFileSync(path.join(root, row.path)) } },
      });
      if (response.ok()) { selected = row; break; }
    }
    if (!selected) throw new Error('No demo portrait passed camera quality checks.');
    const input = path.join(root, selected.path);
    const encoded = fs.readFileSync(input).toString('base64');
    await page.addInitScript(encoded => {
      // A deterministic virtual camera shows a local dataset portrait.
      // Face detection, quality checks and inference still use the real backend.
      navigator.mediaDevices.getUserMedia = async () => {
        const photo = new Image(); photo.src = `data:image/jpeg;base64,${encoded}`;
        await photo.decode();
        const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 640;
        const draw = () => canvas.getContext('2d').drawImage(photo, 0, 0, 640, 640);
        draw();
        const media = canvas.captureStream(10);
        const refresh = setInterval(() => {
          if (media.getTracks().every(track => track.readyState === 'ended')) clearInterval(refresh);
          else draw();
        }, 100);
        window.demoStream = media;
        return media;
      };
    }, encoded);
    await page.goto('http://127.0.0.1:3000');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(assets, 'overview.png'), fullPage: true });
    const entries = [], events = [];
    const started = Date.now();
    const stage = name => events.push({ name, at_ms: Date.now() - started });
    recording = true;
    captureTask = (async () => {
      while (recording) {
        const file = `frame-${String(entries.length).padStart(4, '0')}.png`;
        const at_ms = Date.now() - started;
        await page.screenshot({ path: path.join(frames, file) });
        entries.push({ file, at_ms });
        await page.waitForTimeout(180);
      }
    })();
    stage('Light theme');
    await page.waitForTimeout(1200);
    await page.getByRole('button', { name: 'Upload image' }).click();
    stage('Upload a portrait — real API');
    await page.locator('input[type=file]').setInputFiles(input);
    await expect(page.getByRole('status')).toHaveText('Your estimate is ready.');
    const uploadedAge = await page.locator('.age-number').innerText();
    await page.waitForTimeout(1800);
    await page.getByRole('button', { name: 'Switch to dark mode' }).click();
    stage('Dark theme');
    await page.waitForTimeout(1200);
    await page.getByRole('button', { name: 'Live camera' }).click();
    await page.getByRole('button', { name: 'Open Camera' }).click();
    stage('Virtual camera — real scan and model');
    await expect(page.getByLabel('Detected face scan')).toBeVisible({ timeout: 12000 });
    await expect(page.getByRole('status')).toHaveText('Your estimate is ready.', { timeout: 30000 });
    const cameraAge = await page.locator('.age-number').innerText();
    expect(await page.evaluate(() => window.demoStream.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
    stage('Scan complete — camera stopped');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(assets, 'dark-result.png'), fullPage: true });
    recording = false;
    await captureTask;
    const report = { source: 'One adult UTKFace test portrait', virtual_camera: true, mocked_api: false, uploaded_age: uploadedAge, camera_age: cameraAge, duration_ms: Date.now() - started, events, frames: entries };
    fs.writeFileSync(path.join(frames, 'manifest.json'), JSON.stringify(report, null, 2));
    fs.writeFileSync(path.join(assets, 'demo-recording.json'), JSON.stringify({ ...report, frames: entries.length }, null, 2));
    console.log(JSON.stringify({ passed: true, frames: entries.length, duration_ms: report.duration_ms, uploadedAge, cameraAge }));
  } finally {
    recording = false;
    if (captureTask) await captureTask.catch(() => {});
    await browser.close();
  }
})();
