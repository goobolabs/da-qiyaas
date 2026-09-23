"""Age-balanced fine-tuning evaluated on both portraits and serving crops."""
import argparse
import copy
import hashlib
import json
import random
import shutil
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import local

import cv2
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import transforms

from ml.face_crop import crop_face
from ml.face_detect import DETECTOR_ID, create_detector, detect_faces
from ml.model import ROOT, IMAGE_SIZE, load_model
from ml.train import Portraits, metrics


def face_boxes(rows, split):
    # The detector id is part of the key, so boxes from an older detector are never reused.
    fingerprint = hashlib.sha256(json.dumps([DETECTOR_ID, rows], sort_keys=True).encode()).hexdigest()
    path = ROOT / 'data/processed' / f'{split}-face-boxes.json'
    if path.exists():
        cache = json.loads(path.read_text())
        if cache['fingerprint'] == fingerprint:
            return cache['boxes']
    cv2.setNumThreads(1)
    state = local()

    def detect(row):
        if not hasattr(state, 'detector'):
            state.detector = create_detector()
        with Image.open(ROOT / row['path']) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1280, 1280))
            found = detect_faces(state.detector, image)
            return list(found[0]) if len(found) == 1 else None
    boxes = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, box in enumerate(pool.map(detect, rows)):
            boxes.append(box)
            if (index + 1) % 2000 == 0:
                print(f'{split} face detection: {index + 1}/{len(rows)}', flush=True)
    path.write_text(json.dumps({'fingerprint': fingerprint, 'boxes': boxes}))
    return boxes


class CropPortraits(Portraits):
    def __init__(self, rows, boxes, augment=False):
        super().__init__(rows)
        self.boxes, self.augment = boxes, augment
        self.jitter = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomAffine(6, translate=(.03, .03), scale=(.95, 1.05)),
            transforms.ColorJitter(brightness=.15, contrast=.15, saturation=.1),
        ])

    def __getitem__(self, index):
        row, box = self.rows[index], self.boxes[index]
        with Image.open(ROOT / row['path']) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1280, 1280))
            if box is not None and (not self.augment or random.random() < .5):
                image = crop_face(image, box)
            if self.augment:
                image = self.jitter(image)
            return self.transform(image), float(row['age'])


def evaluate(model, dataset):
    model.eval()
    predictions, ages = [], []
    with torch.inference_mode():
        for images, targets in DataLoader(dataset, batch_size=64):
            predictions.append(model(images))
            ages.append(targets.float())
    return metrics(torch.cat(predictions), torch.cat(ages))


def datasets(rows, boxes):
    accepted = [(row, box) for row, box in zip(rows, boxes) if box is not None]
    return {'full': Portraits(rows), 'crop': CropPortraits([r for r, _ in accepted], [b for _, b in accepted])}


