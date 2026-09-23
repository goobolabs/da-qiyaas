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

## MobileNetV3 Large comparison

- Start Large from torchvision ImageNet V2 weights; retain 160-pixel input and shared runtime face crops.
- Warm the regression head for up to 60 epochs on frozen full/crop training embeddings, using crop validation for early stopping.
- Fine-tune feature blocks 10 onward for six epochs with mixed portrait/crop augmentation and mild age-balanced sampling. Keep batch-normalization statistics frozen.
- Compare against the preserved active Small model on the same full and detected-face validation subsets, with the acceptance gates above.
- Select the lowest crop-MAE eligible checkpoint, or report the lowest crop-MAE candidate as rejected if no epoch passes. Evaluate the existing test split only after selection.
- Measure warmed single-image CPU latency for both models in alternating order on four threads; report the accuracy/speed tradeoff.
- Preserve all run artifacts under a unique local `models/large-*/` directory. Promotion is opt-in via `--promote` and checks that the active checkpoint has not changed during training.
- A single training run does not establish the best possible Large configuration or physical-webcam accuracy.

## YuNet face detector

- Replace the Haar cascade with OpenCV Zoo YuNet for training, evaluation and serving, behind one shared module.
- Pin the detector weights by SHA-256, fetch them into the local pretrained folder on first use, and never commit them.
- Keep the 15 percent crop margin unless a validation margin sweep shows a better value.
- Include the detector identity in the cached face-box key so boxes from an older detector are rebuilt, not reused.
- Decide on validation only: same-image crop MAE must improve by at least 0.1 years with no age-band regression above 1 year.
- Evaluate the existing test split after the decision, and report single-face coverage separately from error.
- Change no model weights. This is a preprocessing change, so the promoted checkpoint stays as it is.
- Higher coverage on already-cropped UTKFace portraits does not establish the same gain on live camera frames.
