"""Optional Somali speech. Only fixed age sentences leave the server."""
import os
import re
import threading
from urllib.request import Request, urlopen

from flask import Blueprint, Response, jsonify, request

from ml.model import ROOT

# Pre-generated clips, one fixed sentence per age. See scripts/generate_speech.py.
CLIP_DIR = ROOT / 'data' / 'speech' / 'so'
VOICE = 'so-SO-UbaxNeural'
MAX_CLIP_BYTES = 256 * 1024


def sentence(age):
    return f'Da’daada waxaa lagu qiyaasay {age} sano.'


def clip_path(age):
    return CLIP_DIR / f'{age}.mp3'


def speech_blueprint():
    api = Blueprint('speech', __name__)
    cache = {}
    lock = threading.Lock()
    key = os.environ.get('AZURE_SPEECH_KEY', '')
    region = os.environ.get('AZURE_SPEECH_REGION', '')
    azure = bool(key and re.fullmatch(r'[a-z0-9-]+', region))

    def local_clips():
        return sum(clip_path(age).is_file() for age in range(121))

    @api.get('/api/speech')
    def availability():
        clips = local_clips()
        return jsonify(available=bool(clips) or azure, language='so-SO',
                       source='local' if clips else 'azure' if azure else 'none', clips=clips)

    @api.post('/api/speech')
    def speak():
        body = request.get_json(silent=True)
        age = body.get('age') if isinstance(body, dict) else None
        if type(age) is not int or not 0 <= age <= 120:
            return jsonify(error='Provide an integer age from 0 to 120.'), 400
        # Prefer the local clip: no credentials, no outbound request, no rate limit.
        path = clip_path(age)
        if path.is_file() and path.stat().st_size <= MAX_CLIP_BYTES:
            return Response(path.read_bytes(), mimetype='audio/mpeg')
        if not azure:
            return jsonify(error='Somali audio is not configured on this server.'), 503
        if not lock.acquire(timeout=1):
            return jsonify(error='Audio is busy. Please try again.'), 429
        try:
            if age not in cache:
                ssml = f'<speak version="1.0" xml:lang="so-SO"><voice name="{VOICE}">{sentence(age)}</voice></speak>'
                call = Request(f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1',
                               data=ssml.encode('utf-8'), headers={
                                   'Ocp-Apim-Subscription-Key': key,
                                   'Content-Type': 'application/ssml+xml',
                                   'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3',
                                   'User-Agent': 'DaQiyaas',
                               }, method='POST')
                with urlopen(call, timeout=12) as upstream:
                    audio = upstream.read(MAX_CLIP_BYTES + 1)
                    if not audio or len(audio) > MAX_CLIP_BYTES:
                        raise ValueError('Invalid audio size')
                    cache[age] = audio
            return Response(cache[age], mimetype='audio/mpeg')
        except (OSError, ValueError):
            return jsonify(error='Audio is unavailable. Please try again.'), 502
        finally:
            lock.release()

    return api
