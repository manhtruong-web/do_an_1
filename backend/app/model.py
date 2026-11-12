"""Trích xuất image embedding cục bộ bằng ResNet18 pretrained trên ImageNet."""

from functools import lru_cache

import numpy as np
import torch
from PIL import Image, ImageOps
from torchvision.models import ResNet18_Weights, resnet18


EMBEDDING_MODEL_NAME = "resnet18-imagenet-v1"
EMBEDDING_DIMENSIONS = 512


@lru_cache(maxsize=1)
def get_feature_model():
    weights = ResNet18_Weights.DEFAULT
    model = resnet18(weights=weights)
    model.fc = torch.nn.Identity()
    model.eval()
    return model, weights.transforms()


def _prepare_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def extract_feature(image: Image.Image) -> np.ndarray:
    model, transform = get_feature_model()
    tensor = transform(_prepare_image(image)).unsqueeze(0)
    with torch.inference_mode():
        vector = model(tensor).squeeze(0).numpy().astype("float32")
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector
