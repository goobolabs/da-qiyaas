"""Generate the fixed Somali age sentences once, so serving needs no speech credentials.

Uses the Microsoft Edge read-aloud voices through edge-tts, which requires no API key.
Run it once; afterwards Flask reads the clips from disk and makes no outbound request.

    .\\.venv\\Scripts\\python.exe scripts/generate_speech.py
"""
import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import edge_tts  # noqa: E402

from backend.speech import CLIP_DIR, MAX_CLIP_BYTES, VOICE, clip_path, sentence  # noqa: E402

# MPEG audio frame sync; guards against saving an error page as if it were audio.
MP3_MAGIC = (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2', b'ID3')


async def synthesize(age, voice):
    stream = edge_tts.Communicate(sentence(age), voice)
    audio = b''.join([chunk['data'] async for chunk in stream.stream() if chunk['type'] == 'audio'])
    if not audio.startswith(MP3_MAGIC):
        raise RuntimeError(f'Age {age}: response is not MP3 audio.')
    if not 0 < len(audio) <= MAX_CLIP_BYTES:
        raise RuntimeError(f'Age {age}: unexpected audio size {len(audio)} bytes.')
    return audio


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--voice', default=VOICE)
    parser.add_argument('--force', action='store_true', help='Regenerate clips that already exist.')
    args = parser.parse_args()
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    manifest, written, total = {}, 0, 0
    for age in range(121):
        path = clip_path(age)
        if args.force or not path.is_file():
            path.write_bytes(await synthesize(age, args.voice))
            written += 1
        data = path.read_bytes()
        total += len(data)
        manifest[str(age)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if (age + 1) % 20 == 0:
            print(f'{age + 1}/121 clips ready', flush=True)
    report = {'voice': args.voice, 'language': 'so-SO', 'count': len(manifest),
              'sentence_template': sentence('{age}'), 'total_bytes': total,
              'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'source': 'Microsoft Edge read-aloud voices via edge-tts; no API key required.',
              'clips': manifest}
    (CLIP_DIR / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'clips'}, indent=2, ensure_ascii=False))
    print(f'newly generated: {written}')


if __name__ == '__main__':
    asyncio.run(main())
