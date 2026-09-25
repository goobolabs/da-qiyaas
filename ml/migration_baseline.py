"""Capture immutable Python reference artifacts before Rust migration.

Run: python -m ml.migration_baseline capture --name <unique-run-name>
     python -m ml.migration_baseline verify models/migration-baselines/<name>
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps

from backend.app import InputError, Predictor, check_camera_quality, decode_image
from ml.face_crop import crop_face
from ml.face_detect import DETECTOR_ID, MODEL_PATH, MODEL_SHA256, detect_faces
from ml.migration_contracts import capture_contracts
from ml.model import IMAGE_SIZE, ROOT, preprocess
from ml.train import metrics

BANDS = [(0, 12), (13, 19), (20, 39), (40, 59), (60, 79), (80, 120)]
SOURCE_FILES = ['backend/app.py', 'backend/feedback.py', 'backend/speech.py',
                'ml/model.py', 'ml/face_detect.py', 'ml/face_crop.py', 'ml/prepare.py',
                'ml/train.py', 'ml/improve.py', 'ml/finetune.py', 'ml/compare_large.py',
                'ml/migration_baseline.py', 'ml/migration_contracts.py', 'requirements.txt']


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def save_array(directory, name, array):
    path = directory / f'{name}.npy'
    np.save(path, np.asarray(array), allow_pickle=False)
    return {'file': path.name, 'shape': list(array.shape), 'dtype': str(array.dtype), 'sha256': sha256(path)}


def snapshot_sources(root, output):
    paths = ['models/age_model.pt', MODEL_PATH.relative_to(ROOT).as_posix(),
             'data/processed/audit.json', *[f'data/processed/{split}.json' for split in ('train', 'validation', 'test')],
             *SOURCE_FILES]
    paths += [p.relative_to(root).as_posix() for p in sorted((root / 'docs').glob('model-*.json'))]
    records = {}
    for relative in paths:
        source = root / relative
        digest = sha256(source)
        destination = output / 'snapshot' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(destination) != digest:
            raise RuntimeError(f'Snapshot changed during copy: {relative}')
        records[relative] = {'sha256': digest, 'bytes': source.stat().st_size}
    return records


def quality_record(gray, box):
    sharpness = float(cv2.Laplacian(cv2.resize(gray, (160, 160)), cv2.CV_64F).var())
    result = {'brightness': float(gray.mean()), 'sharpness': sharpness, 'box': box, 'dimensions': list(gray.shape)}
    try:
        result.update(quality=check_camera_quality(gray, box), error=None)
    except InputError as error:
        result.update(quality=error.quality, error={'code': error.code, 'message': error.message, 'status': error.status})
    return result


def synthetic_fixtures(directory):
    directory.mkdir()
    y, x = np.indices((119, 173))
    rgb = np.stack(((x * 3 + y) % 256, (y * 7) % 256, (x + y * 5) % 256), axis=2).astype('uint8')
    image = Image.fromarray(rgb)
    fixtures = {}
    inputs = [('rgb_png', image, 'PNG', {}), ('rgb_jpeg', image, 'JPEG', {'quality': 95}),
              ('rgb_webp', image, 'WEBP', {'lossless': True}),
              ('grayscale', image.convert('L'), 'PNG', {}),
              ('alpha', Image.fromarray(np.dstack((rgb, (x % 256).astype('uint8')))), 'PNG', {})]
    for orientation in range(2, 9):
        exif = Image.Exif()
        exif[274] = orientation
        inputs.append((f'exif_{orientation}', image, 'JPEG', {'exif': exif, 'quality': 95}))
    inputs += [('thumbnail', image.resize((1801, 1301)), 'PNG', {}),
               ('unsupported_bmp', image, 'BMP', {}),
               ('pixel_limit', Image.new('L', (4001, 4000)), 'PNG', {})]
    for name, original, kind, options in inputs:
        buffer = io.BytesIO()
        original.save(buffer, kind, **options)
        raw = buffer.getvalue()
        (directory / f'{name}.input').write_bytes(raw)
        try:
            decoded = decode_image(raw)
        except InputError as error:
            fixtures[name] = {'error': error.code, 'status': error.status}
            continue
        decoded_array = save_array(directory, name + '.decoded', np.asarray(decoded))
        decoded.thumbnail((1280, 1280))
        box = (0, 3, min(71, decoded.width), min(83, decoded.height - 3))
        crop = crop_face(decoded, box)
        fixtures[name] = {'decoded': decoded_array, 'thumbnail': save_array(directory, name + '.thumbnail', np.asarray(decoded)),
                          'box': list(box), 'crop': save_array(directory, name + '.crop', np.asarray(crop)),
                          'tensor': save_array(directory, name + '.tensor', preprocess()(crop).numpy())}
    for name, raw in [('malformed', b'not an image'), ('truncated', (directory / 'rgb_jpeg.input').read_bytes()[:40])]:
        (directory / f'{name}.input').write_bytes(raw)
        try:
            decode_image(raw)
        except InputError as error:
            fixtures[name] = {'error': error.code, 'status': error.status}
        else:
            raise AssertionError('Invalid fixture unexpectedly decoded')

    # Exact lighting/size boundaries; checkerboards retain useful sharpness.
    box = {'x': 0.1, 'y': 0.1, 'width': 0.5, 'height': 0.5}
    qualities = {}
    for size in (99, 100, 160):
        pattern = ((np.indices((size, size)).sum(axis=0) % 2) * 2 - 1)
        for brightness in (44, 45, 220, 221):
            name = f'quality_{size}_{brightness}'
            gray = (brightness + pattern * 10).astype('uint8')
            qualities[name] = dict(quality_record(gray, box), array=save_array(directory, name, gray))
    for fraction in (0.159, 0.16):
        gray = np.full((160, 160), 120, dtype='uint8')
        name = f'quality_fraction_{fraction}'
        qualities[name] = dict(quality_record(gray, dict(box, width=fraction)), array=save_array(directory, name, gray))
    # Float64 fixtures bracket the sharpness threshold independent of uint8 quantization.
    pattern = (np.indices((160, 160)).sum(axis=0) % 2).astype('float64')
    base_variance = cv2.Laplacian(pattern, cv2.CV_64F).var()
    for variance in (34.99, 35.01):
        name = f'quality_sharpness_{variance}'
        gray = 120 + pattern * np.sqrt(variance / base_variance)
        qualities[name] = dict(quality_record(gray, box), array=save_array(directory, name, gray))
    fixtures['quality'] = qualities
    fixtures['rounding'] = [{'raw_age': age, 'api_age': round(max(0., min(120., age)), 1),
                             'displayed_age': int(np.floor(round(max(0., min(120., age)), 1) + .5))}
                            for age in (-1., 0., .05, .15, 24.25, 24.45, 24.5, 24.55, 119.95, 120., 121.)]
    write_json(directory / 'fixtures.json', fixtures)
    return fixtures


def manifest_rows(snapshot):
    splits = {name: json.loads((snapshot / f'data/processed/{name}.json').read_text(encoding='utf-8'))
              for name in ('train', 'validation', 'test')}
    seen = set()
    for name, rows in splits.items():
        for row in rows:
            if row['hash'] in seen:
                raise ValueError(f'Duplicate pixel hash in manifests ({name}).')
            seen.add(row['hash'])
    return splits


def select_fixtures(splits):
    selected = []
    for split in ('train', 'validation'):
        for low, high in BANDS:
            eligible = sorted((row for row in splits[split] if low <= row['age'] <= high), key=lambda row: row['hash'])
            if eligible:
                selected.append((split, eligible[0]))
    return selected


def checked_image(row):
    path = (ROOT / row['path']).resolve()
    if not path.is_relative_to((ROOT / 'data/UTKFace').resolve()):
        raise ValueError('Manifest image path is outside UTKFace.')
    raw = path.read_bytes()
    image = decode_image(raw)
    pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
    if pixel_hash != row['hash']:
        raise ValueError(f'Image pixels no longer match the manifest: {row["path"]}')
    return image, raw


def real_fixtures(service, splits, output):
    directory = output / 'portraits'
    directory.mkdir()
    records = []
    for index, (split, row) in enumerate(select_fixtures(splits)):
        image, raw = checked_image(row)
        name = f'{index:02d}-{split}'
        (directory / (name + '.input')).write_bytes(raw)
        image.thumbnail((1280, 1280))
        boxes = detect_faces(service.detector, image)
        record = {'name': name, 'split': split, **row, 'boxes': boxes}
        if len(boxes) == 1:
            crop = crop_face(image, boxes[0])
            tensor = service.transform(crop)
            record['tensor'] = save_array(directory, name + '.tensor', tensor.numpy())
            record['crop'] = save_array(directory, name + '.crop', np.asarray(crop))
            with torch.inference_mode():
                record['raw_age'] = float(service.model(tensor.unsqueeze(0)).item())
        for mode in ('upload', 'camera', 'scan'):
            try:
                record[mode] = service.analyze(image.copy(), camera=mode != 'upload', scan_only=mode == 'scan')
            except InputError as error:
                record[mode] = {'error': error.code, 'message': error.message, 'status': error.status,
                                'face_box': error.face_box, 'quality': error.quality}
        records.append(record)
    write_json(directory / 'fixtures.json', records)
    return len(records)


def evaluate_validation(service, rows, output, batch_size=32):
    records = []
    pending = []

    def flush():
        if not pending:
            return
        with torch.inference_mode():
            predictions = service.model(torch.stack([entry[2] for entry in pending])).tolist()
        for (index, view, _), prediction in zip(pending, predictions):
            if not np.isfinite(prediction):
                raise ValueError('Non-finite validation prediction.')
            records[index][view + '_raw_age'] = prediction
        pending.clear()

    for index, row in enumerate(rows):
        image, _ = checked_image(row)
        record = dict(row)
        records.append(record)
        pending.append((index, 'full', service.transform(image)))
        image.thumbnail((1280, 1280))
        boxes = detect_faces(service.detector, image)
        record['boxes'] = boxes
        if len(boxes) == 1:
            pending.append((index, 'crop', service.transform(crop_face(image, boxes[0]))))
        if len(pending) >= batch_size:
            flush()
        if (index + 1) % 250 == 0:
            print(f'Validation: {index + 1}/{len(rows)}', flush=True)
    flush()
    write_json(output / 'validation-predictions.json', records)
    result = {}
    for view in ('full', 'crop'):
        accepted = [row for row in records if view + '_raw_age' in row]
        if not accepted:
            raise ValueError(f'No validation observations for {view}.')
        result[view] = metrics(torch.tensor([row[view + '_raw_age'] for row in accepted]),
                               torch.tensor([row['age'] for row in accepted]))
    result['coverage'] = {'images': len(rows), 'single_face': sum(len(row['boxes']) == 1 for row in records),
                          'no_face': sum(len(row['boxes']) == 0 for row in records),
                          'multiple_faces': sum(len(row['boxes']) > 1 for row in records)}
    return result


def verify(directory):
    directory = Path(directory).resolve()
    inventory_path = directory / 'inventory.json'
    completion = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
    if sha256(inventory_path) != completion['inventory_sha256']:
        raise ValueError('Inventory checksum mismatch.')
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()} - {'inventory.json', 'complete.json'}
    if actual != set(inventory):
        raise ValueError('Baseline file inventory changed.')
    for relative, digest in inventory.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory) or sha256(path) != digest:
            raise ValueError(f'Baseline checksum mismatch: {relative}')
    return len(inventory)


def capture(name, validation_limit=None):
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
        raise ValueError('Run name must contain only letters, digits, hyphens or underscores.')
    if validation_limit is not None and validation_limit < 1:
        raise ValueError('Validation limit must be positive.')
    # No auto-downloads and no writes to original checkpoints/manifests/detector caches.
    if not MODEL_PATH.is_file() or sha256(MODEL_PATH) != MODEL_SHA256:
        raise ValueError('A checksum-verified local YuNet model is required before capture.')
    output = ROOT / 'models/migration-baselines' / name
    output.mkdir(parents=True, exist_ok=False)
    artifacts = snapshot_sources(ROOT, output)
    splits = manifest_rows(output / 'snapshot')
    torch.manual_seed(42)
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    checkpoint_path = output / 'snapshot/models/age_model.pt'
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    service = Predictor(checkpoint_path)
    synthetic_fixtures(output / 'synthetic')
    contracts = capture_contracts()
    write_json(output / 'api-contracts.json', contracts)
    portraits = real_fixtures(service, splits, output)
    rows = splits['validation'][:validation_limit] if validation_limit else splits['validation']
    scores = evaluate_validation(service, rows, output)
    report = {
        'schema_version': 1, 'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'kind': 'python_reference', 'scope': 'full_validation' if validation_limit is None else 'smoke_subset',
        'artifacts': artifacts, 'split_counts': {name: len(rows) for name, rows in splits.items()},
        'model': {key: value for key, value in checkpoint.items() if key != 'state_dict'},
        'preprocessing': {'image_size': IMAGE_SIZE, 'rgb': True, 'layout': 'CHW', 'dtype': 'float32',
                          'mean': [.485, .456, .406], 'std': [.229, .224, .225], 'crop_margin': .15,
                          'detector_id': DETECTOR_ID, 'thumbnail_resample': 'Pillow BICUBIC default',
                          'model_resize': 'torchvision PIL bilinear; antialias=True'},
        'environment': {'python': sys.version, 'platform': platform.platform(), 'torch_threads': 4, 'opencv_threads': 1,
                        'packages': {name: importlib.metadata.version(name) for name in
                                     ('torch', 'torchvision', 'numpy', 'pillow', 'opencv-python-headless', 'flask')}},
        'validation': scores, 'portrait_fixtures': portraits, 'http_contracts': len(contracts['cases']),
        'limits': ['No training or checkpoint promotion.', 'Test manifest was snapshotted; no test images were evaluated.',
                   'Historical reports are preserved separately from this measurement.',
                   'UTKFace results do not establish physical-webcam accuracy.',
                   'Raw predictions and private portrait fixtures remain in ignored local output.',
                   'HTTP inference is scripted; separate portrait/tensor fixtures use the real model.',
                   'MAE clamps raw ages to 0-120 before comparison, following ml.train.metrics.']}
    for relative, metadata in artifacts.items():
        if sha256(ROOT / relative) != metadata['sha256']:
            raise RuntimeError(f'Original artifact changed during capture: {relative}')
    write_json(output / 'report.json', report)
    inventory = {path.relative_to(output).as_posix(): sha256(path) for path in sorted(output.rglob('*')) if path.is_file()}
    write_json(output / 'inventory.json', inventory)
    write_json(output / 'complete.json', {'inventory_sha256': sha256(output / 'inventory.json')})
    verify(output)
    print(f'Complete reference: {output}', flush=True)
    print(json.dumps(scores, indent=2), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    create = subparsers.add_parser('capture')
    create.add_argument('--name', required=True)
    create.add_argument('--validation-limit', type=int, help='Smoke test only; report is marked as a subset.')
    check = subparsers.add_parser('verify')
    check.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.command == 'capture':
        capture(args.name, args.validation_limit)
    else:
        print(f'Verified {verify(args.directory)} baseline files.')


if __name__ == '__main__':
    main()
