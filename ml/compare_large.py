"""Train a Large candidate without touching the incumbent until validation passes."""
import argparse
import copy
import hashlib
import json
import random
import shutil
import statistics
import time
from collections import Counter
from datetime import datetime, timezone

import torch
from torch.utils.data import ConcatDataset, DataLoader, TensorDataset, WeightedRandomSampler

from ml.improve import CropPortraits, datasets, eligible, evaluate, face_boxes
from ml.model import AgeModel, IMAGE_SIZE, ROOT, load_model
from ml.train import metrics


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def checkpoint(model):
    return {'state_dict': model.state_dict(), 'image_size': IMAGE_SIZE,
            'architecture': f'mobilenet_v3_{model.backbone}_balanced_crops',
            'seed': 209, 'age_range': [0, 120]}


def embeddings(model, dataset, label):
    features, targets = [], []
    with torch.inference_mode():
        for index, (images, ages) in enumerate(DataLoader(dataset, batch_size=64)):
            features.append(model.embed(images))
            targets.append(ages.float())
            if index % 40 == 0:
                print(f'{label}: {min((index + 1) * 64, len(dataset))}/{len(dataset)}', flush=True)
    return torch.cat(features), torch.cat(targets)


def warm_head(model, training, validation, epochs, directory):
    # Local to this run: these features cannot collide with Small/fine-tuned caches.
    train_x, train_y = embeddings(model, ConcatDataset(list(training.values())), 'Head training features')
    val_features = {view: embeddings(model, data, f'Head validation {view}') for view, data in validation.items()}
    loader = DataLoader(TensorDataset(train_x, train_y / 100), batch_size=256, shuffle=True)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=.001, weight_decay=.01)
    best, state, stale, history = float('inf'), None, 0, []
    for epoch in range(epochs):
        model.head.train()
        for features, ages in loader:
            optimizer.zero_grad()
            loss = torch.nn.functional.smooth_l1_loss(model.head(features).squeeze(1), ages, beta=.1)
            loss.backward()
            optimizer.step()
        model.head.eval()
        with torch.inference_mode():
            scores = {view: metrics(model.head(x).squeeze(1) * 100, y) for view, (x, y) in val_features.items()}
        history.append({'epoch': epoch + 1, 'validation': scores})
        score = scores['crop']['mae_years']
        if score < best:
            best, state, stale = score, copy.deepcopy(model.head.state_dict()), 0
        else:
            stale += 1
        if (epoch + 1) % 5 == 0:
            print(f'Head epoch {epoch + 1}: crop validation MAE {score:.3f}', flush=True)
        if stale >= 10:
            break
    model.head.load_state_dict(state)
    with torch.no_grad():
        model.head[-1].weight.mul_(100)
        model.head[-1].bias.mul_(100)
    save_json(directory / 'head-history.json', history)
    torch.save(checkpoint(model), directory / 'warm-head.pt')


