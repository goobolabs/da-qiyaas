import io
import json

import pytest
import torch
from PIL import Image

from backend.app import Predictor, create_app
from ml.model import AgeModel, IMAGE_SIZE, ROOT, load_model, preprocess


@pytest.mark.parametrize('backbone', ['small', 'large'])
def test_checkpoint_architecture_round_trip(tmp_path, backbone):
    torch.set_num_threads(2)
    original = AgeModel(backbone=backbone).eval()
    path = tmp_path / 'model.pt'
    torch.save({'state_dict': original.state_dict(), 'image_size': IMAGE_SIZE,
                'architecture': f'mobilenet_v3_{backbone}_balanced_crops'}, path)
    restored = load_model(path)
    sample = torch.randn(2, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.inference_mode():
        expected, actual = original(sample), restored(sample)
    assert restored.backbone == backbone
    assert actual.shape == (2,)
    assert torch.isfinite(actual).all()
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)


def test_checkpoint_rejects_unknown_architecture(tmp_path):
    path = tmp_path / 'unknown.pt'
    torch.save({'image_size': IMAGE_SIZE, 'architecture': 'unsupported'}, path)
    with pytest.raises(ValueError, match='Unsupported checkpoint architecture'):
        load_model(path)


@pytest.mark.skipif(not (ROOT / 'models' / 'age_model.pt').exists(), reason='Run training first')
def test_trained_model_and_real_face_pipeline():
    service = Predictor()
    client = create_app(service).test_client()
    assert client.get('/api/health').json['model_ready'] is True
    blank = io.BytesIO()
    Image.new('RGB', (200, 200), 'white').save(blank, 'PNG')
    blank.seek(0)
    response = client.post('/api/predict', data={'image': (blank, 'blank.png')})
    assert response.status_code == 422
    assert response.json['error']['code'] == 'NO_FACE'
    rows = json.loads((ROOT / 'data' / 'processed' / 'test.json').read_text())
    # Exercise real detector + real model; no mocked numerical output.
    for row in rows[:30]:
        with (ROOT / row['path']).open('rb') as source:
            response = client.post('/api/predict', data={'image': (source, 'portrait.jpg')})
        if response.status_code == 200:
            assert 0 <= response.json['estimated_age'] <= 120
            with (ROOT / row['path']).open('rb') as source:
                scanned = client.post('/api/scan', data={'image': (source, 'portrait.jpg')})
            assert scanned.status_code in (200, 422)
            assert 'estimated_age' not in scanned.json
            assert set(scanned.json['quality']) == {'lighting', 'face_size', 'sharpness'}
            assert 0 <= scanned.json['face_box']['x'] <= 1
            break
    else:
        pytest.fail('The face pipeline did not detect any of the first 30 test portraits')


@pytest.mark.skipif(not (ROOT / 'models' / 'age_model.pt').exists(), reason='Run training first')
def test_checkpoint_reload_is_deterministic():
    model = load_model(ROOT / 'models' / 'age_model.pt')
    sample = preprocess()(Image.new('RGB', (160, 160), 'gray')).unsqueeze(0)
    with torch.inference_mode():
        first, second = model(sample), model(sample)
    assert torch.isfinite(first).all()
    assert torch.equal(first, second)
