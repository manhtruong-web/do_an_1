"""Optional Gemini Vision analysis for OCR and multi-object queries."""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types
from PIL import Image, ImageOps

from .config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisualObservation:
    name: str
    category: str
    brand: str
    package_details: str
    visible_text: str
    bbox: tuple[int, int, int, int] | None

    @property
    def search_text(self) -> str:
        return " ".join(
            item
            for item in (
                self.name,
                self.category,
                self.brand,
                self.package_details,
                self.visible_text,
            )
            if item
        )


def _bounded_text(value: Any, limit: int = 180) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _parse_bbox(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = (int(round(float(item))) for item in value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
        return None
    return x1, y1, x2, y2


def analyze_products_in_image(
    image: Image.Image,
    user_query: str | None = None,
) -> tuple[list[VisualObservation], str]:
    if not settings.visual_search_vision_enabled:
        return [], "disabled"
    if not settings.gemini_configured:
        return [], "not_configured"

    normalized = ImageOps.exif_transpose(image).convert("RGB")
    normalized.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    normalized.save(buffer, format="JPEG", quality=88, optimize=True)
    prompt = (
        "Analyze only retail products visible in this image. Return JSON with an "
        "objects array. For each distinct product, report product_name, category, "
        "brand only when legible, package_details, visible_text copied only when "
        "readable, and bbox as [left, top, right, bottom] normalized to 0..1000. "
        "Do not infer prices, stock, or products that are not visible. Ignore people "
        "and unrelated personal information. If none are identifiable, use an empty "
        "objects array. "
    )
    if user_query:
        prompt += f"User hint: {user_query[:300]}"

    try:
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=20000),
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/jpeg"),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        payload = json.loads(response.text or "{}")
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Gemini Vision returned invalid JSON: %s", type(exc).__name__)
        return [], "invalid_response"
    except Exception as exc:
        logger.warning("Gemini Vision analysis unavailable: %s", type(exc).__name__)
        return [], "unavailable"

    raw_objects = payload.get("objects", []) if isinstance(payload, dict) else []
    if not isinstance(raw_objects, list):
        return [], "invalid_response"

    observations: list[VisualObservation] = []
    for item in raw_objects[:6]:
        if not isinstance(item, dict):
            continue
        observation = VisualObservation(
            name=_bounded_text(item.get("product_name")),
            category=_bounded_text(item.get("category")),
            brand=_bounded_text(item.get("brand"), 100),
            package_details=_bounded_text(item.get("package_details")),
            visible_text=_bounded_text(item.get("visible_text")),
            bbox=_parse_bbox(item.get("bbox")),
        )
        if observation.search_text:
            observations.append(observation)
    return observations, "available"
