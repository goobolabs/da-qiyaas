# Implementation tasks

Status: version 1 implemented and verified following user authorization on 2026-09-09. Rust migration implementation was authorized on 2026-09-25, with each issue tested before its PR. Issue #4 reference capture is implemented; later issues remain pending.

## Rust migration — proposed 2026-09-25

Detailed dependencies and acceptance gates: [rust-migration.md](rust-migration.md). Implementation proceeds R0 through R5 in dependency order, with a separate tested PR for each issue.

GitHub issues are published: [tracking issue #12](https://github.com/goobolabs/da-qiyaas/issues/12) links the eight implementation issues (#4–#11) for the user to implement. See [migration-issues.md](migration-issues.md) for their bodies and dependency order. All nine issues were verified open on 2026-09-25.

- [x] Inspect Python processing/training, existing product routes and recorded evaluation evidence.
- [x] Document target stack, checkpoint transition, parity gates, training requirements and rollback.
- [x] Update requirements and distinguish proposed Rust work from historical Python results.
- [x] Incorporate the user's clarification: retain the Python/Flask backend and integrate Rust processing/inference through a native extension.
- [x] R0 / #4: Snapshot artifact/manifest hashes, API fixtures and validation baselines; see [reference guide](../docs/migration/README.md).
- [ ] R0: Validate Windows MSVC/Rust, Python/PyO3/maturin extension import, compatible LibTorch/OpenCV and release forward/backward/detector smoke checks; pin dependencies.
- [ ] R1: Port shared image validation, EXIF/RGB, resize, YuNet, quality checks, crops and normalization; satisfy fixture parity.
- [ ] R2: Recreate Small/Large architectures, convert trusted weights once and verify parameter mapping, raw inference parity and reload.
- [ ] R3: Port audit/preparation and preserve existing split membership; version caches and training configuration.
- [ ] R3: Port head training, partial fine-tuning, balanced sampling, augmentation, validation selection and final evaluation.
- [ ] R3: Verify gradients/frozen layers and complete a Rust training run without Python; keep promotion subject to accuracy gates.
- [ ] R4: Connect existing Flask health/scan/predict and photo sanitization to the Rust extension; preserve Python speech, feedback and SQLite logic.
- [ ] R4: Verify existing SQLite/consent behavior and API contracts using temporary databases.
- [ ] R5: Run Rust checks, Python backend tests, frontend build, browser flows and real-model integration against Flask with the Rust extension.
- [ ] R5: Record release latency/memory/training benchmarks and resolve cutover regressions.
- [ ] R5: Update extension/backend and CLI operating instructions; verify standalone Rust training, switch Flask's processing engine and test restoration of the original Python processing/artifacts.

## Completed original implementation

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

## Crop-aware and Large backbone accuracy work

- [x] Audit predictions across six age bands and reproduce the runtime crop/full-portrait mismatch.
- [x] Preserve the active checkpoint and metrics before every training run.
- [x] Add crop-aware balanced fine-tuning with full-portrait and detected-face validation.
- [x] Make the checkpoint format and loader carry the backbone so Small and Large both load.
- [x] Train a MobileNetV3 Large candidate with a warmed head and blocks 10 onward.
- [x] Gate promotion on crop, full-portrait and age-band validation, then evaluate the test split once.
- [x] Measure alternating warmed CPU latency for the candidate and the incumbent.
- [x] Promote the Large checkpoint, restart Flask and confirm varied live API estimates.
- [x] Update portable metrics under docs/ and the README results, including the speed cost.
- [ ] Future: sweep Large learning rates, unfrozen depth and seeds; one run is not a tuned result.

## YuNet face detector

- [x] Measure Haar single-face coverage and confirm it rejects nearly half the portraits.
- [x] Add a shared detector module with pinned, checksum-verified YuNet weights fetched on first use.
- [x] Key cached face boxes by detector identity so older boxes are rebuilt.
- [x] Use the one detector in Flask, training and evaluation.
- [x] Compare Haar and YuNet on validation, including a crop-margin sweep, before touching the test split.
- [x] Evaluate the test split after the decision and report coverage separately from error.
- [x] Restart Flask and confirm portraits the old detector rejected now return estimates.
- [x] Record the comparison under docs/ and document the change.
- [ ] Future: retrain crop-aware on YuNet boxes; the active weights still come from Haar crops.
- [ ] Future: benchmark detection latency and camera-frame coverage, which cropped portraits do not predict.

## Somali speech without a speech account

- [x] Confirm both Somali neural voices are reachable through the keyless Edge read-aloud service.
- [x] Add a reproducible generator for the 121 fixed sentences, with MP3 and size validation.
- [x] Serve local clips ahead of Azure, and report the active source from the availability route.
- [x] Keep Azure as an optional fallback so an existing key still works.
- [x] Cover the new path with tests that isolate the clip directory from locally generated audio.
- [x] Generate the clips, restart Flask and confirm playback in the browser with no credentials set.
- [ ] Future: a Somali speaker should listen to the clips and confirm pronunciation of every number.
