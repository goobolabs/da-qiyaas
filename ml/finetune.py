"""Fine-tune a candidate using training/validation only; preserve the baseline."""
import argparse
import copy
import json
import random
import shutil
import time

import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader
from torchvision import transforms

from ml.model import ROOT, IMAGE_SIZE, load_model
from ml.train import Portraits, metrics


class AugmentedPortraits(Portraits):
    def __init__(self, rows):
        super().__init__(rows)
        self.augment = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomAffine(degrees=8, translate=(.05, .05), scale=(.92, 1.08)),
            transforms.ColorJitter(brightness=.2, contrast=.2, saturation=.1),
            transforms.RandomApply([transforms.GaussianBlur(3, sigma=(.1, .7))], p=.15),
        ])

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row['path']) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            tensor = self.transform(self.augment(image))
        return tensor, float(row['age'])


def evaluate(model, loader):
    model.eval()
    predictions, ages = [], []
    with torch.inference_mode():
        for images, targets in loader:
            predictions.append(model(images))
            ages.append(targets.float())
    return metrics(torch.cat(predictions), torch.cat(ages))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=3)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(73)
    random.seed(73)
    directory = ROOT / 'models'
    baseline = directory / 'baseline'
    baseline.mkdir(exist_ok=True)
    for name in ('age_model.pt', 'evaluation.json'):
        if not (baseline / name).exists():
            shutil.copy2(directory / name, baseline / name)
    model = load_model(baseline / 'age_model.pt')
    train_rows = json.loads((ROOT / 'data/processed/train.json').read_text())
    val_rows = json.loads((ROOT / 'data/processed/validation.json').read_text())
    training = DataLoader(AugmentedPortraits(train_rows), batch_size=32, shuffle=True, num_workers=0)
    validation = DataLoader(Portraits(val_rows), batch_size=64, num_workers=0)
    started = time.perf_counter()
    initial = evaluate(model, validation)
    best = initial['mae_years']
    best_state = copy.deepcopy(model.state_dict())
    # Adapt the final feature blocks while keeping early visual filters and BN statistics stable.
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    for parameter in model.features[9:].parameters():
        parameter.requires_grad = True
    optimizer = torch.optim.AdamW([
        {'params': model.features[9:].parameters(), 'lr': 0.00005},
        {'params': model.head.parameters(), 'lr': 0.0001},
    ], weight_decay=.01)
    history = []
    print(f'Baseline validation MAE: {best:.3f}', flush=True)
    for epoch in range(args.epochs):
        model.eval()
        model.head.train()
        for index, (images, ages) in enumerate(training):
            optimizer.zero_grad()
            loss = torch.nn.functional.smooth_l1_loss(model(images) / 100, ages.float() / 100, beta=.05)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            if index % 100 == 0:
                print(f'Epoch {epoch + 1}: batch {index + 1}/{len(training)}, elapsed {time.perf_counter() - started:.0f}s', flush=True)
        result = evaluate(model, validation)
        history.append({'epoch': epoch + 1, 'validation': result})
        print(f'Epoch {epoch + 1}: validation MAE {result["mae_years"]:.3f}', flush=True)
        if result['mae_years'] < best:
            best = result['mae_years']
            best_state = copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    model.eval()
    selected = evaluate(model, validation)
    # Promotion gate is determined using validation only; no test-set selection.
    promoted = best < initial['mae_years'] - .1
    report = {'baseline_validation': initial, 'selected_validation': selected, 'promoted': promoted, 'history': history,
              'selection_rule': 'Validation MAE must improve by at least 0.1 years.',
              'limitations': ['No labeled physical-webcam data was supplied.', 'Camera-like augmentation does not establish real-camera accuracy.', 'The test split was previously evaluated for the baseline; it is not a newly collected external holdout.', 'Near-duplicate and identity overlap may remain.']}
    checkpoint = {'state_dict': model.state_dict(), 'image_size': IMAGE_SIZE, 'architecture': f'mobilenet_v3_{model.backbone}_partial_finetune', 'seed': 73, 'age_range': [0, 120]}
    torch.save(checkpoint, directory / 'candidate.pt')
    if promoted:
        # Evaluate the selected candidate once, after the promotion decision is fixed.
        test_rows = json.loads((ROOT / 'data/processed/test.json').read_text())
        report['test'] = evaluate(model, DataLoader(Portraits(test_rows), batch_size=64))
        model_dir_tmp = directory / 'age_model.tmp'
        torch.save(checkpoint, model_dir_tmp)
        model_dir_tmp.replace(directory / 'age_model.pt')
        with torch.inference_mode():
            sample = torch.zeros(1, 3, IMAGE_SIZE, IMAGE_SIZE)
            model(sample)
            tick = time.perf_counter()
            for _ in range(20):
                model(sample)
            latency = (time.perf_counter() - tick) * 1000 / 20
        baseline_report = json.loads((baseline / 'evaluation.json').read_text())
        evaluation = {'model': checkpoint['architecture'], 'test': report['test'], 'validation': selected,
                      'baseline_test_mae': baseline_report['test']['mae_years'], 'cpu_model_latency_ms': latency,
                      'training_seconds': time.perf_counter() - started, 'history': history, 'limitations': report['limitations']}
        (directory / 'evaluation.json').write_text(json.dumps(evaluation, indent=2))
    report['elapsed_seconds'] = time.perf_counter() - started
    (directory / 'finetune-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'history'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
