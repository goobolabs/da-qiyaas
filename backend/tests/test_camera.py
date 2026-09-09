import io

import numpy as np
import pytest
from PIL import Image

from backend.app import InputError, check_camera_quality, create_app


BOX = {'x': .2, 'y': .2, 'width': .4, 'height': .4}


@pytest.mark.parametrize('pixels,code', [
    (np.full((80, 80), 120, dtype=np.uint8), 'FACE_TOO_SMALL'),
    (np.full((160, 160), 20, dtype=np.uint8), 'LOW_LIGHT'),
    (np.full((160, 160), 240, dtype=np.uint8), 'OVEREXPOSED'),
    (np.full((160, 160), 120, dtype=np.uint8), 'BLURRY_FACE'),
])
def test_camera_rejects_poor_capture(pixels, code):
    with pytest.raises(InputError) as error:
        check_camera_quality(pixels, BOX)
    assert error.value.code == code
    assert error.value.face_box == BOX
    assert set(error.value.quality) == {'lighting', 'face_size', 'sharpness'}


def test_quality_reports_good_for_a_bright_sharp_large_capture():
    pixels = np.random.default_rng(1).integers(60, 200, (160, 160), dtype=np.uint8)
    assert check_camera_quality(pixels, BOX) == {'lighting': 'good', 'face_size': 'good', 'sharpness': 'good'}


def test_scan_returns_box_without_age_and_camera_requests_quality_checks():
    class Service:
        ready = True

        def analyze(self, image, camera=False, scan_only=False):
            assert camera is True
            return {'face_box': BOX, 'ready': True} if scan_only else {'face_box': BOX, 'estimated_age': 30}

    client = create_app(Service()).test_client()
    def payload():
        stream = io.BytesIO()
        Image.new('RGB', (200, 200), 'gray').save(stream, 'PNG')
        stream.seek(0)
        return {'image': (stream, 'frame.png'), 'source': 'camera'}
    response = client.post('/api/scan', data=payload())
    assert response.status_code == 200
    assert 'estimated_age' not in response.json
    assert response.json['face_box'] == BOX
    response = client.post('/api/predict', data=payload())
    assert response.json['estimated_age'] == 30
