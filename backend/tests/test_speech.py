from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from backend.speech import speech_blueprint


def client(monkeypatch, configured=True):
    monkeypatch.setenv('AZURE_SPEECH_KEY', 'test-key' if configured else '')
    monkeypatch.setenv('AZURE_SPEECH_REGION', 'eastus')
    app = Flask(__name__)
    app.register_blueprint(speech_blueprint())
    return app.test_client()


@pytest.mark.parametrize('age', [-1, 121, 24.5, True, '24', None])
def test_rejects_invalid_age(monkeypatch, age):
    with patch('backend.speech.urlopen') as upstream:
        assert client(monkeypatch).post('/api/speech', json={'age': age}).status_code == 400
        upstream.assert_not_called()


def test_missing_credentials(monkeypatch):
    api = client(monkeypatch, False)
    assert api.get('/api/speech').json['available'] is False
    assert api.post('/api/speech', json={'age': 24}).status_code == 503


def test_fixed_sentence_cache_and_private_key(monkeypatch):
    api = client(monkeypatch)
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


def test_upstream_failure_can_retry(monkeypatch):
    api = client(monkeypatch)
    with patch('backend.speech.urlopen', side_effect=OSError('secret provider detail')):
        for _ in range(2):
            result = api.post('/api/speech', json={'age': 24})
            assert result.status_code == 502
            assert b'secret' not in result.data
