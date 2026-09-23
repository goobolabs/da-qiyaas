from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import backend.speech as speech
from backend.speech import CLIP_DIR, clip_path, speech_blueprint


def client(monkeypatch, tmp_path, configured=True, clips=()):
    """Isolate the clip directory so tests never depend on locally generated audio."""
    monkeypatch.setattr(speech, 'CLIP_DIR', tmp_path)
    monkeypatch.setenv('AZURE_SPEECH_KEY', 'test-key' if configured else '')
    monkeypatch.setenv('AZURE_SPEECH_REGION', 'eastus')
    for age, data in clips:
        (tmp_path / f'{age}.mp3').write_bytes(data)
    app = Flask(__name__)
    app.register_blueprint(speech_blueprint())
    return app.test_client()


@pytest.mark.parametrize('age', [-1, 121, 24.5, True, '24', None])
def test_rejects_invalid_age(monkeypatch, tmp_path, age):
    with patch('backend.speech.urlopen') as upstream:
        assert client(monkeypatch, tmp_path).post('/api/speech', json={'age': age}).status_code == 400
        upstream.assert_not_called()


def test_no_clips_and_no_credentials(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path, False)
    assert api.get('/api/speech').json == {'available': False, 'language': 'so-SO', 'source': 'none', 'clips': 0}
    assert api.post('/api/speech', json={'age': 24}).status_code == 503


def test_local_clip_is_served_without_credentials(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path, False, clips=[(24, b'\xff\xf3local-mp3')])
    with patch('backend.speech.urlopen') as upstream:
        result = api.post('/api/speech', json={'age': 24})
        assert result.status_code == 200
        assert result.mimetype == 'audio/mpeg'
        assert result.data == b'\xff\xf3local-mp3'
        # A missing age still falls through to the unconfigured response.
        assert api.post('/api/speech', json={'age': 25}).status_code == 503
        upstream.assert_not_called()
    availability = api.get('/api/speech').json
    assert availability['available'] is True and availability['source'] == 'local' and availability['clips'] == 1


def test_local_clip_wins_over_configured_azure(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path, True, clips=[(24, b'\xff\xf3local-mp3')])
    with patch('backend.speech.urlopen') as upstream:
        assert api.post('/api/speech', json={'age': 24}).data == b'\xff\xf3local-mp3'
        upstream.assert_not_called()


def test_oversized_clip_does_not_bypass_the_size_limit(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path, False, clips=[(24, b'x' * (speech.MAX_CLIP_BYTES + 1))])
    assert api.post('/api/speech', json={'age': 24}).status_code == 503


def test_fixed_sentence_cache_and_private_key(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'fake-mp3'
    with patch('backend.speech.urlopen', return_value=response) as upstream:
        for _ in range(2):
            result = api.post('/api/speech', json={'age': 24, 'text': 'ignored'})
            assert result.status_code == 200
            assert result.mimetype == 'audio/mpeg'
            assert result.data == b'fake-mp3'
        upstream.assert_called_once()
        call = upstream.call_args.args[0]
        assert 'Da’daada waxaa lagu qiyaasay 24 sano.' in call.data.decode()
        assert 'ignored' not in call.data.decode()
        assert 'test-key' not in str(api.get('/api/speech').json)


def test_upstream_failure_can_retry(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    with patch('backend.speech.urlopen', side_effect=OSError('secret provider detail')):
        for _ in range(2):
            result = api.post('/api/speech', json={'age': 24})
            assert result.status_code == 502
            assert b'secret' not in result.data


@pytest.mark.skipif(not clip_path(24).is_file(), reason='Run scripts/generate_speech.py first')
def test_generated_clips_cover_every_age():
    missing = [age for age in range(121) if not clip_path(age).is_file()]
    assert missing == []
    assert all(clip_path(age).read_bytes().startswith((b'\xff\xfb', b'\xff\xf3', b'\xff\xf2', b'ID3'))
               for age in range(0, 121, 10))
    # Distinct audio per age; a repeated file would read the wrong number aloud.
    assert len({clip_path(age).read_bytes() for age in range(0, 121, 10)}) == 13
    assert (CLIP_DIR / 'manifest.json').is_file()
