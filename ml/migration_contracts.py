"""Capture HTTP contracts offline, using synthetic inputs and isolated storage."""
import io
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import backend.app as api
import backend.speech as speech


@contextmanager
def close_test_connections():
    """sqlite's transaction context does not close handles; release them on Windows."""
    connect = sqlite3.connect
    connections = []

    def tracked(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    try:
        with patch('backend.feedback.sqlite3.connect', side_effect=tracked):
            yield
    finally:
        for connection in connections:
            connection.close()


def png_bytes():
    output = io.BytesIO()
    Image.new('RGB', (160, 160), (80, 120, 160)).save(output, 'PNG')
    return output.getvalue()


class ContractPredictor:
    """Only numerical inference is scripted; real routes/decoding/storage execute."""
    ready = True
    error = None

    def predict(self, image):
        return self.analyze(image)['estimated_age']

    def analyze(self, image, camera=False, scan_only=False):
        if self.error:
            raise self.error
        if not self.ready:
            raise api.InputError('MODEL_NOT_READY', 'The age model is not ready yet. Finish training and restart the backend.', 503)
        assert image.mode == 'RGB'
        result = {'face_box': {'x': 0.1, 'y': 0.2, 'width': 0.5, 'height': 0.5},
                  'quality': {'lighting': 'good', 'face_size': 'good', 'sharpness': 'good'}}
        result['ready' if scan_only else 'estimated_age'] = True if scan_only else 32.5
        return result


def capture_contracts():
    records = []
    predictor = ContractPredictor()
    raw = png_bytes()

    def record(name, client, method, route, **kwargs):
        response = getattr(client, method)(route, **kwargs)
        body = response.get_json() if response.is_json else {'bytes_hex': response.data.hex()}
        records.append({'name': name, 'method': method.upper(), 'route': route,
                        'status': response.status_code, 'body': body,
                        'headers': {key: response.headers.get(key) for key in
                                    ('Content-Type', 'Cache-Control', 'X-Content-Type-Options')}})

    def upload(data=raw, **fields):
        return dict(image=(io.BytesIO(data), 'synthetic.png'), **fields)

    with tempfile.TemporaryDirectory(prefix='age-contracts-') as directory, close_test_connections():
        root = Path(directory)
        clips = root / 'clips'
        clips.mkdir()
        with (patch.object(api, 'ROOT', root), patch.object(speech, 'CLIP_DIR', clips),
              patch.dict(os.environ, {'AZURE_SPEECH_KEY': '', 'AZURE_SPEECH_REGION': ''}),
              patch.object(speech, 'urlopen', side_effect=AssertionError('Contracts must stay offline'))):
            app = api.create_app(predictor)
            client = app.test_client()
            record('health.ready', client, 'get', '/api/health')
            record('predict.upload', client, 'post', '/api/predict', data=upload())
            record('predict.camera', client, 'post', '/api/predict', data=upload(source='camera'))
            record('scan.ready', client, 'post', '/api/scan', data=upload())
            for route in ('predict', 'scan'):
                record(f'{route}.missing', client, 'post', f'/api/{route}')
                record(f'{route}.invalid', client, 'post', f'/api/{route}', data=upload(b'not an image'))
                record(f'{route}.image_limit', client, 'post', f'/api/{route}', data=upload(b'x' * (8 * 1024 * 1024 + 1)))
                record(f'{route}.request_limit', client, 'post', f'/api/{route}', data=b'x' * (8 * 1024 * 1024 + 65537), content_type='multipart/form-data; boundary=test')
            predictor.ready = False
            record('health.unready', client, 'get', '/api/health')
            record('predict.unready', client, 'post', '/api/predict', data=upload())
            record('scan.unready', client, 'post', '/api/scan', data=upload())
            predictor.ready = True
            for code in ('NO_FACE', 'MULTIPLE_FACES', 'FACE_TOO_SMALL', 'LOW_LIGHT', 'OVEREXPOSED', 'BLURRY_FACE'):
                # Message here is explicitly synthetic; processing fixtures capture real messages.
                predictor.error = api.InputError(code, 'Synthetic contract error.')
                record(f'predict.{code}', client, 'post', '/api/predict', data=upload(source='camera'))
            predictor.error = RuntimeError('synthetic failure')
            with patch.object(api.logging, 'exception'):
                record('predict.failure', client, 'post', '/api/predict', data=upload())
            predictor.error = None

            record('speech.unavailable', client, 'get', '/api/speech')
            record('speech.unconfigured', client, 'post', '/api/speech', json={'age': 24})
            for value in (-1, 121, True, 24.5, '24', None):
                record(f'speech.invalid.{json.dumps(value)}', client, 'post', '/api/speech', json={'age': value})
            (clips / '24.mp3').write_bytes(b'\xff\xf3synthetic-audio')
            record('speech.local_availability', client, 'get', '/api/speech')
            record('speech.local_audio', client, 'post', '/api/speech', json={'age': 24})
            record('speech.missing_clip', client, 'post', '/api/speech', json={'age': 25})

            record('feedback.empty_summary', client, 'get', '/api/feedback/summary')
            assert not (root / 'data').exists(), 'Prediction/summary must not create storage.'
            feedback = {'submission_id': '00000000-0000-4000-8000-000000000001',
                        'estimated_age': 32, 'actual_age': 30, 'source': 'upload', 'consent': True}
            for name, payload in [('missing', {}), ('no_consent', dict(feedback, consent=False)),
                                  ('unknown_field', dict(feedback, extra=True)),
                                  ('fractional_age', dict(feedback, actual_age=30.5)),
                                  ('training_without_photo', dict(feedback, training_consent=True))]:
                record('feedback.' + name, client, 'post', '/api/feedback', json=payload)
            record('feedback.numeric', client, 'post', '/api/feedback', json=feedback)
            record('feedback.retry', client, 'post', '/api/feedback', json=feedback)
            record('feedback.conflict', client, 'post', '/api/feedback', json=dict(feedback, actual_age=31))
            photo_feedback = dict(feedback, submission_id='00000000-0000-4000-8000-000000000002', source='camera')
            record('feedback.photo_no_consent', client, 'post', '/api/feedback', data=upload(metadata=json.dumps(photo_feedback)))
            photo_feedback['training_consent'] = True
            record('feedback.photo', client, 'post', '/api/feedback', data=upload(metadata=json.dumps(photo_feedback)))
            record('feedback.photo_retry', client, 'post', '/api/feedback', data=upload(metadata=json.dumps(photo_feedback)))
            record('feedback.summary', client, 'get', '/api/feedback/summary')
            with sqlite3.connect(root / 'data/feedback.sqlite3') as database:
                assert database.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] == 2
                assert database.execute('SELECT consent_version, review_status FROM training_contributions').fetchall() == [('training-photo-v1', 'pending')]
            with patch('backend.feedback.sqlite3.connect', side_effect=sqlite3.OperationalError('synthetic')):
                record('feedback.storage_failure', client, 'post', '/api/feedback', json=feedback)
                record('feedback.summary_failure', client, 'get', '/api/feedback/summary')

            with patch.dict(os.environ, {'AZURE_SPEECH_KEY': 'synthetic', 'AZURE_SPEECH_REGION': 'eastus'}):
                azure_client = api.create_app(predictor).test_client()
                record('speech.local_priority', azure_client, 'post', '/api/speech', json={'age': 24})
                (clips / '24.mp3').unlink()
                record('speech.azure_availability', azure_client, 'get', '/api/speech')
                with patch.object(speech, 'urlopen', return_value=io.BytesIO(b'synthetic-provider-audio')) as upstream:
                    record('speech.azure_audio', azure_client, 'post', '/api/speech', json={'age': 25})
                    record('speech.azure_cached', azure_client, 'post', '/api/speech', json={'age': 25})
                    assert upstream.call_count == 1
                with patch.object(speech, 'urlopen', side_effect=OSError('synthetic provider failure')):
                    record('speech.azure_failure', azure_client, 'post', '/api/speech', json={'age': 26})
    return {'schema_version': 1, 'description': 'Real Flask handlers with scripted inference, temporary SQLite and synthetic/offline audio; no real user data or provider calls.', 'cases': records}
