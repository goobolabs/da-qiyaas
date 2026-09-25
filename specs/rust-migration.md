# Rust processing and model training migration

Date: 2026-09-25. Status: proposed; documentation only. Implementation awaits the user's next instruction.

## Objective and scope

Move image processing and machine-learning computation into Rust, including real model training, fine-tuning and evaluation. As explicitly clarified by the user, Python/Flask remains the backend for HTTP APIs and application logic. Flask calls a Rust native extension for processing/inference; a standalone Rust CLI handles training. Python remains required to run the backend. A one-time conversion of existing trusted Python checkpoints is allowed during transition.

Next.js remains the frontend. Python retains Flask/Waitress, request/response handling, speech, feedback consent and SQLite transactions. Rust owns image decoding/processing, detection, quality checks, model computation and training/evaluation. Existing Python utilities may remain. This proposal does not introduce a different model architecture, new dataset, GPU requirement or new product features.

## Current baseline from repository inspection

| Area | Existing implementation | Migration obligation |
| --- | --- | --- |
| HTTP service | `backend/app.py`, Flask/Waitress, loopback port 5000 | Retain Python handlers and adapt their calls to the Rust extension; preserve external contracts |
| Image processing | Pillow decoding/EXIF/RGB and thumbnailing; OpenCV grayscale, YuNet and quality metrics | Reproduce ordering, geometry, interpolation, thresholds and input limits |
| Age model | `ml/model.py`, torchvision MobileNetV3 Small/Large, adaptive pooling, 128-unit regression head, dropout 0.2 | Support both backbones; preserve layer parameters and evaluation behavior |
| Recorded active model | `mobilenet_v3_large_balanced_crops`; existing weights were trained using Haar crops | Verify the live checkpoint hash/metadata before importing; keep a restoration copy |
| Detector | `ml/face_detect.py`, YuNet 2023mar, score 0.7, NMS 0.3, top-k 5000 | Reuse the pinned ONNX detector and checksum; this file is a face detector, not an exported age model |
| Training | `ml/train.py`, `finetune.py`, `improve.py`, `compare_large.py` | Port preparation, head training, partial fine-tuning, comparison, validation selection and evaluation |
| Dataset | `ml/prepare.py`, local UTKFace; existing 16,176/3,467/3,470 train/validation/test manifests | Reuse current membership and preserve audit/deduplication/conflicting-label rules |
| Feedback | `backend/feedback.py`, `data/feedback.sqlite3` | Retain Python storage/consent logic; delegate photo validation/sanitization to shared Rust processing |
| Speech | `backend/speech.py`, fixed Somali sentences, local MP3 first, optional Azure fallback | Retain Python implementation and verify availability/audio behavior after integration |
| Browser | Next.js API proxy and Playwright flows | Preserve camera scan, upload, cancellation, feedback, dashboard, theme and speech |

Recorded reference metrics: Large full-portrait test MAE 5.687 years; later YuNet crop test MAE 5.681 years on 3,465/3,470 images. These are historical measurements from `docs/model-large-comparison.json` and `docs/model-detector-comparison.json`, not Rust results. Recompute a validation reference from the actual active checkpoint before measuring migration equivalence.

The previously recorded machine is Windows with an i7-10610U, 4 cores/8 threads and approximately 32 GB RAM. No NVIDIA GPU was recorded. During this planning review, `cargo` and `rustc` were not found on PATH. This does not establish whether an installation exists elsewhere. Toolchain installation and native-library compatibility are unverified.

## Proposed architecture and dependency decision

```text
Next.js -> Python Flask API -> PyO3 extension -> Rust image pipeline/model
                 |                                       |
                 +-> SQLite feedback / speech             +-> LibTorch CPU

Rust training CLI -> audited manifests -> shared image pipeline
                  -> train / validate / evaluate -> versioned model bundle
```

Proposed workspace, to be created only during implementation:

- `rust/crates/age-core`: image validation, detection, crop/quality/preprocessing contracts, model architecture and artifact loading.
- `rust/crates/age-train`: audit/prepare, training recipes, validation, evaluation and benchmarks.
- `rust/crates/age-python`: PyO3 extension exposing the shared Rust core to Flask; packaged with maturin.
- `backend/`: retained Python HTTP/application layer with a small adapter for native results/errors.
- `rust/Cargo.toml` and committed `Cargo.lock`: workspace and pinned dependency graph.
- `models/rust-runs/<run-id>/`: local weights, metadata, reports and candidate artifacts, excluded from Git.

