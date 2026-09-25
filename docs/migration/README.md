# Python reference for the Rust migration

Issue: [#4](https://github.com/goobolabs/da-qiyaas/issues/4). This recorder freezes the current Python behavior before Rust implementation. Flask remains the backend throughout the migration.

## Capture and verify

From the repository root, with the existing Python environment, active checkpoint, checksum-verified YuNet weights and UTKFace manifests/images present:

```powershell
.\.venv\Scripts\python.exe -m ml.migration_baseline capture --name my-python-reference
.\.venv\Scripts\python.exe -m ml.migration_baseline verify models/migration-baselines/my-python-reference
.\.venv\Scripts\python.exe -m pytest backend/tests/test_migration_baseline.py -q
```

Use a new run name each time. Capture refuses an existing directory and never replaces original artifacts. An interrupted run has no `complete.json` marker and fails verification; retain it for inspection and start with a different name. `--validation-limit 20` is available for a smoke run and marks its report `smoke_subset`; it does not satisfy the full validation gate.

Capture is offline: it requires local model/detector files, scripts speech-provider responses, and uses a temporary SQLite database. It does not access the live feedback database or write original checkpoints, images, manifests or detection caches. Existing backend tests still exercise their own documented paths independently.

## Outputs

Everything in `models/migration-baselines/<name>/` is local and Git-ignored:

| File/directory | Purpose |
| --- | --- |
| `snapshot/` | Original checkpoint, detector, all split manifests, audit, portable historical reports and relevant Python source/dependency files |
| `synthetic/` | Generated encoded images, decoded/thumbnail/crop arrays, float32 CHW tensors, quality-boundary and rounding expectations |
| `portraits/` | Deterministic training/validation portrait inputs, crop/tensor arrays, boxes, raw predictions and actual upload/camera/scan outcomes |
| `api-contracts.json` | Offline Flask contract capture with synthetic inputs and temporary storage |
| `validation-predictions.json` | Raw full/crop predictions and detected boxes for each validation image; private manifest paths/labels remain local |
| `report.json` | Artifact hashes, model metadata, dependency versions, preprocessing and newly measured validation metrics |
| `inventory.json`, `complete.json` | Per-file hashes and completion marker; verification rejects corruption, missing files and extra files |

The shared NumPy arrays are non-pickled `.npy` files with dtype/shape/hash metadata. Future Rust tests can load these arrays without Python serialization. Portraits are selected by sorted pixel hash, one per available age band from train and validation only. Exact image hashes must match the existing manifests. No test images are evaluated; the test manifest is preserved solely for split integrity and restoration.

For restoration, verify the bundle first and copy only the needed checkpoint/detector/manifests from `snapshot/` back to their corresponding original paths after stopping the backend. Capture performs no restoration or promotion automatically. Historical reports and source snapshots describe the old runtime; they are never substituted for the newly measured `report.json`.

## Contract and numerical meaning

`python-api-contracts.json` in this directory is the reviewed, portable response reference for all seven routes, including request limits, readiness, camera/upload shapes, inference failure, consent, idempotency, photo storage, summaries and local/mocked-provider speech. Predictor values and provider audio are intentionally scripted to isolate HTTP behavior. Real model outputs are captured separately in the ignored portrait and validation files.

The recorder preserves current behavior, including distinctions that a Rust port could otherwise miss:

- Pillow applies EXIF before RGB conversion, drops alpha rather than compositing, and uses its default bicubic thumbnail resampling. Model resizing uses torchvision/PIL bilinear with antialiasing.
- A PNG just over 16 million pixels currently maps the Pillow decompression-bomb warning to `INVALID_IMAGE`/400 before the explicit size check. Byte/request limits produce 413. This reference records that behavior without changing the application.
- API output clamps to 0–120 and uses Python decimal rounding; browser display uses positive `Math.round` behavior. Binary floating-point ties need explicit fixtures.
- Validation MAE clamps model outputs to 0–120, following `ml.train.metrics`; saved raw predictions remain unclamped for parity checks. Full-portrait and single-face-crop views have separate counts and coverage.
- Quality fixtures cover exact size/lighting thresholds and values just below/above sharpness 35. Float64 sharpness fixtures isolate that mathematical boundary; normal decoded portraits are uint8.

Future Rust comparisons must meet the tolerances in [the migration specification](../../specs/rust-migration.md). This issue does not train, convert, promote or change the running model. Neither synthetic camera tests nor UTKFace validation establish physical-webcam accuracy.

## Updating the portable reference

After reviewing the captured contracts, copy only the synthetic `api-contracts.json` to `docs/migration/python-api-contracts.json`. The contract regression test compares real handler responses with that checked-in reference. Do not regenerate expectations merely to make a failing test pass.

Publish only aggregate metrics/artifact metadata from a completed full-validation report as `python-reference-summary.json`. Never commit `portraits/`, `validation-predictions.json`, snapshots, weights, images or private databases. Document the exact commands and results in `specs/verification.md`.
