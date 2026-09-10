# Age prediction improvement

## Problem and diagnosis

The user reports repeated estimates around 23. A deterministic validation audit across six age bands found predictions from 2.5 to 97 years; no constant-output failure was reproduced. Errors are much larger for older ages. Runtime detects/crops faces, whereas the previous training and published evaluation used entire UTKFace portraits.

## Plan and acceptance

- Preserve the deployed checkpoint and metrics before training.
- Keep existing deduplicated splits; never train on validation, test, or the owner's demo portrait.
- Train from the deployed weights with mild age-balanced sampling, full-portrait/face-crop augmentation and more trainable feature blocks.
- Measure full validation MAE and runtime-crop validation MAE on identical images before/after. Report detector coverage separately.
- Choose a checkpoint using validation only: crop MAE must improve by at least 0.1 years and full-image MAE must not worsen. Reject candidates whose validation age-band MAE worsens by more than 1 year on either view.
- Evaluate the existing test split only after selection. This reused split is not an external holdout or evidence of webcam accuracy.
- Compare diverse real API uploads and ensure the UI updates per image, including repeated rounded ages.
- Keep model weights and dataset local, update portable metrics and documentation, restart the backend to load the selected model.
