import hashlib
import json

import pytest
from PIL import Image

from ml.face_detect import MODEL_PATH, MODEL_SHA256, create_detector, detect_faces, ensure_model
from ml.model import ROOT

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason='Face detector weights not downloaded')


def test_detector_weights_match_the_pinned_checksum():
    assert hashlib.sha256(ensure_model().read_bytes()).hexdigest() == MODEL_SHA256


def test_blank_image_yields_no_face():
    assert detect_faces(create_detector(), Image.new('RGB', (200, 200), 'white')) == []


@pytest.mark.skipif(not (ROOT / 'data' / 'processed' / 'test.json').exists(), reason='Build the dataset splits first')
def test_boxes_stay_inside_real_portraits():
    rows = json.loads((ROOT / 'data' / 'processed' / 'test.json').read_text())
    detector = create_detector()
    detected = 0
    for row in rows[:40]:
        with Image.open(ROOT / row['path']) as source:
            image = source.convert('RGB')
            for x, y, width, height in detect_faces(detector, image):
                detected += 1
                assert 0 <= x < x + width <= image.width
                assert 0 <= y < y + height <= image.height
    # Coverage on cropped portraits is near total; this only guards a silent detector failure.
    assert detected >= 30
