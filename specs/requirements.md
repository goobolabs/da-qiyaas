# Requirements

Status: the Python application is implemented. Rust migration implementation was authorized on 2026-09-25, one issue and tested PR at a time. See [Rust migration](rust-migration.md) for the target and acceptance gates.

## Confirmed

- Follow Spec-Driven Development: requirements, technical plan, tasks, implementation, verification.
- Frontend: Next.js 15. Backend: Python/Flask, retained as explicitly confirmed by the user. Proposed image processing, inference and model training: Rust, called from Python through a native extension; details in [Rust migration](rust-migration.md).
- All user-facing UI text must be in English, including buttons, instructions, results, and error messages.
- Support camera input and image upload.
- After camera permission is granted, automatically analyze the face without a capture button.
- Display one estimated age and stop analysis after success. A Try again action starts a new attempt.
- Uploaded images use the same face analysis and age estimation pipeline.
- Display estimated age in years, not a verified age.
- Use the local UTKFace dataset for training and evaluation.

## Observed environment

- Dataset: 23,708 JPG files, 114.43 MB, all with numeric age prefixes from 1 to 116; zero empty files.
- All source images decoded. Audit found 390 duplicate copies and 205 contradictory-age groups. Deduplication and conflict exclusion leave 23,113 unique usable images. Label correctness beyond filename parsing remains unverified.
- CPU: Intel Core i7-10610U, 4 cores / 8 threads.
- RAM: 31.8 GB. Graphics: Intel UHD Graphics; no NVIDIA GPU detected.
- Free space on C: approximately 392.7 GB when inspected.

## Version 1 defaults

- One face per prediction. Explain no-face and multiple-face cases clearly.
- Prediction inputs are transient. The later, separately consented training-contribution flow may persist a photo and self-reported age for review; collection never automatically adds it to training.
- Handle denied camera access, invalid images, and failed predictions with retry guidance.
- Release camera access after a successful prediction or when leaving camera mode.
- The app runs locally without accounts or prediction history. Explicitly submitted feedback and optional training contributions use the existing local SQLite database.

## Acceptance criteria

- Opening the camera with permission starts analysis automatically.
- A valid single-face input produces a visible estimated age for both input modes.
- After camera success, prediction requests stop and the result remains stable until a new attempt.
- Try again clears the previous result and restarts camera analysis.
- Invalid input does not produce a fabricated age.
- The backend uses the same model and preprocessing for both modes.

## Implementation decisions and remaining evaluation

- Original baseline: frozen MobileNetV3 Small and Haar detection. The latest recorded active model is MobileNetV3 Large with a regression head; serving uses shared OpenCV YuNet detection and a 15 percent crop margin. Migration must verify the active artifact before conversion.
- Original baseline test MAE was 7.70 years. The recorded Large model has 5.687 years full-portrait test MAE; the subsequent YuNet pipeline has 5.681 years crop MAE on 3,465 detected test faces. These are different evaluation views. See `docs/model-large-comparison.json` and `docs/model-detector-comparison.json`. Physical-camera accuracy remains unmeasured.
- Responsive English UI following the Goobo Labs brand: mint #3ACC69, black text, Space Grotesk headings, Manrope body text, official logo, camera/upload controls and a stable result card.
- Manual physical-webcam validation remains for the user; automated tests use a synthetic video stream.



## Camera acceptance criteria — scan update

- Show a scan box aligned with the detected face, accounting for mirrored video and letterboxing.
- Display no age until a stable, quality-checked multi-frame scan completes.
- Give actionable guidance for distant, dark, overexposed or blurry faces.
- Reset the scan when the face moves significantly, disappears, or multiple faces appear.
- Show the median of five sufficiently consistent estimates, then release camera access.
- Cancel, retry and mode changes clear all prior scan state.
- Preserve upload behavior; do not claim the scan guarantees a correct age.

## Fine-tuning and usability acceptance criteria

- Keep a restorable copy of the baseline before fine-tuning.
- Select a model using validation data, without changing selection based on test results.
- Camera indicators reflect returned quality states and clear on cancellation/retry.
- Dark/light toggle persists across reloads and preserves mobile layout.
- Validate existing camera scanning and uploaded-image prediction after changes.

## Rust migration requirements — proposed 2026-09-25

- Move image processing, age inference, dataset preparation, training, fine-tuning and evaluation into Rust. Keep Python/Flask for HTTP APIs, application logic, speech and feedback/database operations.
- Use Rust with `tch`/LibTorch as the proposed ML stack, subject to Windows build, checkpoint and training compatibility gates. Native C++ dependencies are allowed; a fully Rust dependency stack is not assumed.
- Python remains a runtime dependency for the backend. Flask calls a Rust extension for processing/inference; a standalone Rust CLI performs training without invoking Python. A documented, one-time checkpoint conversion may use the existing Python environment.
- Preserve the trained model, original dataset, split manifests, feedback database, consent rules, English interface and Somali speech behavior.
- Validate numerical equivalence before changing training recipes. Measure CPU latency, memory and training throughput; do not promise an accuracy or speed gain from the language change.
- Implement migration issues individually and run relevant automated and integration checks before opening each PR, as requested by the user. The detailed acceptance criteria in [Rust migration](rust-migration.md) govern this work; previous completed milestones remain historical evidence.
