# Verification — version 1

Date: 2026-09-09.

## Completed checks

- Production build: npm.cmd run build passed on Next.js 15.5.24 after PostCSS 8.5.28 override.
- Backend: 9 pytest tests passed, including a real trained checkpoint and face detection test.
- Browser: 7 Playwright tests passed in 19.9 seconds on headless Microsoft Edge.
- Browser coverage: upload/result/replacement; invalid upload and no-face feedback; camera permission denial; automatic camera analysis and track release; Try Again; stale response rejection; mobile overflow check; real Next.js proxy + Flask + trained model upload.
- Model readiness: http://127.0.0.1:3000/api/health returned model_ready=true and status=ready.
- Dependency installation after PostCSS override reported 0 vulnerabilities. Standalone online npm audit attempts previously failed with connection resets; offline audit is not used as evidence of a clean online scan.
- Original UTKFace files were read, not modified. All 23,708 decoded successfully.

## Dataset audit

- 390 extra exact-pixel duplicate copies.
- 205 exact-pixel groups had contradictory age labels and were excluded in full.
- 23,113 usable unique portraits; 16,176 train / 3,467 validation / 3,470 test.
- Detailed records: data/processed/audit.json and split JSON manifests.
- Exact duplicates cannot cross splits. Near duplicates and identity overlap may remain.

## Model evidence

- Artifact: models/age_model.pt, 4,135,051 bytes.
- Architecture: frozen MobileNetV3 Small features plus a trained regression head.
- Best validation MAE: 7.779 years; test MAE: 7.696 years on 3,470 images.
- Training-median test baseline: 14.914 years.
- CPU model-only latency: 13.247 ms averaged over 20 warmed runs.
- Training, feature extraction and evaluation: 159.542 seconds in the measured run.
- Exact metrics and per-age-band errors: models/evaluation.json.
- Pretrained weight SHA256: 047DCFF4ADDEF86EA5BC2EFF13C9614DC11F47AB1160D0A71A25E7DB994F4E1F.

## Practical limits

- Camera browser tests use synthetic streams; no physical webcam was accessed.
- Real upload integration proves pipeline operation, not external-world accuracy.
- MAE is substantially larger for older age bands; this is a baseline estimator.
- Haar detection and the difference between UTKFace crops and camera crops can affect results.
- No changes were selected based on repeated test-set model tuning.

## Running services at handoff

- Frontend production server: http://127.0.0.1:3000.
- Backend: http://127.0.0.1:5000.
- Both bind to loopback. See README.md for restarting in terminal sessions.

## Camera scan correction — verified

- Replaced first-frame prediction with a face-aligned scan, capture-quality checks, three-frame stability gate and five-estimate median.
- Face loss, motion, quality errors or inconsistent estimates reset the scan rather than displaying an early age.
- Upload integration remains passing with the same model and crop pipeline.
- Production build passed; 14 backend tests passed; 9 browser tests passed in 23.9 seconds, including real upload integration.
- Browser checks confirmed an age is not shown during scan, poor frames do not start age prediction, cancellation stops scans, and five estimates are collected before success and again after Try Again.
- Services restarted and proxied health returned ready.
- No physical-webcam accuracy validation was performed. The reported age-14 mismatch cannot be attributed conclusively without the relevant camera frame; capture conditions and existing model error remain possible causes.

## Goobo Labs brand update

- Visited https://www.goobolabs.so/en and inspected its rendered layout, computed CSS, official SVG logo and font assets.
- Applied #3ACC69 mint, #0C0C0C ink, #FAFAFA background, Space Grotesk headings, Manrope body text, pill controls, rounded white cards and a subtle dot pattern.
- Official logo and both font files are served locally; browser inspection confirmed they loaded.
- Production build passed. All 9 browser tests passed in 27.8 seconds, including camera scanning, cancel/retry, mobile overflow and real Flask/model upload integration.
- Desktop (1440px) and mobile (390px) screenshots were visually inspected.
- Production frontend restarted on http://127.0.0.1:3000.
- Brand evidence and asset source URLs: specs/brand/.

## Usability improvement checks