def eligible(scores, baseline):
    return (scores['crop']['mae_years'] <= baseline['crop']['mae_years'] - .1
            and scores['full']['mae_years'] <= baseline['full']['mae_years']
            and all(scores[view]['age_bands'][band]['mae'] <= values['mae'] + 1
                    for view in ('full', 'crop')
                    for band, values in baseline[view]['age_bands'].items() if values['count']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=6)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(109)
    random.seed(109)
    started = time.perf_counter()
    directory = ROOT / 'models' / ('improvement-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    directory.mkdir()
    for name in ('age_model.pt', 'evaluation.json'):
        shutil.copy2(ROOT / 'models' / name, directory / name)
    model = load_model(directory / 'age_model.pt')
    read = lambda name: json.loads((ROOT / 'data/processed' / f'{name}.json').read_text())
    training, validation = read('train'), read('validation')
    train_boxes, val_boxes = face_boxes(training, 'train'), face_boxes(validation, 'validation')
    val_data = datasets(validation, val_boxes)
    baseline = {name: evaluate(model, dataset) for name, dataset in val_data.items()}
    print('Starting validation: ' + json.dumps({k: v['mae_years'] for k, v in baseline.items()}), flush=True)
    counts = Counter(row['age'] // 10 for row in training)
    weights = [1 / counts[row['age'] // 10] ** .35 for row in training]
    loader = DataLoader(CropPortraits(training, train_boxes, True), batch_size=32,
                        sampler=WeightedRandomSampler(weights, len(training), replacement=True))
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    first_block = 10 if model.backbone == 'large' else 6
    for parameter in model.features[first_block:].parameters():
        parameter.requires_grad = True
    optimizer = torch.optim.AdamW([
        {'params': model.features[first_block:].parameters(), 'lr': .0001},
        {'params': model.head.parameters(), 'lr': .0002},
    ], weight_decay=.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=.00001)
    best, best_state, best_scores, selected_epoch = baseline['crop']['mae_years'], None, None, None
    history = []
    for epoch in range(args.epochs):
        model.eval()  # Freeze batch-normalization running statistics.
        model.head.train()
        for index, (images, ages) in enumerate(loader):
            optimizer.zero_grad()
            loss = torch.nn.functional.smooth_l1_loss(model(images) / 100, ages.float() / 100, beta=.05)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            if index % 100 == 0:
                print(f'Epoch {epoch + 1}/{args.epochs}: {index + 1}/{len(loader)} batches, elapsed {time.perf_counter() - started:.0f}s', flush=True)
        scheduler.step()
        scores = {name: evaluate(model, dataset) for name, dataset in val_data.items()}
        history.append({'epoch': epoch + 1, 'validation': scores})
        print(f'Epoch {epoch + 1} validation: ' + json.dumps({k: v['mae_years'] for k, v in scores.items()}), flush=True)
        if eligible(scores, baseline) and scores['crop']['mae_years'] < best:
            best, best_state, best_scores, selected_epoch = scores['crop']['mae_years'], copy.deepcopy(model.state_dict()), scores, epoch + 1
        (directory / 'progress.json').write_text(json.dumps(history, indent=2))
    report = {'baseline_validation': baseline, 'selected_validation': best_scores, 'selected_epoch': selected_epoch,
              'promoted': best_state is not None, 'history': history,
              'selection_rule': 'Crop validation MAE improves >=0.1y, full MAE does not worsen, no age-band MAE worsens >1y on either view.',
              'limitations': ['Existing test split has been evaluated previously; not an external holdout.',
                             'Crop scores cover single-face detections only.', 'No labeled webcam evaluation.',
                             'Near duplicates and identity overlap may remain.']}
    if best_state is not None:
        model.load_state_dict(best_state)
        checkpoint = {'state_dict': best_state, 'image_size': IMAGE_SIZE, 'architecture': f'mobilenet_v3_{model.backbone}_balanced_crops', 'seed': 109, 'age_range': [0, 120]}
        torch.save(checkpoint, directory / 'selected.pt')
        test_rows = read('test')  # Selection is fixed before loading the test split.
        test_data = datasets(test_rows, face_boxes(test_rows, 'test'))
        report['test'] = {name: evaluate(model, dataset) for name, dataset in test_data.items()}
        previous = load_model(directory / 'age_model.pt')
        report['baseline_test_crop'] = evaluate(previous, test_data['crop'])
        with torch.inference_mode():
            sample = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
            model(sample)
            tick = time.perf_counter()
            for _ in range(20):
                model(sample)
            latency = (time.perf_counter() - tick) * 1000 / 20
        evaluation = {'model': checkpoint['architecture'], 'test': report['test']['full'], 'validation': best_scores['full'],
                      'runtime_crop_test': report['test']['crop'], 'runtime_crop_validation': best_scores['crop'],
                      'baseline_test_mae': json.loads((directory / 'evaluation.json').read_text())['test']['mae_years'],
                      'cpu_model_latency_ms': latency, 'training_seconds': time.perf_counter() - started,
                      'history': history, 'limitations': report['limitations']}
        shutil.copy2(directory / 'selected.pt', ROOT / 'models/age_model.tmp')
        (ROOT / 'models/age_model.tmp').replace(ROOT / 'models/age_model.pt')
        (ROOT / 'models/evaluation.json').write_text(json.dumps(evaluation, indent=2))
    report['elapsed_seconds'] = time.perf_counter() - started
    (directory / 'report.json').write_text(json.dumps(report, indent=2))
    (ROOT / 'models/improvement-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'history'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
