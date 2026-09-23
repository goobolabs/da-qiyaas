from pathlib import Path

import torch
from torch import nn
from torchvision.models import (mobilenet_v3_small, MobileNet_V3_Small_Weights,
                                mobilenet_v3_large, MobileNet_V3_Large_Weights)
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[1]
IMAGE_SIZE = 160


def preprocess():
    return transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


class AgeModel(nn.Module):
    def __init__(self, pretrained=False, backbone='small'):
        super().__init__()
        torch.hub.set_dir(str(ROOT / 'models' / 'pretrained'))
        self.backbone = backbone
        if backbone == 'small':
            base = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT if pretrained else None)
        elif backbone == 'large':
            base = mobilenet_v3_large(weights=MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None)
        else:
            raise ValueError(f'Unsupported backbone: {backbone}')
        self.features = base.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.head = nn.Sequential(nn.Linear(base.classifier[0].in_features, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1))

    def embed(self, images):
        return self.pool(self.features(images)).flatten(1)

    def forward(self, images):
        return self.head(self.embed(images)).squeeze(1)


def load_model(path):
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    if checkpoint.get('image_size') != IMAGE_SIZE:
        raise ValueError('Model preprocessing version does not match the application.')
    architecture = checkpoint.get('architecture', '')
    if architecture.startswith('mobilenet_v3_small_'):
        backbone = 'small'
    elif architecture.startswith('mobilenet_v3_large_'):
        backbone = 'large'
    else:
        raise ValueError(f'Unsupported checkpoint architecture: {architecture}')
    model = AgeModel(backbone=backbone)
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    return model
