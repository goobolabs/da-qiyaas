# Requirements

Status: version 1 implemented after the user authorized implementation on 2026-09-09.

## Confirmed

- Follow Spec-Driven Development: requirements, technical plan, tasks, implementation, verification.
- Frontend: Next.js 15. Backend: Flask.
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
- Do not persist camera frames or uploaded images, or add them to training data.
- Handle denied camera access, invalid images, and failed predictions with retry guidance.
- Release camera access after a successful prediction or when leaving camera mode.
- First version runs locally without accounts or prediction history.

## Acceptance criteria

- Opening the camera with permission starts analysis automatically.
- A valid single-face input produces a visible estimated age for both input modes.
- After camera success, prediction requests stop and the result remains stable until a new attempt.
- Try again clears the previous result and restarts camera analysis.
- Invalid input does not produce a fabricated age.
- The backend uses the same model and preprocessing for both modes.

## Implementation decisions and remaining evaluation

- Model: frozen MobileNetV3 Small with regression head; OpenCV 4 Haar frontal-face detector; CPU training.
- Baseline test MAE is 7.70 years. No guaranteed accuracy target; physical-camera accuracy remains unmeasured.
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
