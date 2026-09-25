# Rust migration issue drafts

Status: ready to publish. GitHub creation was attempted on 2026-09-25 but the connected integration returned HTTP 403 (`Resource not accessible by integration`). No new GitHub issue was created.

Repository: https://github.com/goobolabs/da-qiyaas

The user will implement these issues. Python/Flask remains the backend; Rust handles processing, inference and training. These drafts are self-contained and accompany the [migration specification](rust-migration.md).

## Tracking issue

Title: [Rust migration] Track Rust processing and training with the Python backend

Move computational work into Rust through a PyO3 extension and standalone training CLI while keeping Python/Flask, speech and SQLite application logic. Follow the local `specs/rust-migration.md` specification.

Create the eight implementation issues below and replace the local draft links with their GitHub issue references. Close this tracking issue when their acceptance gates pass and Flask's Rust processing engine plus rollback have been verified.

- [ ] [[Rust migration R0] Capture Python contracts and model parity baselines](#issue-1-baseline)
- [ ] [[Rust migration R0] Validate Windows Rust, PyO3, LibTorch and OpenCV builds](#issue-2-toolchain)
- [ ] [[Rust migration R1] Port image decoding, YuNet and preprocessing to Rust](#issue-3-processing)
- [ ] [[Rust migration R2] Import trainable MobileNetV3 models and verify inference parity](#issue-4-model)
- [ ] [[Rust migration R3] Port dataset auditing, manifests and versioned caches](#issue-5-data)
- [ ] [[Rust migration R3] Implement Rust training, fine-tuning and evaluation CLI](#issue-6-training)
- [ ] [[Rust migration R4] Integrate the Rust predictor into the Python Flask backend](#issue-7-flask)
- [ ] [[Rust migration R5] Verify performance, package the extension and document engine cutover](#issue-8-cutover)

Existing issues remain separate: [#1 webcam accuracy](https://github.com/goobolabs/da-qiyaas/issues/1), [#2 YuNet retraining](https://github.com/goobolabs/da-qiyaas/issues/2), [#3 Somali speech review](https://github.com/goobolabs/da-qiyaas/issues/3). Coordinate the new training issue with #2.

## Issue 1: baseline

Title: [Rust migration R0] Capture Python contracts and model parity baselines

Dependencies: none; can start first.

## Outcome

Create a reproducible reference for moving image processing, inference and training into Rust while retaining the Python/Flask backend.

## Work

- Hash and preserve the active checkpoint, model metadata, YuNet weights and existing train/validation/test manifests. Keep weights, images and private databases out of Git.
- Record the actual active model architecture and preprocessing settings. The recorded incumbent is MobileNetV3 Large with 160×160 input and a 15% crop margin.
- Capture success/error contracts for health, scan, prediction, speech, feedback and feedback summary from the Python service and tests.
- Generate deterministic training/validation fixtures for decoding, EXIF, grayscale/alpha, malformed/oversized input, face boxes, quality thresholds, crops, normalized tensors and rounding boundaries.
- Record full-portrait/crop validation MAE, age-band results, detector coverage and raw predictions. Do not tune against the test split.
- Keep implementation aligned with the agreed migration specification under `specs/` and record any approved changes to it.

## Done when

- [ ] Baselines can be reproduced from recorded commands, hashes and configuration.
- [ ] Fixture contracts cover status codes, response shapes, errors and transient image handling.
- [ ] The reference clearly distinguishes historical results from new measurements.
- [ ] Original artifacts and split membership remain recoverable.

Relevant files: `backend/app.py`, `backend/tests/`, `ml/model.py`, `ml/face_detect.py`, `ml/face_crop.py`, `specs/rust-migration.md`.

## Issue 2: toolchain

Title: [Rust migration R0] Validate Windows Rust, PyO3, LibTorch and OpenCV builds

Dependencies: none; can start first.

## Outcome

Prove the proposed native stack works on Windows before porting the model. Python/Flask remains the HTTP backend.

## Work

- Validate Rust/MSVC, native OpenCV build dependencies, compatible `tch`/LibTorch CPU versions, and PyO3/maturin against the project's Python 3.14 environment. Cargo/rustc were not found on PATH during planning.
- Scaffold a workspace with `age-core`, `age-train` and `age-python`; keep the training CLI independent of the Python extension crate.
- Build a release CLI and extension wheel; test installation/import in the supported Python environment.
- Run tensor forward/backward and checksum-verified YuNet smoke checks.
- Pin verified dependencies and commit Cargo.lock. Document compiler profiles and native DLL paths; do not bypass version checks.
- Test native loading without mixing Python torch and an incompatible LibTorch distribution in the same process.

## Done when

- [ ] A clean documented Windows setup builds/imports the release extension.
- [ ] The standalone CLI performs a gradient update and loads YuNet.
- [ ] Required DLLs and Python ABI compatibility are verified.
- [ ] Toolchain/native dependency failures are recorded before choosing any alternative framework.

References: [tch](https://github.com/LaurentMazare/tch-rs), [OpenCV bindings](https://github.com/twistedfall/opencv-rust), [PyO3](https://pyo3.rs/main/), [maturin](https://www.maturin.rs/).

## Issue 3: processing

Title: [Rust migration R1] Port image decoding, YuNet and preprocessing to Rust

Dependencies: [draft 1: baseline](#issue-1-baseline), [draft 2: toolchain](#issue-2-toolchain).

## Outcome

Provide one shared Rust image pipeline for training and Flask inference.

## Work

- Accept JPEG/PNG/WebP and preserve EXIF orientation, RGB conversion and Pillow-compatible resize behavior.
- Enforce an 8 MiB image limit and 16 million decoded pixels before large allocation; Flask retains multipart/body validation.
- Preserve 1280-pixel maximum-side thumbnailing, YuNet score 0.7/NMS 0.3/top-k 5000, integer/clipped boxes and normalized coordinates.
- Verify detector SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; retain detector ID `yunet_2023mar_score70`.
- Preserve camera checks and error order: face side ≥100 px and normalized side ≥0.16; brightness 45–220; Laplacian variance ≥35 after 160-pixel normalization.
- Preserve 15% clipped crop margin and bilinear/antialias resize to 160×160; float32 RGB CHW, ImageNet mean/std.
- Provide photo sanitization returning a maximum-1280-side JPEG with EXIF/filenames stripped for separately consented contributions.
- Synchronize mutable detector instances and bound native concurrency. Ordinary prediction images remain transient.

## Done when

- [ ] Fixture formats, orientation, dimensions, face count, error code and quality states match Python.
- [ ] Corresponding face-box edges differ by at most one pixel; threshold decision mismatches are resolved.
- [ ] Decode/crop/tensor parity checks and invalid/oversized-input cases pass.
- [ ] Sanitization preserves contribution requirements without writing photos itself.

Relevant files: `backend/app.py`, `ml/face_detect.py`, `ml/face_crop.py`, `ml/model.py`.

## Issue 4: model

Title: [Rust migration R2] Import trainable MobileNetV3 models and verify inference parity

Dependencies: [draft 1: baseline](#issue-1-baseline), [draft 2: toolchain](#issue-2-toolchain), [draft 3: processing](#issue-3-processing).

## Outcome

Load the existing age-model weights into trainable Rust Small/Large architectures before changing training recipes.

## Work

- Recreate torchvision MobileNetV3 Small/Large feature topology, normalization buffers, activations, squeeze/excitation, adaptive pooling and the 128-unit regression head with dropout 0.2.
- Convert the trusted Python checkpoint dictionary once into a verified named-tensor format plus metadata. Do not assume the existing .pt dictionary loads directly into tch.
- Strictly validate parameter names/shapes and metadata; preserve original checkpoint hashes.
- Version the bundle with architecture, normalization, image size, age range, detector/crop versions, weight/source hashes, manifest hashes and training configuration.
- Load once in evaluation mode, disable gradients for prediction, reject non-finite output and preserve clamp/rounding behavior.
- Verify gradients can be computed on the imported architecture; an inference-only export is insufficient.

## Done when

- [ ] Small and Large save/reload checks pass; invalid/missing keys and unsupported metadata fail safely.
- [ ] Identical tensor inputs produce raw ages within 0.001 years absolute difference.
- [ ] Full validation pipeline maximum raw-age difference is ≤0.1 years and MAE change ≤0.05 years on both evaluation views, with matching detection coverage.
- [ ] API fixtures keep the same displayed age; rounding-boundary differences are investigated.
- [ ] Evidence exists before any new YuNet training run.

Relevant files: `ml/model.py`, `backend/tests/test_model.py`, `specs/rust-migration.md`.

## Issue 5: data

Title: [Rust migration R3] Port dataset auditing, manifests and versioned caches

Dependencies: [draft 1: baseline](#issue-1-baseline), [draft 3: processing](#issue-3-processing).

## Outcome

Prepare reproducible data for Rust training using the current UTKFace split membership.

## Work

- Port filename age parsing, image decoding audit, decoded-pixel duplicate grouping and contradictory-label exclusion from `ml/prepare.py`.
- Reuse the current 16,176 train / 3,467 validation / 3,470 test membership for migration comparisons; validate manifest hashes instead of resplitting.
- Provide an explicit preparation command for future dataset rebuilds and document the seed/randomness algorithm.
- Version detection caches with detector identity and preprocessing configuration; version embedding caches with model and manifest fingerprints.
- Convert verified cache contents or rebuild them; do not treat Python pickle caches as native Rust data.
- Keep original images immutable and all data/weights private to local ignored directories.
- Exclude validation/test/demo images and unreviewed feedback contributions from training.

## Done when

- [ ] Audit rules reproduce the reference audit on the same dataset.
- [ ] Existing split membership is preserved exactly with no duplicate leakage.
- [ ] Stale model/detector/preprocessing caches are rejected or rebuilt.
- [ ] Repeat runs produce documented, reproducible manifests/cache metadata.

Related future work: #2 concerns a new YuNet-trained candidate; it does not replace this data-porting task.

## Issue 6: training

Title: [Rust migration R3] Implement Rust training, fine-tuning and evaluation CLI

Dependencies: [draft 4: model](#issue-4-model), [draft 5: data](#issue-5-data).

## Outcome

Perform real gradient-based age-model training in a standalone Rust process, sharing the inference pipeline used by Flask.

## Work

- Port frozen-feature head training, partial fine-tuning and balanced crop recipes from `ml/train.py`, `finetune.py`, `improve.py` and `compare_large.py`.
- Preserve target scaling, losses, AdamW parameter groups, schedules, early stopping, augmentation and balanced sampling. Record seeds/configuration; equal seed numbers across languages do not guarantee identical randomness.
- Support Small recipes and Large head warm-up up to 60 epochs plus six fine-tuning epochs of blocks 10 onward, with batch-normalization statistics frozen.
- Verify a deterministic augmentation-free mini-batch forward/backward/update against Python with declared numerical tolerances.
- Save versioned run weights/config/history/reports and document whether exact optimizer/scheduler/RNG resume is supported.
- Select using validation only: crop MAE improves ≥0.1 years, full-portrait MAE does not worsen and no age band worsens >1 year on either view. Evaluate the test split only after selection.
- Keep failed candidates unpromoted and preserve the incumbent. Report detector coverage independently from age error.

## Done when

- [ ] Rust CLI trains without invoking Python.
- [ ] Frozen parameters/BN statistics remain unchanged; intended parameters update with finite gradients/loss.
- [ ] A repeatable small run and a complete configured run produce reloadable, evaluated artifacts.
- [ ] Promotion decision and latency/accuracy tradeoffs are recorded; improvement is measured, not assumed.

Coordinate any YuNet candidate/promotion report with existing #2 to avoid duplicating that accuracy experiment.

## Issue 7: flask

Title: [Rust migration R4] Integrate the Rust predictor into the Python Flask backend

Dependencies: [draft 4: model](#issue-4-model).

## Outcome

Keep Flask/Waitress as the backend while delegating image processing and inference to a PyO3 extension.

## Work

- Expose a reusable Rust predictor through `age-python`, packaged with maturin. Pass bounded encoded bytes and camera/scan flags; return simple age/box/quality/readiness values.
- Load one predictor per process. Release interpreter attachment during long native work using the pinned PyO3 API; synchronize native detector/model access and bound concurrency.
- Adapt Python health/scan/predict handlers without changing response shapes, status/error codes, headers, body limits or Next.js routing.
- Route contribution photo sanitization through shared Rust processing while Python retains consent checks, SQLite transactions/idempotency and summary logic.
- Keep speech/local MP3/Azure behavior in Python.
- Translate native errors into controlled API responses. Exercise missing DLLs, extension import failures, incompatible artifacts and concurrent requests.
- Add explicit startup engine selection for migration/rollback. Avoid importing Python torch with an incompatible native LibTorch in the same process; compare engines in separate processes.

## Done when

- [ ] Existing Python API, speech and feedback tests pass with the Rust adapter.
- [ ] Native boundary tests verify readiness, error mapping, thread safety and transient image handling.
- [ ] Temporary-database tests preserve numeric/photo consent, atomic writes, retry idempotency and aggregate-only summaries.
- [ ] Original Python prediction remains restorable through documented startup configuration.

No Rust HTTP server or new training endpoint is required.

## Issue 8: cutover

Title: [Rust migration R5] Verify performance, package the extension and document engine cutover

Dependencies: [draft 6: training](#issue-6-training), [draft 7: flask](#issue-7-flask).

## Outcome

Make the Flask-plus-Rust system reviewable and reproducible, then enable Rust processing only after migration gates pass.

## Work

- Run cargo fmt --check, workspace Clippy/tests, Python backend tests, frontend production build and Playwright flows with Flask calling Rust.
- Cover real-model upload, camera reset/cancel/stale responses, quality gates, speech, consented photo feedback, summary/dashboard and theme.
- Benchmark release builds on identical CPU inputs with four tensor threads, equal concurrency and alternating engine order. Report warm-up/sample counts, preprocessing/detection/model/end-to-end p50/p95, cold start, peak memory, epoch time and images/second.
- Proposed cutover ceiling: ≤10% regression in end-to-end p95 and peak resident memory. Investigate repeatable regressions; do not promise training acceleration.
- Document reproducible wheel installation/native DLL setup, Flask startup/engine selection, standalone Rust training and artifact locations.
- Publish complete versioned model bundles atomically using a Windows-tested strategy; recheck incumbent hashes before activation.
- Exercise rollback to the original Python processing engine/artifacts without touching dataset or feedback records. Update operating docs and verification with actual results.

## Done when

- [ ] Numerical, API, training and performance gates pass with recorded evidence.
- [ ] Flask imports the installed release extension in the supported Python environment.
- [ ] Rust training runs without invoking Python; backend operation still uses Python.
- [ ] Engine activation and restoration are verified.
- [ ] No migrated feature is marked complete solely from old Python test results.

Existing #1 (physical-webcam accuracy) and #3 (Somali listening review) remain separate follow-ups.