Use `tch` with LibTorch for the proposed initial ML implementation. Its upstream documentation describes Rust access to PyTorch's C++ tensor and gradient APIs, training examples and Windows MSVC requirements. This makes it a reasonable compatibility candidate for the existing PyTorch model; compatibility with this project's checkpoint is still an experiment. [tch upstream](https://github.com/LaurentMazare/tch-rs)

Use OpenCV's Rust bindings for the existing YuNet/quality operations. The crate requires native OpenCV/build dependencies; a Python OpenCV wheel is not a substitute for a verified Rust build. Flask/Waitress continues serving HTTP. [OpenCV bindings](https://github.com/twistedfall/opencv-rust)

Propose PyO3 for the native Python extension and maturin for building/installing its wheel. Validate the selected releases against the project's Python 3.14 environment and Windows native dependencies in R0 before committing to version pins. [PyO3 documentation](https://pyo3.rs/main/), [maturin documentation](https://www.maturin.rs/)

Burn is an alternative if removing LibTorch becomes a requirement or the compatibility experiment fails. It supports Rust model training and multiple backends, but choosing it here would require a separate architecture/import/parity experiment. Do not change frameworks silently after a failed gate. [Burn documentation](https://burn.dev/docs/burn/), [Burn training](https://burn.dev/docs/burn/train/index.html)

Exact versions must be pinned after a working Windows release build. `requirements.txt` pins Python torch 2.14.0; do not assume that installation matches the chosen `tch` release. Use a compatible standalone LibTorch distribution for the final runtime, record DLL paths and build profiles, and do not bypass library-version checks. Rust source here still relies on native C++ numerical libraries. A language rewrite alone does not establish faster tensor kernels or better age accuracy.

## Python–Rust integration boundary

- Flask owns request parsing, HTTP body limits, response serialization, headers and mapping typed processing errors to existing API codes/statuses. Pass bounded encoded image bytes and explicit camera/scan flags to Rust; avoid passing PIL or Python torch objects across the boundary.
- The Rust extension owns a reusable predictor loaded once per backend process. Return age, normalized box, quality and readiness as simple Python-compatible values. Release interpreter attachment during long native computation using the pinned PyO3 API; synchronize detector/model access independently of Python's execution lock.
- Rust owns pixel-limit validation, decoding, EXIF/RGB conversion and downstream processing. For consented contributions, expose a sanitization operation returning bounded JPEG bytes/checksum for the existing Python transaction logic.
- Convert recoverable Rust errors into controlled Python exceptions/results. Verify extension import failures, missing DLLs, bad artifacts and concurrent requests; preserve readiness/error behavior and never fabricate a successful prediction after a native failure.
- Keep the Rust training CLI independent of the extension crate so that training does not require a Python process. Flask may orchestrate an explicitly requested offline job later; adding a web training endpoint is outside this scope.
- During migration, keep the original Python predictor available through explicit startup configuration for comparison/rollback. Avoid loading Python torch and a different LibTorch distribution in the same process; compare engines in separate processes and validate DLL loading. Select the Rust engine only after the integration gates pass.

## Image processing and inference contract

1. Accept JPEG, PNG and WebP; preserve existing malformed-image and oversized-image errors. Bound each image to 8 MiB, multipart overhead to the existing 64 KiB allowance and decoded dimensions to 16 million pixels. Check dimensions before allocating the decoded image.
2. Preserve EXIF orientation and RGB conversion, including grayscale and alpha cases. Decode in memory; ordinary camera/upload requests must not create persistent images or image logs.
3. Preserve the aspect-ratio thumbnail bounded to 1280 by 1280 before detection. Match Pillow's actual resize/rounding behavior using fixtures rather than assuming all libraries produce the same pixels.
4. Use detector SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` and detector ID `yunet_2023mar_score70`. Verify locally stored/fetched detector bytes. Preserve RGB-to-BGR conversion, integer truncation, clipped boxes, single-face rules and normalized coordinates.
5. Serialize each detector instance's mutable input-size/detect operations or give a worker its own instance. Bound workers and queue length to prevent large images and tensor threads from exhausting memory or oversubscribing the CPU.
6. Preserve camera thresholds: minimum face side 100 pixels and normalized side 0.16; grayscale mean 45 through 220; Laplacian variance at least 35 after OpenCV 160-pixel resizing. Preserve error priority: small, low light, overexposed, blurry.
7. Apply the shared crop margin `int(max(width, height) * 0.15)` clipped to image bounds. Resize to 160 by 160 with the current bilinear/antialias semantics. Convert to float32 RGB CHW in [0,1], then normalize by mean `[0.485, 0.456, 0.406]` and standard deviation `[0.229, 0.224, 0.225]`.
8. Load the model once, use evaluation mode with gradients disabled during inference, reject non-finite outputs, clamp to [0,120] and match Python rounding to one decimal. Include rounding ties in compatibility fixtures; the frontend continues rounding the displayed integer.
9. Preserve upload versus camera response shapes, including optional/null `quality` and `face_box`. `/api/scan` performs quality/detection work without estimating age, and retains the current model-readiness behavior.

## Model artifact migration

- Hash and snapshot the active checkpoint, its metadata and portable reports before conversion. Treat original files as restoration artifacts throughout migration.
- Recreate the actual torchvision MobileNetV3 feature topology for Small and Large, including activation, squeeze/excitation, padding, normalization buffers, pooling and the project regression head. Do not substitute a similarly named architecture without a parameter-by-parameter check.
- The existing `.pt` file contains a Python checkpoint dictionary with `state_dict` and metadata. Do not assume `tch` can directly load it as a trainable model. Plan a one-time export to a verified named-tensor format supported by the pinned Rust stack, with a JSON sidecar. Missing/unexpected keys, incompatible tensor shapes and unsupported metadata must fail loading.
- Record artifact format/version, architecture, image size, normalization, age range, detector and crop versions, source checkpoint hash, weight hash, split-manifest hashes, seed, training configuration and library versions.
- Inference-only converted artifacts do not satisfy the training requirement. Prove that the Rust architecture loads the imported parameters, computes gradients and updates intended layers.
- Save candidates in unique directories. After validation, atomically publish the complete bundle with a Windows-tested replacement strategy; verify the incumbent hash has not changed since the run started. Restart/readiness checks must support restoring Flask's original Python predictor and model without changing data.

## Training and evaluation contract

- Reuse the existing manifest membership for migration comparisons. Port dataset auditing and preparation for future explicit rebuilds, preserving age parsing, decoded-pixel duplicate hashing and contradictory-label exclusion. Do not regenerate the splits merely because Rust's random generator differs from Python's.
- Preserve seed 42 for the original baseline recipe, 73 for partial fine-tuning, 109 for balanced crop work and 209 for the Large comparison as recorded configurations. Record sampler/augmentation randomness explicitly; equal seed numbers do not guarantee identical streams across languages.
- Port frozen feature extraction/head training and partial backbone fine-tuning. Preserve age-target scaling, loss definitions, AdamW parameter groups, learning-rate schedules, early stopping, augmentation and age-balanced sampling from the corresponding Python recipe.
- Support the current Large recipe: head warm-up up to 60 epochs and blocks 10 onward fine-tuned for six epochs, with frozen batch-normalization statistics. Preserve the Small recipes for reproduction and baseline comparison.
- Key feature and detection caches by input/manifest, model/preprocessing and detector identity as applicable. Never interpret Python pickle caches as Rust artifacts without conversion/validation; regenerate in a versioned format when needed.
- Use the shared YuNet detector for training/evaluation/serving. The incumbent was trained on Haar crops, so a new YuNet training run is a separate model candidate; measure imported-weight equivalence before that run.
- Training contributions remain pending review. Neither ordinary numeric feedback nor collected photos enter these UTKFace runs automatically. Validation/test images and the owner's demo portrait are never training inputs.
- Compare candidates against the incumbent using the same validation images, full-portrait and crop views, per-age-band counts/MAE and detector coverage. Preserve the accuracy spec's promotion rule: crop MAE improves at least 0.1 years, full-image MAE does not worsen and no age band worsens more than 1 year on either view.
- Freeze model selection before the final test evaluation. The reused UTKFace test split is not an external holdout and cannot establish physical-webcam accuracy. Routine development and parity selection use training/validation fixtures, not repeated test tuning.
- Save weights, configuration, history and validation report for each run. Record whether optimizer/scheduler/RNG state supports exact resume; if not, label the operation as a new fine-tuning run rather than an exact resume.

## API and stored-data continuity

Keep these endpoints in Python/Flask. Capture executable contracts before integrating the Rust processing engine:

| Endpoint | Required behavior |
| --- | --- |
| `GET /api/health` | Same readiness JSON and 200/503 behavior |
| `POST /api/scan` | Same multipart image, camera quality fields, face box and errors |
| `POST /api/predict` | Same multipart image/source, age, unit, estimate flag and camera-specific fields |
| `GET /api/speech` | Same local/Azure availability reporting |
| `POST /api/speech` | Integer age 0–120, fixed Somali sentence, MP3 response, local-first behavior and bounded fallback |
| `POST /api/feedback` | Existing JSON numeric feedback and separately consented multipart photo contribution |
| `GET /api/feedback/summary` | Same aggregate-only output, empty groups and storage-error behavior |

Retain `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`, English errors, loopback defaults and Next.js `BACKEND_URL` routing. Capture body-limit failures and unknown/invalid fields in addition to successful requests. Run database checks against temporary copies/fixtures, never against live feedback records.

Keep the existing SQLite tables, submission-id idempotency, atomic feedback/photo transaction, private JPEG bytes/checksum, `training-photo-v1` consent and pending-review status. Preserve re-encoding to a maximum 1280-pixel side and stripping source filenames/EXIF. No new endpoint exposes individual feedback or photos.

## Phases and completion gates

| Phase | Deliverable | Exit condition |
| --- | --- | --- |
| R0: compatibility baseline | Artifact/manifest hashes, API fixtures, validation references; pinned Windows build recipe | Rust release CLI and Python extension load native dependencies; tensor forward/backward and YuNet smoke checks pass |
| R1: shared processing | Image/decode/detection/quality/preprocessing library | Fixture parity and all input/error boundaries pass |
| R2: imported inference | Trainable Small/Large definitions and converted active weights | Strict weight mapping, numerical parity and reload checks pass before training |
| R3: Rust training | Preparation/training/fine-tuning/evaluation CLI and run reports | Frozen-layer/gradient checks, repeatable small run and a complete configured run pass; rejected candidates remain unpromoted |
| R4: Flask integration | Python adapter and Rust extension, including contribution sanitization | Backend contracts, native error/concurrency checks and browser flows pass with Flask calling Rust |
| R5: engine cutover | Benchmark report, extension installation/startup and restoration procedure | Gates below pass; select Rust processing in Flask and verify health, upload, scan, feedback and speech |

Migration parity gates, to be fixed before implementation measurements:

- Exact agreement on fixture formats, orientation, dimensions, face count, error code/status and quality state. Corresponding face-box edges may differ at most one pixel; investigate any threshold-boundary decision mismatch.
- On identical preprocessed tensors, imported raw model outputs must agree within 0.001 years absolute error. On the complete accepted validation image pipeline, maximum raw-age difference must be at most 0.1 years and MAE change at most 0.05 years for both supported evaluation views. Detection coverage must match; do not hide differing subsets inside MAE averages.
- Successful API fixtures must have the same displayed integer age. Record any rounding-boundary differences in the broader validation comparison and resolve them before cutover rather than silently rounding away drift.
- Verify a deterministic, augmentation-free mini-batch forward/backward/update against Python with documented numerical tolerances. Frozen parameters and batch-normalization statistics must remain unchanged; trainable parameters must change, loss/gradients must remain finite and save/reload must preserve predictions.
- Training acceptance means the Rust process performs gradient updates and produces a reloadable evaluated checkpoint without invoking Python. An improved candidate is desirable but is not required to prove the migration works; only a candidate passing the separate accuracy gates may replace the incumbent.
- Run the existing browser suites against Flask with the Rust extension, including camera reset/cancel/stale responses, speech, consent/photo feedback, summary dashboard and real-model upload. Add Rust tests for migrated processing/model behavior; retain Python API/speech/feedback coverage and adapt predictor fixtures to exercise the native boundary.
- Compare warmed release CPU runs using identical inputs, four tensor threads and alternating backend order: preprocessing/detection/model/end-to-end p50 and p95, peak resident memory, epoch time and images/second. Record sample counts, warm-up and cold startup separately. Proposed cutover ceiling: no greater than 10 percent regression in end-to-end p95 or peak resident memory under equal concurrency. Investigate repeated regressions before cutover; report actual training throughput without promising a speedup.
- Complete `cargo fmt --check`, workspace Clippy and Rust tests under the validated Windows setup; run Python backend tests, frontend production build and relevant Playwright suites. Verify Flask loads the installed extension in the supported Python environment and the standalone Rust training CLI runs without invoking Python.

If a gate fails, keep Flask using the original Python processing engine and artifacts, document the failed assumption and revise the proposal before engine cutover. Do not relax a tolerance after observing results without an explicit documented decision.

## Planning review outcome

This document and the linked requirements, plan, tasks and verification notes are the deliverables for the current request. No Rust workspace has been created, no tools installed, no model converted or trained, and no running backend changed. The next implementation step, when requested, is R0.
