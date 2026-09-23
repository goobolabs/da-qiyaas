import json

import pytest
from PIL import Image

from backend.app import Predictor, create_app
from ml.face_crop import crop_face
from ml.improve import eligible
from ml.model import ROOT


def test_crop_keeps_margin_inside_image():
    image = Image.new('RGB', (200, 160))
    assert crop_face(image, (0, 0, 100, 100)).size == (115, 115)
    assert crop_face(image, (100, 80, 100, 80)).size == (115, 95)


def test_validation_gate_rejects_overall_or_age_band_regressions():
    def scores(full, crop, band):
        return {view: {'mae_years': value, 'age_bands': {'60-79': {'count': 20, 'mae': band}}}
                for view, value in [('full', full), ('crop', crop)]}
    baseline = scores(7, 8, 10)
    assert eligible(scores(6, 7, 9), baseline)
    assert eligible(scores(7, 7.9, 11), baseline)
    assert not eligible(scores(7.1, 7, 9), baseline)
    assert not eligible(scores(6, 7.95, 9), baseline)
    assert not eligible(scores(6, 7, 11.1), baseline)


@pytest.mark.skipif(not (ROOT / 'models/age_model.pt').exists(), reason='Train the model first')
def test_distinct_age_uploads_do_not_return_a_constant():
    client = create_app(Predictor()).test_client()
    rows = json.loads((ROOT / 'data/processed/validation.json').read_text())
    predictions = []
    for low, high in [(0, 12), (20, 39), (60, 120)]:
        for row in [r for r in rows if low <= r['age'] <= high][:40]:
            with (ROOT / row['path']).open('rb') as source:
                result = client.post('/api/predict', data={'image': (source, 'portrait.jpg')})
            if result.status_code == 200:
                predictions.append(result.json['estimated_age'])
                break
        else:
            pytest.fail(f'No detectable portrait for age band {low}-{high}')
    # This checks the real image-to-response path, not individual age accuracy.
    assert max(predictions) - min(predictions) > 10
