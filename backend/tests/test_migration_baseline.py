"""Guard the reference recorder and freeze Python behavior for the Rust port."""
import json
from pathlib import Path

import numpy as np
import pytest

from ml.migration_baseline import (manifest_rows, select_fixtures, sha256,
                                   synthetic_fixtures, verify, write_json)
from ml.migration_contracts import capture_contracts
from ml.model import ROOT


def test_http_contracts_match_reviewed_reference():
    expected = json.loads((ROOT / 'docs/migration/python-api-contracts.json').read_text(encoding='utf-8'))
    actual = capture_contracts()
    assert actual == expected
    assert {case['route'] for case in actual['cases']} == {
        '/api/health', '/api/predict', '/api/scan', '/api/speech', '/api/feedback', '/api/feedback/summary'}


def test_synthetic_orientation_crop_normalization_and_quality_boundaries(tmp_path):
    directory = tmp_path / 'synthetic'
    fixtures = synthetic_fixtures(directory)
    rgb = np.load(directory / fixtures['rgb_png']['decoded']['file'], allow_pickle=False)
    exif = np.load(directory / fixtures['exif_6']['decoded']['file'], allow_pickle=False)
    assert rgb.shape == (119, 173, 3)
    assert exif.shape == (173, 119, 3)
    alpha = np.load(directory / fixtures['alpha']['decoded']['file'], allow_pickle=False)
    np.testing.assert_array_equal(alpha, rgb)  # PIL drops alpha rather than compositing.
    for name in ('rgb_png', 'grayscale', 'alpha', 'thumbnail', 'exif_6'):
        tensor = np.load(directory / fixtures[name]['tensor']['file'], allow_pickle=False)
        assert tensor.shape == (3, 160, 160) and tensor.dtype == np.float32
        assert np.isfinite(tensor).all()
        assert -2.2 < tensor.min() <= tensor.max() < 2.7
    quality = fixtures['quality']
    assert quality['quality_99_45']['error']['code'] == 'FACE_TOO_SMALL'
    assert quality['quality_100_45']['error'] is None
    assert quality['quality_160_44']['error']['code'] == 'LOW_LIGHT'
    assert quality['quality_160_220']['error'] is None
    assert quality['quality_160_221']['error']['code'] == 'OVEREXPOSED'
    assert quality['quality_fraction_0.159']['error']['code'] == 'FACE_TOO_SMALL'
    assert quality['quality_fraction_0.16']['error']['code'] == 'BLURRY_FACE'
    assert quality['quality_sharpness_34.99']['error']['code'] == 'BLURRY_FACE'
    assert quality['quality_sharpness_35.01']['error'] is None
    assert fixtures['malformed']['status'] == 400
    assert fixtures['truncated']['status'] == 400
    assert fixtures['unsupported_bmp']['error'] == 'INVALID_IMAGE'
    # Preserve the actual Pillow decompression-bomb warning mapping, not the intended 413.
    assert fixtures['pixel_limit'] == {'error': 'INVALID_IMAGE', 'status': 400}
    rounding = {row['raw_age']: row for row in fixtures['rounding']}
    assert rounding[24.25]['api_age'] == 24.2
    assert rounding[24.5]['displayed_age'] == 25
    assert rounding[-1.]['api_age'] == 0
    assert rounding[121.]['api_age'] == 120


def test_manifest_selection_ignores_test_and_rejects_duplicates(tmp_path):
    directory = tmp_path / 'data/processed'
    directory.mkdir(parents=True)
    for name, value in [('train', 'b'), ('validation', 'a'), ('test', 'c')]:
        write_json(directory / f'{name}.json', [{'age': 25, 'hash': value, 'path': 'unused.jpg'}])
    splits = manifest_rows(tmp_path)
    assert [name for name, _ in select_fixtures(splits)] == ['train', 'validation']
    write_json(directory / 'test.json', splits['train'])
    with pytest.raises(ValueError, match='Duplicate'):
        manifest_rows(tmp_path)


def completed_reference(directory):
    content = directory / 'snapshot.txt'
    content.write_text('original reference', encoding='utf-8')
    write_json(directory / 'inventory.json', {'snapshot.txt': sha256(content)})
    write_json(directory / 'complete.json', {'inventory_sha256': sha256(directory / 'inventory.json')})


@pytest.mark.parametrize('damage', ['modified', 'missing', 'extra', 'inventory', 'incomplete'])
def test_verify_rejects_tampering_and_partial_captures(tmp_path, damage):
    completed_reference(tmp_path)
    assert verify(tmp_path) == 1
    if damage == 'modified':
        (tmp_path / 'snapshot.txt').write_text('changed', encoding='utf-8')
    elif damage == 'missing':
        (tmp_path / 'snapshot.txt').unlink()
    elif damage == 'extra':
        (tmp_path / 'extra.txt').write_text('untracked', encoding='utf-8')
    elif damage == 'inventory':
        write_json(tmp_path / 'inventory.json', {})
    else:
        (tmp_path / 'complete.json').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(tmp_path)
