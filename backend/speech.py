"""Optional Somali speech. Only fixed age sentences leave the server."""
import os
import re
import threading
from urllib.request import Request, urlopen

from flask import Blueprint, Response, jsonify, request


def speech_blueprint():
    api = Blueprint('speech', __name__)
    cache = {}
    lock = threading.Lock()
    key = os.environ.get('AZURE_SPEECH_KEY', '')
    region = os.environ.get('AZURE_SPEECH_REGION', '')
    configured = bool(key and re.fullmatch(r'[a-z0-9-]+', region))

    @api.get('/api/speech')
    def availability():
        return jsonify(available=configured, language='so-SO')

    @api.post('/api/speech')
    def speak():
        body = request.get_json(silent=True)
        age = body.get('age') if isinstance(body, dict) else None
        if type(age) is not int or not 0 <= age <= 120:
            return jsonify(error='Provide an integer age from 0 to 120.'), 400
        if not configured:
            return jsonify(error='Somali audio is not configured on this server.'), 503
        if not lock.acquire(timeout=1):
            return jsonify(error='Audio is busy. Please try again.'), 429
        try:
            if age not in cache:
                text = f'Da’daada waxaa lagu qiyaasay {age} sano.'
                ssml = f'<speak version="1.0" xml:lang="so-SO"><voice name="so-SO-UbaxNeural">{text}</voice></speak>'
                call = Request(f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1',
                               data=ssml.encode('utf-8'), headers={
                                   'Ocp-Apim-Subscription-Key': key,
                                   'Content-Type': 'application/ssml+xml',
                                   'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3',
                                   'User-Agent': 'DaQiyaas',
                               }, method='POST')
                with urlopen(call, timeout=12) as upstream:
                    audio = upstream.read(256 * 1024 + 1)
                    if not audio or len(audio) > 256 * 1024:
                        raise ValueError('Invalid audio size')
                    cache[age] = audio
            return Response(cache[age], mimetype='audio/mpeg')
        except (OSError, ValueError):
            return jsonify(error='Audio is unavailable. Please try again.'), 502
        finally:
            lock.release()

    return api