- Added Lighting, Face size, Sharpness and Position indicators. Flask returns all three measured quality states on accepted frames and quality errors; position reflects client-side box stability.
- Added persistent light/dark theme selection, defaulting to saved or system preference.
- Frontend production build passed. 11 browser tests passed in 30.8 seconds, including theme persistence, mobile overflow, indicator reset, camera scanning and real upload integration.
- 15 backend tests passed before candidate model promotion; the final model reload check is recorded separately below.
- Dark desktop and mobile screenshots were visually inspected.

## Fine-tuned model result

- Baseline copied to models/baseline/ before training. Candidate saved to models/candidate.pt.
- Three epochs of partial fine-tuning; validation MAE 7.779 -> 7.356 -> 7.062 -> 6.957 years.
- Promotion decision used validation MAE only, under a predeclared 0.1-year minimum improvement rule.
- Selected candidate test MAE: 6.723 years versus baseline 7.696 on the existing 3,470-image test split, a 12.6% reduction.
- Age-band test errors are not uniformly improved: 40–59 increased from 9.498 to 9.851 years. Older age bands remain less accurate.
- Fine-tuning plus evaluation elapsed 647.173 seconds. Full comparison: models/finetune-report.json.
- New checkpoint passed the real face pipeline, camera scan metadata and deterministic reload checks (2 model tests).
- No labeled physical-webcam data was provided; this result does not establish webcam accuracy or fix a specific user's age estimate.

## README and recorded demo

- Rewrote README with setup, architecture diagram, camera/upload behavior, capture thresholds, training, dataset audit, model/subgroup metrics, API, tests, configuration and troubleshooting.
- Added docs/assets/demo.gif, a 12.78-second looping recording at 960 x 825, approximately 2.27 MiB. It contains real upload and model inference plus a deterministic virtual-camera portrait; no API responses are mocked.
- Recording assertions passed, including completed scan and released camera tracks. Both demonstrated estimates were 28 years; the fixture was chosen for capture validity, not age-label agreement.
- Preserved portable model and dataset summaries under docs/, since models/ and data/ are excluded from Git.
- Re-ran backend suite: 15 passed. Re-ran full browser suite with real integration enabled: 11 passed in 25.0 seconds.
- README check: 16 local references resolved; no broken links; model snapshot matched the active report; all 25 GIF frames decoded and looping/timing metadata were checked.
- Visually inspected the overview and an encoded animation frame.
- Reproduction scripts: frontend/scripts/record-demo.cjs, scripts/encode_demo.py and scripts/check_readme.py.

## Project name

The user selected Da'qiyaas as the project name. The interface and document display spelling uses a typographic apostrophe; the package slug is da-qiyaas-frontend. Updated the app header, page title, README and brand notes. Theme writes now use da-qiyaas-theme, while reading the previous preference remains supported.

Production build passed. Theme persistence/mobile layout and camera-indicator tests passed. The README demo was recorded again with the real API/model so screenshots and GIF show the new name.

## Git preparation

Initialized a local main branch and reviewed files eligible for version control. Dataset contents, trained/pretrained weights, Python/Node dependencies, build caches, test output, .env files, runtime recordings, and one-time brand inspection helpers are ignored. README demo assets, brand assets, lockfile, environment template, source, tests and portable metric reports remain included. Empty placeholders retain the dataset and model destination folders. No source or dataset files were deleted.

## Somali result speech — 2026-09-10

- Added the fixed Somali estimate sentence, opt-in sound preference, replay and cancellation for completed results.
- Added optional Azure speech with server-only credentials, integer validation, bounded requests and an in-memory clip cache.
- Backend: 24 tests passed. Browser: 13 passed with the integration test skipped in the first run; all four voice tests and real-model integration passed in the targeted final run (15 distinct passing browser tests across runs).
- Production build and TypeScript checks passed. README links and GIF validation passed.
- Local headless Edge exposed three en-GB voices and no Somali voice. The backend reports speech unavailable because Azure credentials are not configured. Actual Azure synthesis and Somali pronunciation have not been tested.
- On Windows the first Playwright run needed its finished test server stopped manually to complete teardown; assertions passed.
