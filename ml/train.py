"""CPU baseline: cache frozen pretrained features, train an age regression head."""
import argparse
import copy
import hashlib
import json
import random
import time

import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset, TensorDataset

from ml.model import ROOT, IMAGE_SIZE, AgeModel, preprocess


class Portraits(Dataset):
    def __init__(self, rows):
        self.rows, self.transform = rows, preprocess()

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row['path']) as image:
            tensor = self.transform(ImageOps.exif_transpose(image).convert('RGB'))
        return tensor, float(row['age'])


def extract(model, rows, name, batch_size):
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    cache = ROOT / 'data' / 'processed' / f'{name}-features.pt'
    if cache.exists():
        saved = torch.load(cache, weights_only=True)
        if saved.get('fingerprint') == fingerprint and saved.get('image_size') == IMAGE_SIZE:
            return saved['features'], saved['ages']
    loader = DataLoader(Portraits(rows), batch_size=batch_size, shuffle=False, num_workers=0)
    features, ages = [], []
    started = time.perf_counter()
    model.eval()
    with torch.inference_mode():
        for index, (images, targets) in enumerate(loader):
            features.append(model.embed(images).clone())
            ages.append(targets.float())
            if index % 40 == 0:
                elapsed = time.perf_counter() - started
                print(f'{name}: {min((index + 1) * batch_size, len(rows))}/{len(rows)} images, {elapsed:.1f}s', flush=True)
    values = torch.cat(features), torch.cat(ages)
    torch.save({'fingerprint': fingerprint, 'image_size': IMAGE_SIZE, 'features': values[0], 'ages': values[1]}, cache)
    return values


def metrics(predictions, ages):
    errors = (predictions.clamp(0, 120) - ages).abs()
    bands = {}
    for low, high in [(0, 12), (13, 19), (20, 39), (40, 59), (60, 79), (80, 120)]:
        selected = (ages >= low) & (ages <= high)
        bands[f'{low}-{high}'] = {'count': int(selected.sum()), 'mae': float(errors[selected].mean()) if selected.any() else None}
    return {'mae_years': float(errors.mean()), 'count': len(ages), 'age_bands': bands}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=60)
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(42)
    random.seed(42)
    model = AgeModel(pretrained=True).eval()
    rows = {name: json.loads((ROOT / 'data' / 'processed' / f'{name}.json').read_text()) for name in ['train', 'validation', 'test']}
    if args.benchmark:
        loader = DataLoader(Portraits(rows['train'][:128]), batch_size=args.batch_size)
        with torch.inference_mode():
            model(torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE))
            started = time.perf_counter()
            for images, _ in loader:
                model(images)
        seconds = time.perf_counter() - started
        report = {'images': 128, 'seconds': seconds, 'images_per_second': 128 / seconds, 'estimated_full_feature_minutes': sum(map(len, rows.values())) / 128 * seconds / 60}
        (ROOT / 'data' / 'processed' / 'benchmark.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
        return
    started = time.perf_counter()
    train_x, train_y = extract(model, rows['train'], 'train', args.batch_size)
    val_x, val_y = extract(model, rows['validation'], 'validation', args.batch_size)
    # Normalize age targets to improve head optimization; inference converts back to years.
    loader = DataLoader(TensorDataset(train_x, train_y / 100), batch_size=256, shuffle=True)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=0.001, weight_decay=0.01)
    loss_fn = torch.nn.SmoothL1Loss(beta=0.1)
    best, best_head, stale, history = float('inf'), None, 0, []
    for epoch in range(args.epochs):
        model.head.train()
        for features, targets in loader:
            optimizer.zero_grad()
            loss = loss_fn(model.head(features).squeeze(1), targets)
            loss.backward()
            optimizer.step()
        model.head.eval()
        with torch.inference_mode():
            score = metrics(model.head(val_x).squeeze(1) * 100, val_y)['mae_years']
        history.append({'epoch': epoch + 1, 'validation_mae': score})
        print(f'Epoch {epoch + 1}: validation MAE {score:.3f} years', flush=True)
        if score < best:
            best, best_head, stale = score, copy.deepcopy(model.head.state_dict()), 0
        else:
            stale += 1
        if stale >= 10:
            break
    model.head.load_state_dict(best_head)
    # Fold target scaling into the last layer so runtime output is in years.
    with torch.no_grad():
        model.head[-1].weight.mul_(100)
        model.head[-1].bias.mul_(100)
    model.eval()
    test_x, test_y = extract(model, rows['test'], 'test', args.batch_size)
    with torch.inference_mode():
        evaluation = metrics(model.head(test_x).squeeze(1), test_y)
        validation = metrics(model.head(val_x).squeeze(1), val_y)
        median_baseline = float((test_y - train_y.median()).abs().mean())
        sample, _ = Portraits(rows['test'])[0]
        model(sample.unsqueeze(0))
        tick = time.perf_counter()
        for _ in range(20):
            model(sample.unsqueeze(0))
        latency = (time.perf_counter() - tick) * 1000 / 20
    checkpoint = {'state_dict': model.state_dict(), 'image_size': IMAGE_SIZE, 'architecture': 'mobilenet_v3_small_frozen_regression', 'seed': 42, 'age_range': [0, 120]}
    model_dir = ROOT / 'models'
    model_dir.mkdir(exist_ok=True)
    temporary = model_dir / 'age_model.tmp'
    torch.save(checkpoint, temporary)
    temporary.replace(model_dir / 'age_model.pt')
    report = {'model': checkpoint['architecture'], 'test': evaluation, 'validation': validation, 'median_baseline_test_mae': median_baseline, 'cpu_model_latency_ms': latency, 'training_seconds': time.perf_counter() - started, 'history': history, 'limitations': ['Frozen ImageNet features; baseline model, not a verified age measurement.', 'Identity overlap and near duplicates may remain.', 'Camera domain accuracy has not been measured.', 'Sparse age groups may have larger errors.']}
    (model_dir / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['test', 'median_baseline_test_mae', 'cpu_model_latency_ms', 'training_seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