def latency_pair(previous, candidate):
    """Interleave warmed models on the same thread count to limit timing drift."""
    sample = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    times = {'previous': [], 'candidate': []}
    with torch.inference_mode():
        for _ in range(10):
            previous(sample)
            candidate(sample)
        for index in range(100):
            order = [('previous', previous), ('candidate', candidate)]
            for name, model in order[::1 if index % 2 else -1]:
                started = time.perf_counter()
                model(sample)
                times[name].append((time.perf_counter() - started) * 1000)
    return {name: {'median_ms': statistics.median(values), 'mean_ms': statistics.mean(values)}
            for name, values in times.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=6)
    parser.add_argument('--head-epochs', type=int, default=60)
    parser.add_argument('--promote', action='store_true', help='Promote only after validation gates pass.')
    args = parser.parse_args()
    if args.epochs < 1 or args.head_epochs < 1:
        parser.error('Epoch counts must be positive.')
    torch.set_num_threads(4)
    torch.manual_seed(209)
    random.seed(209)
    started = time.perf_counter()
    directory = ROOT / 'models' / ('large-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    directory.mkdir()
    print(f'Run directory: {directory}', flush=True)
    for name in ('age_model.pt', 'evaluation.json'):
        shutil.copy2(ROOT / 'models' / name, directory / name)
    original_hash = hashlib.sha256((directory / 'age_model.pt').read_bytes()).hexdigest()
    previous = load_model(directory / 'age_model.pt')
    read = lambda split: json.loads((ROOT / 'data/processed' / f'{split}.json').read_text())
    train_rows, val_rows = read('train'), read('validation')
    train_boxes, val_boxes = face_boxes(train_rows, 'train'), face_boxes(val_rows, 'validation')
    val_data = datasets(val_rows, val_boxes)
    baseline = {view: evaluate(previous, data) for view, data in val_data.items()}
    print('Incumbent validation: ' + json.dumps({v: s['mae_years'] for v, s in baseline.items()}), flush=True)
    model = AgeModel(pretrained=True, backbone='large').eval()
    warm_head(model, datasets(train_rows, train_boxes), val_data, args.head_epochs, directory)
    history = []
    best_eligible, best_crop = float('inf'), float('inf')
    selected_state, selected_scores, selected_epoch = None, None, None
    best_state, best_scores, best_epoch = None, None, None

    def consider(epoch):
        nonlocal best_eligible, best_crop, selected_state, selected_scores, selected_epoch
        nonlocal best_state, best_scores, best_epoch
        scores = {view: evaluate(model, data) for view, data in val_data.items()}
        passes = eligible(scores, baseline)
        history.append({'epoch': epoch, 'validation': scores, 'accuracy_gate_passed': passes})
        crop = scores['crop']['mae_years']
        if crop < best_crop:
            best_crop, best_scores, best_epoch = crop, scores, epoch
            best_state = copy.deepcopy(model.state_dict())
            torch.save(checkpoint(model), directory / 'best-crop.pt')
        if passes and crop < best_eligible:
            best_eligible, selected_scores, selected_epoch = crop, scores, epoch
            selected_state = copy.deepcopy(model.state_dict())
            torch.save(checkpoint(model), directory / 'eligible.pt')
        save_json(directory / 'progress.json', history)
        print(f'Epoch {epoch}: ' + json.dumps({v: s['mae_years'] for v, s in scores.items()}) + f', gate={passes}', flush=True)

    consider(0)
    counts = Counter(row['age'] // 10 for row in train_rows)
    weights = [1 / counts[row['age'] // 10] ** .35 for row in train_rows]
    loader = DataLoader(CropPortraits(train_rows, train_boxes, True), batch_size=32,
                        sampler=WeightedRandomSampler(weights, len(train_rows), replacement=True))
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    for parameter in model.features[10:].parameters():
        parameter.requires_grad = True
    optimizer = torch.optim.AdamW([
        {'params': model.features[10:].parameters(), 'lr': .0001},
        {'params': model.head.parameters(), 'lr': .0002},
    ], weight_decay=.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=.00001)
    for epoch in range(1, args.epochs + 1):
        model.eval()
        model.head.train()
        for index, (images, ages) in enumerate(loader):
            optimizer.zero_grad()
            loss = torch.nn.functional.smooth_l1_loss(model(images) / 100, ages.float() / 100, beta=.05)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            if index % 100 == 0:
                print(f'Fine-tune {epoch}/{args.epochs}: {index + 1}/{len(loader)}, elapsed {time.perf_counter() - started:.0f}s', flush=True)
        scheduler.step()
        consider(epoch)
    # Fix the candidate using validation before opening the existing test split.
    passes = selected_state is not None
    model.load_state_dict(selected_state if passes else best_state)
    model.eval()
    chosen_scores = selected_scores if passes else best_scores
    chosen_epoch = selected_epoch if passes else best_epoch
    torch.save(checkpoint(model), directory / 'selected.pt')
    timing = latency_pair(previous, model)
    report = {'candidate_model': 'mobilenet_v3_large_balanced_crops', 'seed': 209,
              'pretrained_weights': 'MobileNet_V3_Large_Weights.IMAGENET1K_V2',
              'baseline_checkpoint_sha256': original_hash, 'baseline_validation': baseline,
              'selected_validation': chosen_scores, 'selected_epoch': chosen_epoch,
              'accuracy_gate_passed': passes, 'cpu_latency': timing, 'promoted': False,
              'selection_rule': 'Crop validation MAE improves at least 0.1 years; full MAE does not worsen; no age-band MAE worsens more than 1 year on either view.',
              'history': history, 'head_epochs_completed': len(json.loads((directory / 'head-history.json').read_text())),
              'limitations': ['Existing test split is reused, not an external holdout.',
                             'Crop metrics cover single-face detections only.',
                             'No labeled physical-webcam evaluation.',
                             'Near duplicates and identity overlap may remain.',
                             'One seed and training schedule; this does not establish the best possible Large model.']}
    test_rows = read('test')
    test_data = datasets(test_rows, face_boxes(test_rows, 'test'))
    report['candidate_test'] = {v: evaluate(model, d) for v, d in test_data.items()}
    report['baseline_test'] = {v: evaluate(previous, d) for v, d in test_data.items()}
    if passes and args.promote:
        active = ROOT / 'models/age_model.pt'
        if hashlib.sha256(active.read_bytes()).hexdigest() != original_hash:
            raise RuntimeError('Active checkpoint changed during training; candidate preserved, promotion aborted.')
        evaluation = {'model': report['candidate_model'], 'test': report['candidate_test']['full'],
                      'validation': chosen_scores['full'], 'runtime_crop_test': report['candidate_test']['crop'],
                      'runtime_crop_validation': chosen_scores['crop'],
                      'baseline_test_mae': report['baseline_test']['full']['mae_years'],
                      'baseline_runtime_crop_test_mae': report['baseline_test']['crop']['mae_years'],
                      'cpu_model_latency_ms': timing['candidate']['mean_ms'],
                      'previous_cpu_model_latency_ms': timing['previous']['mean_ms'],
                      'training_seconds': time.perf_counter() - started, 'history': history,
                      'limitations': report['limitations']}
        shutil.copy2(directory / 'selected.pt', active.with_suffix('.tmp'))
        active.with_suffix('.tmp').replace(active)
        save_json(ROOT / 'models/evaluation.json', evaluation)
        report['promoted'] = True
    report['elapsed_seconds'] = time.perf_counter() - started
    save_json(directory / 'report.json', report)
    save_json(ROOT / 'models/large-comparison.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('history', 'baseline_validation', 'selected_validation', 'candidate_test', 'baseline_test')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
