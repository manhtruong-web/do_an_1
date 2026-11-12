"""Resolve and serve product images from the existing project image directory."""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

from .config import settings

PRODUCT_IMAGE_ROOT = (Path(__file__).resolve().parents[1] / "static").resolve()
DATASET_IMAGE_ROOT = (
    settings.dataset_dir / "iconic-images-and-descriptions"
).resolve()
ALLOWED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

DEFAULT_PRODUCT_IMAGE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f0faf5"/>
      <stop offset="1" stop-color="#e6f0eb"/>
    </linearGradient>
    <linearGradient id="bag" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#d5e9dd"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" rx="32" fill="url(#background)"/>
  <circle cx="320" cy="210" r="118" fill="#ffffff" opacity=".52"/>
  <path d="M259 146h122l20 154a18 18 0 0 1-18 20H257a18 18 0 0 1-18-20l20-154Z" fill="url(#bag)" stroke="#94b7a3" stroke-width="5"/>
  <path d="M277 146c0-25 16-43 43-43s43 18 43 43" fill="none" stroke="#94b7a3" stroke-width="8" stroke-linecap="round"/>
  <path d="M320 190c-27 21-31 50 0 72 31-22 27-51 0-72Z" fill="#13815f"/>
  <path d="M320 199v50" stroke="#e8f4ec" stroke-width="4" stroke-linecap="round"/>
  <text x="320" y="376" text-anchor="middle" fill="#21483a" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">SmartMart</text>
  <text x="320" y="407" text-anchor="middle" fill="#698579" font-family="Segoe UI, sans-serif" font-size="16">Chưa có hình ảnh sản phẩm</text>
</svg>
""".encode("utf-8")

DATASET_IMAGE_MATCHES = {
    "táo đỏ": "Fruit/Apple/Red-Delicious/Red-Delicious_Iconic.jpg",
    "táo xanh": "Fruit/Apple/Granny-Smith/Granny-Smith_Iconic.jpg",
    "táo vàng": "Fruit/Apple/Golden-Delicious/Golden-Delicious_Iconic.jpg",
    "chuối": "Fruit/Banana/Banana_Iconic.jpg",
    "cam": "Fruit/Orange/Orange_Iconic.jpg",
    "quýt": "Fruit/Satsumas/Satsumas_Iconic.jpg",
    "dưa hấu": "Fruit/Melon/Watermelon/Watermelon_Iconic.jpg",
    "dưa lưới": "Fruit/Melon/Cantaloupe/Cantaloupe_Iconic.jpg",
    "xoài": "Fruit/Mango/Mango_Iconic.jpg",
    "lê": "Fruit/Pear/Anjou/Anjou_Iconic.jpg",
    "kiwi": "Fruit/Kiwi/Kiwi_Iconic.jpg",
    "bơ": "Fruit/Avocado/Avocado_Iconic.jpg",
    "bắp cải": "Vegetables/Cabbage/Cabbage_Iconic.jpg",
    "cà rốt": "Vegetables/Carrots/Carrots_Iconic.jpg",
    "khoai tây": "Vegetables/Potato/Floury-Potato/Floury-Potato_Iconic.jpg",
    "cà chua": "Vegetables/Tomato/Regular-Tomato/Regular-Tomato_Iconic.jpg",
    "dưa leo": "Vegetables/Cucumber/Cucumber_Iconic.jpg",
    "dưa chuột": "Vegetables/Cucumber/Cucumber_Iconic.jpg",
    "hành tây": "Vegetables/Onion/Yellow-Onion/Yellow-Onion_Iconic.jpg",
    "tỏi": "Vegetables/Garlic/Garlic_Iconic.jpg",
    "ớt đỏ": "Vegetables/Pepper/Red-Bell-Pepper/Red-Bell-Pepper_Iconic.jpg",
    "gừng": "Vegetables/Ginger/Ginger_Iconic.jpg",
    "măng tây": "Vegetables/Asparagus/Asparagus_Iconic.jpg",
    "cà tím": "Vegetables/Aubergine/Aubergine_Iconic.jpg",
    "bí ngòi": "Vegetables/Zucchini/Zucchini_Iconic.jpg",
    "hành boa rô": "Vegetables/Leek/Leek_Iconic.jpg",
}


def resolve_product_image_path(reference: str | None) -> Path | None:
    """Resolve a database reference without allowing reads outside static assets."""
    if not reference:
        return None

    normalized = reference.strip().replace("\\", "/")
    if not normalized or normalized.startswith(("http://", "https://")):
        return None
    if normalized.casefold().startswith("/api/products/"):
        return None

    parts = list(PurePosixPath(normalized).parts)
    if parts and parts[0] == "/":
        parts.pop(0)
    if len(parts) >= 2 and [part.casefold() for part in parts[:2]] == ["backend", "static"]:
        parts = parts[2:]
    elif parts and parts[0].casefold() == "static":
        parts = parts[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None

    reference_path = Path(*parts)
    candidate = (
        reference_path.resolve()
        if reference_path.is_absolute()
        else (PRODUCT_IMAGE_ROOT / reference_path).resolve()
    )
    try:
        candidate.relative_to(PRODUCT_IMAGE_ROOT)
    except ValueError:
        return None

    if candidate.suffix.lower() not in ALLOWED_IMAGE_TYPES or not candidate.is_file():
        return None
    try:
        with Image.open(candidate) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return candidate


def _normalize_product_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(normalized.replace("đ", "d").split())


@lru_cache(maxsize=1)
def _dataset_image_matches() -> tuple[tuple[str, Path], ...]:
    matches = [
        (keyword, (DATASET_IMAGE_ROOT / Path(*relative_path.split("/"))).resolve())
        for keyword, relative_path in DATASET_IMAGE_MATCHES.items()
    ]
    valid_matches = []
    for keyword, path in matches:
        try:
            path.relative_to(DATASET_IMAGE_ROOT)
        except ValueError:
            continue
        if path.is_file():
            valid_matches.append((keyword, path))
    return tuple(sorted(valid_matches, key=lambda match: len(match[0]), reverse=True))


def resolve_dataset_product_image(
    product_name: str | None,
    category: str | None,
) -> Path | None:
    """Return a real, semantically matched dataset image for eligible product names."""
    if not product_name:
        return None

    normalized_name = _normalize_product_name(product_name)
    normalized_category = _normalize_product_name(category or "")
    is_fruit = normalized_category == "trai cay"
    is_vegetable = normalized_category == "rau cu"
    if not (is_fruit or is_vegetable):
        return None

    for keyword, path in _dataset_image_matches():
        normalized_keyword = _normalize_product_name(keyword)
        if normalized_keyword in normalized_name:
            return path
    return None
