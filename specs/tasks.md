# Implementation tasks

Status: version 1 implemented and verified following user authorization on 2026-09-09.

- [x] Finalize camera-once, upload, retry and single-face behavior; English UI.
- [x] Select MobileNetV3 Small, OpenCV 4, and bounded multipart API input.
- [x] Decode/audit dataset, deduplicate exact pixels and exclude conflicting-age groups.
- [x] Produce reproducible train/validation/test manifests with seed 42.
- [x] Benchmark CPU, cache frozen features, train head, select using validation MAE.
- [x] Evaluate selected model on held-out test images and record age-band metrics.
- [x] Implement Flask validation, detection, inference, errors and readiness route.
- [x] Implement responsive Next.js camera, upload, result and retry flows.
- [x] Verify automatic camera analysis, stop after success and retry using a synthetic browser stream.
- [x] Verify API no-face/multiple-face errors, permission denial, invalid input and stale response cancellation.
- [x] Verify real Next.js-to-Flask-to-trained-model upload integration.
- [x] Build production frontend and resolve reported PostCSS dependency advisories.
- [x] Document setup, local startup, reproducibility and measured limitations.

## Manual follow-up

- [ ] User checks physical webcam permission, image quality, and the result in their browser.
- [ ] Measure accuracy on representative camera images before claiming real-world performance.

These follow-ups do not change the completed implementation scope; physical-camera accuracy has not been established by automated synthetic-stream tests.

## Camera scan correction

- [x] Add face-box scan endpoint and camera-only image-quality gates.
- [x] Align scan overlay with mirrored, letterboxed video.
- [x] Wait for a stable face and combine five consistent frame estimates.
- [x] Reset on motion/face loss/poor quality, cancellation or retry.
- [x] Verify new camera behavior and existing upload integration; restart local services.

## Fine-tuning and usability iteration

- [x] Preserve baseline and run three-epoch partial fine-tuning with capture augmentation.
- [x] Select candidate on validation, evaluate existing test split and document subgroup limitations.
- [x] Promote improved candidate and reload it in Flask.
- [x] Add capture-quality indicators with actual quality states and reset behavior.
- [x] Add persistent dark/light mode matching Goobo Labs branding.
- [x] Verify production build, backend tests, browser flows and desktop/mobile dark views.
- [ ] Future: obtain a separate labeled camera dataset to measure real-webcam accuracy.
