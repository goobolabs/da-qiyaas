"""Shared YuNet face detection for training, evaluation and serving."""
import hashlib
import urllib.request

import cv2
import numpy as np

from ml.model import ROOT

# OpenCV Zoo release asset; the checksum pins the exact published weights.
MODEL_URL = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
MODEL_SHA256 = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
MODEL_PATH = ROOT / 'models' / 'pretrained' / 'face_detection_yunet_2023mar.onnx'
# Bump when detection changes, so cached boxes from an older detector are rebuilt.
DETECTOR_ID = 'yunet_2023mar_score70'
SCORE_THRESHOLD = .7
NMS_THRESHOLD = .3


def ensure_model():
    if MODEL_PATH.exists() and hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256:
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MODEL_URL, timeout=120) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MODEL_SHA256:
        raise RuntimeError(f'Face detector checksum mismatch: expected {MODEL_SHA256}, got {digest}.')
    MODEL_PATH.write_bytes(data)
    return MODEL_PATH


def create_detector():
    """One detector per thread; FaceDetectorYN is not safe to share concurrently."""
    return cv2.FaceDetectorYN.create(str(ensure_model()), '', (320, 320), SCORE_THRESHOLD, NMS_THRESHOLD, 5000)


def detect_faces(detector, image):
    """Return integer (x, y, width, height) boxes clamped to an RGB PIL image."""
    detector.setInputSize((image.width, image.height))
    _, found = detector.detect(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
    if found is None:
        return []
    boxes = []
    for x, y, width, height in found[:, :4]:
        left, top = max(0, int(x)), max(0, int(y))
        boxes.append((left, top, min(int(width), image.width - left), min(int(height), image.height - top)))
    return [box for box in boxes if box[2] > 0 and box[3] > 0]
