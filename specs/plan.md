# Technical plan

Status: the sections below describe the implemented Python design and earlier iterations. The 2026-09-25 Rust migration is defined in [rust-migration.md](rust-migration.md); implementation has started with R0 reference capture for issue #4. Each issue is tested before its PR. See README.md and verification.md for measured results and operating instructions.

## Proposed Rust migration sequence

1. Snapshot current API contracts, artifact hashes, preprocessing outputs and validation baselines; establish compatible Windows Rust/MSVC, LibTorch and OpenCV builds.
2. Port decoding, YuNet detection, capture checks, crops and normalization into a shared Rust library; prove numerical and error-behavior compatibility.
3. Recreate Small/Large architectures, convert the current weights and verify Rust inference against Python before retraining.
4. Port dataset audit, manifest handling, training, fine-tuning, evaluation and candidate selection into a Rust CLI; verify gradients, frozen layers and saved-model reload.
5. Integrate a Rust native extension into the existing Python/Flask backend; preserve its HTTP, speech, feedback and database responsibilities against captured API contracts.
6. Run compatibility and performance gates, document extension installation and rollback, then switch Flask's processing engine only after acceptance.

Proposed stack: existing Python/Flask/Waitress backend, PyO3/maturin for its Rust extension, OpenCV Rust bindings, and `tch` with a compatible LibTorch CPU distribution. The Rust training CLI shares the extension's processing/model core. Final dependency pins follow the compatibility experiment. R0 reference capture makes local snapshots and validation measurements; installation, conversion, training and service cutover belong to subsequent issues.

## Structure and responsibilities

- frontend/: Next.js 15 camera permission, preview, upload, progress, result, and retry UI.
- backend/: Flask input validation, face detection, preprocessing, and model inference.
- ml/: dataset audit, split manifests, training, evaluation, and CPU benchmark.
- models/: model weights and accompanying preprocessing/version metadata.
- data/UTKFace/: source dataset; preserve original images.
- specs/: requirements, plan, and implementation task sequence.

## Prediction flow

1. User selects Camera or Upload.
2. Camera mode requests permission and sends a frame automatically; upload mode sends the selected image.
3. Flask validates the image and checks for a single usable face.
4. Flask crops/prepares the face and runs the loaded age model.
5. Frontend displays the estimated age; camera analysis stops after success.
6. Retry starts a new attempt. Cancel or mode changes discard stale responses and stop camera capture.

Camera requests should be paced, with at most one request in flight. Retry recoverable no-face cases with visible guidance. Retry recoverable face errors after 1.5 seconds; abort requests after 30 seconds.

## API

- POST /api/predict: multipart image input; returns estimated_age on success or a structured error code/message.
- GET /api/health: indicates service and model readiness.
- The client never supplies a filesystem path. Limits: 8 MiB image payload and 16 million decoded pixels; JPEG, PNG and WebP only.
- Load the model once at backend startup and use inference mode for predictions.

## Local training design

- Start on CPU using a lightweight pretrained image model with an age regression output; MobileNetV3 Small is selected, with a frozen backbone and a 576-to-128-to-1 regression head.
- Audit decoding, labels, age distribution, and duplicate images before splitting.
- Target a reproducible 70/15/15 train/validation/test split that represents age ranges.
- Keep duplicates in the same split. Group known identities if reliable identity information is available; otherwise document that identity separation is not guaranteed.
- Train the regression head first with the backbone frozen. Benchmark before deciding whether to fine-tune additional layers.
- Use validation data for model selection; reserve the test set for final evaluation.
- Report MAE in years, per-age-band errors, sample counts, and CPU inference latency.
- Preserve the chosen weights, preprocessing settings, split seed, and evaluation report together.
- Evaluate camera/upload examples separately to identify differences from the prepared dataset images.
- If measured local training time is unsuitable, discuss a GPU training environment before changing the plan.

## Data handling

- Keep UTKFace local and excluded from Git.
- Process user inputs transiently; avoid image data in logs.
- No accounts, database, or saved prediction history in the proposed first version.


## Camera scan update

The camera waits 1.5 seconds for initial exposure/focus, then calls POST /api/scan before age inference. Scans return a normalized detected-face box for the mirrored, letterboxed preview overlay. Age remains empty during scanning.

Camera-only checks reject small faces (under 100 pixels or 16% of frame dimensions), low light (mean grayscale under 45), overexposure (over 220), and low sharpness (Laplacian variance under 35 after 160-pixel normalization). These are initial capture heuristics, not calibrated accuracy guarantees.

Three consecutive stable face boxes are required before collecting five quality-checked age estimates. Movement, lost/multiple faces, and quality errors clear accumulated samples. Estimates spanning more than eight years restart the scan; otherwise the median is displayed and the camera stops. Bounding-box stability is not identity recognition. One request is in flight at a time; Cancel, mode switching and Try Again reset the scan.

Camera requests use up to 1280-pixel-wide frames at JPEG quality 0.95. Uploaded-image preprocessing and the trained age model remain the same. No physical-webcam accuracy improvement has yet been measured.

## Fine-tuning and usability iteration

- Fine-tune the last MobileNet feature blocks and regression head on training data only, with mild horizontal flip, affine, light/color and blur augmentation. Keep early filters and batch-normalization statistics frozen.
- Run three epochs. Select using validation MAE; promote only if validation MAE improves by at least 0.1 years. Preserve baseline checkpoint and report in models/baseline/.
- Evaluate the selected candidate on the existing test split only after the promotion decision. This is not a newly collected external holdout, and cannot establish physical-camera accuracy.
- Add four camera indicators: measured lighting, face size and sharpness from Flask, plus frontend bounding-box stability. Show Waiting before measurements or after cancellation; do not present confidence percentages.
- Add a Goobo Labs dark theme. Default to the saved preference or operating-system preference; persist explicit selection locally. Camera images and age results are not persisted.
