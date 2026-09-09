"""Check README local links, result snapshots and the generated animation."""
import json
import re
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
readme = (root / 'README.md').read_text(encoding='utf-8-sig')
body = re.sub(r'```.*?```', '', readme, flags=re.S)
links = re.findall(r'\]\(([^)]+)\)', body) + re.findall(r'(?:src|href)="([^"]+)"', body)
local = [link.split('#')[0] for link in links if not link.startswith(('https://', 'http://', '#'))]
missing = [link for link in local if not (root / link).exists()]
assert not missing, f'Missing README links: {missing}'
assert readme.count('```') % 2 == 0, 'Unclosed code fence'
report = json.loads((root / 'docs/model-evaluation.json').read_text())
active = json.loads((root / 'models/evaluation.json').read_text())
assert report == active, 'Documentation model snapshot is stale'
with Image.open(root / 'docs/assets/demo.gif') as gif:
    count = gif.n_frames
    assert count > 1 and gif.info.get('loop') == 0
    duration = 0
    for index in range(count):
        gif.seek(index)
        gif.load()
        duration += gif.info.get('duration', 0)
    gif.seek(count // 2)
    gif.convert('RGB').save(root / '.run/demo-middle.png')
print(json.dumps({'local_links_checked': len(local), 'broken_links': missing, 'gif_frames': count, 'gif_duration_ms': duration, 'metrics_snapshot_matches': True}))
