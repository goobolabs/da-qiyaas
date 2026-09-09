"""Read-only image audit and reproducible exact-pixel-deduplicated split."""
import hashlib
import json
import random
from collections import Counter, defaultdict

from PIL import Image, ImageOps
from ml.model import ROOT


def main():
    dataset = ROOT / 'data' / 'UTKFace'
    output = ROOT / 'data' / 'processed'
    output.mkdir(exist_ok=True)
    groups = defaultdict(list)
    invalid = []
    files = sorted(dataset.rglob('*.jpg'))
    for index, path in enumerate(files):
        try:
            age = int(path.name.split('_')[0])
            if not 0 <= age <= 120:
                raise ValueError('Age out of range')
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.load()
                digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
            groups[digest].append({'path': path.relative_to(ROOT).as_posix(), 'age': age, 'hash': digest})
        except (OSError, ValueError) as error:
            invalid.append({'path': path.relative_to(ROOT).as_posix(), 'reason': str(error)})
        if (index + 1) % 5000 == 0:
            print(f'Audited {index + 1}/{len(files)}', flush=True)
    # Exclude contradictory labels; retain one image per exact-pixel group.
    conflicts = [items for items in groups.values() if len({item['age'] for item in items}) > 1]
    unique = [items[0] for items in groups.values() if len({item['age'] for item in items}) == 1]
    buckets = defaultdict(list)
    for row in unique:
        buckets[row['age'] // 10].append(row)
    rng = random.Random(42)
    splits = {'train': [], 'validation': [], 'test': []}
    for rows in buckets.values():
        rng.shuffle(rows)
        first, second = int(len(rows) * 0.7), int(len(rows) * 0.85)
        for name, subset in zip(splits, (rows[:first], rows[first:second], rows[second:])):
            splits[name].extend(subset)
    for name, rows in splits.items():
        (output / f'{name}.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    report = {
        'input_images': len(files), 'invalid': invalid,
        'duplicate_copies': sum(len(items) - 1 for items in groups.values()),
        'conflicting_label_groups': conflicts,
        'usable_unique_images': len(unique),
        'split_counts': {name: len(rows) for name, rows in splits.items()},
        'age_counts': dict(sorted(Counter(row['age'] for row in unique).items())),
        'seed': 42,
        'limitations': 'Exact-pixel duplicates removed. Near duplicates and shared identities are not guaranteed separated; UTKFace filenames do not provide reliable identity IDs.',
    }
    (output / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['input_images', 'duplicate_copies', 'usable_unique_images', 'split_counts']}, indent=2))


if __name__ == '__main__':
    main()
