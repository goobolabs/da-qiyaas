"""Encode the recorded browser frames as a README GIF; no image synthesis."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / '.run/demo-frames'
manifest = json.loads((directory / 'manifest.json').read_text())
frames, durations = [], []
for index, entry in enumerate(manifest['frames']):
    with Image.open(directory / entry['file']) as image:
        image.thumbnail((960, 825), Image.Resampling.LANCZOS)
        frames.append(image.convert('RGB').quantize(colors=128))
    following = manifest['frames'][index + 1]['at_ms'] if index + 1 < len(manifest['frames']) else manifest['duration_ms']
    durations.append(max(100, following - entry['at_ms']))
output = ROOT / 'docs/assets/demo.gif'
frames[0].save(output, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=2)
with Image.open(output) as result:
    assert result.n_frames > 1
    print(json.dumps({'path': str(output), 'frames': result.n_frames, 'size_mb': round(output.stat().st_size / 1024**2, 2), 'dimensions': result.size}))
