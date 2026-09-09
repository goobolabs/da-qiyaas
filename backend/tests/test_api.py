import io

import pytest
from PIL import Image

from backend.app import create_app, InputError, Predictor


class FakePredictor:
    ready = True

    def predict(self, image):
        assert image.mode == 'RGB'
        return 32.5


@pytest.fixture
def client():
    return create_app(FakePredictor()).test_client()


def portrait():
    stream = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(stream, 'PNG')
    stream.seek(0)
    return stream


def test_valid_upload(client):
    response = client.post('/api/predict', data={'image': (portrait(), 'test.png')})
    assert response.status_code == 200
    assert response.json == {'estimated_age': 32.5, 'unit': 'years', 'is_estimate': True}
    assert response.headers['Cache-Control'] == 'no-store'


def test_missing_image(client):
    assert client.post('/api/predict').json['error']['code'] == 'MISSING_IMAGE'


def test_invalid_image(client):
    response = client.post('/api/predict', data={'image': (io.BytesIO(b'not an image'), 'test.jpg')})
    assert response.status_code == 400


def test_oversized_upload(client):
    response = client.post('/api/predict', data={'image': (io.BytesIO(b'x' * (8 * 1024 * 1024 + 1)), 'test.jpg')})
    assert response.status_code == 413


@pytest.mark.parametrize('code', ['NO_FACE', 'MULTIPLE_FACES'])
def test_face_errors(code):
    class FaceError(FakePredictor):
        def predict(self, image):
            raise InputError(code, 'Please use one clear face.')
    response = create_app(FaceError()).test_client().post('/api/predict', data={'image': (portrait(), 'test.png')})
    assert response.status_code == 422
    assert response.json['error']['code'] == code


def test_missing_model_does_not_fabricate_age(tmp_path):
    client = create_app(Predictor(tmp_path / 'missing.pt')).test_client()
    assert client.get('/api/health').status_code == 503
    response = client.post('/api/predict', data={'image': (portrait(), 'test.png')})
    assert response.status_code == 503
    assert 'estimated_age' not in response.json
