"""Local OpenCLIP image/text embedding runtime."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Sequence

import numpy as np
import open_clip
import torch
import torch.nn.functional as functional
from PIL import Image, ImageOps

from .config import settings


@lru_cache(maxsize=1)
def _runtime() -> tuple[Any, Any, Any, torch.device]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.visual_search_model,
        pretrained=settings.visual_search_pretrained,
        device=device,
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(settings.visual_search_model)
    return model, preprocess, tokenizer, device


def _normalized_vectors(values: torch.Tensor) -> np.ndarray:
    vectors = functional.normalize(values.float(), dim=-1)
    result = vectors.cpu().numpy().astype(np.float32, copy=False)
    if not np.isfinite(result).all():
        raise ValueError("OpenCLIP returned non-finite embeddings.")
    return result


def encode_images(images: Sequence[Image.Image]) -> np.ndarray:
    if not images:
        return np.empty((0, 0), dtype=np.float32)

    model, preprocess, _, device = _runtime()
    results: list[np.ndarray] = []
    batch_size = settings.visual_search_batch_size
    with torch.inference_mode():
        for start in range(0, len(images), batch_size):
            batch = [
                preprocess(ImageOps.exif_transpose(image).convert("RGB"))
                for image in images[start : start + batch_size]
            ]
            encoded = model.encode_image(torch.stack(batch).to(device))
            results.append(_normalized_vectors(encoded))
    return np.concatenate(results, axis=0)


def encode_texts(texts: Sequence[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    model, _, tokenizer, device = _runtime()
    results: list[np.ndarray] = []
    batch_size = settings.visual_search_batch_size
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            batch = tokenizer(list(texts[start : start + batch_size])).to(device)
            results.append(_normalized_vectors(model.encode_text(batch)))
    return np.concatenate(results, axis=0)


def clear_runtime_cache() -> None:
    _runtime.cache_clear()
