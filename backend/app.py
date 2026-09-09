import io
import logging
import threading
import warnings

import cv2
import numpy as np
import torch
from flask import Flask, Request, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

from ml.model import ROOT, load_model, preprocess

Image.MAX_IMAGE_PIXELS = 16_000_000


class MemoryRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        # Keep bounded uploads in memory instead of Werkzeug's temporary-file spool.
        return io.BytesIO()


class InputError(Exception):
    def __init__(self, code, message, status=422, face_box=None, quality=None):
        self.code, self.message, self.status, self.face_box = code, message, status, face_box
        self.quality = quality


class Predictor:
    def __init__(self, model_path=None):
        torch.set_num_threads(4)
        self.lock = threading.Lock()
        self.model = None
        self.model_path = model_path or ROOT / 'models' / 'age_model.pt'
        self.detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        if self.detector.empty():
            raise RuntimeError('Face detector could not be loaded.')
        self.transform = preprocess()
        if self.model_path.exists():
            self.model = load_model(self.model_path)

    @property
    def ready(self):
        return self.model is not None

    def analyze(self, image, camera=False, scan_only=False):
        if not self.ready:
            raise InputError('MODEL_NOT_READY', 'The age model is not ready yet. Finish training and restart the backend.', 503)
        # Bound detector work independently from the upload pixel limit.
        image.thumbnail((1280, 1280))
        with self.lock:
            gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
            faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            if len(faces) == 0:
                raise InputError('NO_FACE', 'No clear face found. Face forward and improve the lighting.')
            if len(faces) > 1:
                raise InputError('MULTIPLE_FACES', 'More than one face found. Keep only one face in the frame.')
            x, y, width, height = map(int, faces[0])
            box = {'x': x / image.width, 'y': y / image.height, 'width': width / image.width, 'height': height / image.height}
            quality = check_camera_quality(gray[y:y + height, x:x + width], box) if camera else None
            if scan_only:
                return {'face_box': box, 'ready': True, 'quality': quality}
            margin = int(max(width, height) * 0.15)
            face = image.crop((max(0, x - margin), max(0, y - margin), min(image.width, x + width + margin), min(image.height, y + height + margin)))
            with torch.inference_mode():
                age = self.model(self.transform(face).unsqueeze(0)).item()
        if not np.isfinite(age):
            raise RuntimeError('Non-finite model output')
        return {'estimated_age': round(max(0.0, min(120.0, age)), 1), 'face_box': box, 'quality': quality}

    def predict(self, image):
        return self.analyze(image)['estimated_age']


def check_camera_quality(face_gray, box):
    """Conservative capture heuristics, not a guarantee of model accuracy."""
    brightness = float(np.mean(face_gray))
    normalized = cv2.resize(face_gray, (160, 160))
    sharpness = float(cv2.Laplacian(normalized, cv2.CV_64F).var())
    small = min(face_gray.shape) < 100 or min(box['width'], box['height']) < 0.16
    quality = {
        'lighting': 'low' if brightness < 45 else 'harsh' if brightness > 220 else 'good',
        'face_size': 'too_small' if small else 'good',
        'sharpness': 'blurry' if sharpness < 35 else 'good',
    }
    if small:
        raise InputError('FACE_TOO_SMALL', 'Move closer so your face fills more of the frame.', face_box=box, quality=quality)
    if brightness < 45:
        raise InputError('LOW_LIGHT', 'Add light in front of your face.', face_box=box, quality=quality)
    if brightness > 220:
        raise InputError('OVEREXPOSED', 'Move away from harsh light so facial details are visible.', face_box=box, quality=quality)
    if sharpness < 35:
        raise InputError('BLURRY_FACE', 'Hold still and let the camera focus on your face.', face_box=box, quality=quality)
    return quality


def decode_image(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise InputError('INVALID_IMAGE', 'Choose a JPG, PNG or WebP image.', 400)
                if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                    raise InputError('IMAGE_TOO_LARGE', 'Choose an image under 16 megapixels.', 413)
                source.load()
                return ImageOps.exif_transpose(source).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InputError('INVALID_IMAGE', 'The image cannot be read. Choose a valid image under 16 megapixels.', 400) from None


def create_app(predictor=None):
    app = Flask(__name__)
    app.request_class = MemoryRequest
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 + 64 * 1024
    service = predictor if predictor is not None else Predictor()

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(InputError)
    def input_error(error):
        return jsonify(error={'code': error.code, 'message': error.message}, face_box=error.face_box, quality=error.quality), error.status

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        return jsonify(error={'code': 'IMAGE_TOO_LARGE', 'message': 'Choose an image under 8 MB.'}), 413

    @app.get('/api/health')
    def health():
        return jsonify(status='ready' if service.ready else 'model_not_ready', model_ready=service.ready), 200 if service.ready else 503

    @app.post('/api/scan')
    @app.post('/api/predict')
    def predict():
        upload = request.files.get('image')
        if upload is None:
            raise InputError('MISSING_IMAGE', 'Choose an image first.', 400)
        raw = upload.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise RequestEntityTooLarge()
        image = decode_image(raw)
        try:
            if request.path == '/api/scan' or request.form.get('source') == 'camera':
                result = service.analyze(image, camera=True, scan_only=request.path == '/api/scan')
                if request.path == '/api/scan':
                    return jsonify(result)
                return jsonify(**result, unit='years', is_estimate=True)
            age = service.predict(image)
        except InputError:
            raise
        except Exception:
            logging.exception('Age inference failed')
            return jsonify(error={'code': 'INFERENCE_FAILED', 'message': 'Analysis failed. Please try again.'}), 500
        return jsonify(estimated_age=age, unit='years', is_estimate=True)

    return app


if __name__ == '__main__':
    from waitress import serve
    serve(create_app(), host='127.0.0.1', port=5000, threads=2)
