"""Hash-based OpenCLIP product index and hybrid visual/metadata retrieval."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import text
from sqlalchemy.orm import Session

from .clip_model import encode_images, encode_texts
from .config import settings
from .image_service import FaissProductIndex
from .product_images import PRODUCT_IMAGE_ROOT, resolve_product_image_path
from .vision_analysis import VisualObservation, analyze_products_in_image

logger = logging.getLogger(__name__)

MAX_SEARCH_CANDIDATES = 50
MAX_INDEX_CHECK_INTERVAL_SECONDS = 60
MIN_RESULT_SCORE = 0.30
SEARCH_CACHE_TTL_SECONDS = 900
MAX_SEARCH_CACHE_ENTRIES = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _product_text(product: dict[str, Any]) -> str:
    return " ".join(
        str(product.get(key) or "").strip()
        for key in ("TenSP", "DanhMuc", "ThuongHieu", "MoTa")
        if str(product.get(key) or "").strip()
    )


def _normalize_text(value: str) -> str:
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _token_overlap(query: str, target: str) -> float:
    query_tokens = set(_normalize_text(query).split())
    target_tokens = set(_normalize_text(target).split())
    if not query_tokens or not target_tokens:
        return 0.0
    return len(query_tokens & target_tokens) / len(query_tokens)


def _validated_vector(value: Any) -> np.ndarray | None:
    try:
        vector = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all():
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


class VisualSearchEngine:
    """Builds one vector per unique image and one text vector per live product."""

    _lock = threading.RLock()
    _loaded = False
    _last_catalog_check = 0.0
    _source_signature: tuple[tuple[int, str, int, int], ...] = ()
    _image_index: faiss.IndexFlatIP | None = None
    _text_index: faiss.IndexFlatIP | None = None
    _image_hashes: list[str] = []
    _image_product_ids: list[set[int]] = []
    _text_product_ids: list[int] = []
    _products_by_id: dict[int, dict[str, Any]] = {}
    _image_records: list[dict[str, Any]] = []
    _errors: list[dict[str, Any]] = []
    _built_at: str | None = None

    @classmethod
    def cache_path(cls) -> Path:
        return settings.faiss_index_dir / "visual_product_embeddings.json"

    @classmethod
    def _fetch_catalog(
        cls, db: Session
    ) -> tuple[dict[int, dict[str, Any]], list[tuple[int, Path]]]:
        rows = db.execute(
            text("""
                SELECT sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
                       sp.MoTa, sp.ThuongHieu, sp.Anh
                FROM dbo.SanPham sp
                INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
                WHERE sp.TrangThai = 1
                ORDER BY sp.MaSP
            """)
        ).mappings().all()
        products = {int(row["MaSP"]): dict(row) for row in rows}
        sources: list[tuple[int, Path]] = []
        seen_paths: set[tuple[int, str]] = set()

        for product_id, product in products.items():
            path = resolve_product_image_path(product.get("Anh"))
            if path is not None:
                sources.append((product_id, path))
                seen_paths.add((product_id, str(path)))

        additional_rows = db.execute(
            text("""
                SELECT spa.MaSP, spa.DuongDanAnhDataset
                FROM dbo.SanPhamAnh spa
                INNER JOIN dbo.SanPham sp ON sp.MaSP = spa.MaSP
                WHERE sp.TrangThai = 1 AND spa.DuongDanAnhDataset IS NOT NULL
            """)
        ).all()
        for row in additional_rows:
            product_id = int(row[0])
            path = resolve_product_image_path(row[1])
            path_key = (product_id, str(path)) if path is not None else None
            if path is not None and product_id in products and path_key not in seen_paths:
                sources.append((product_id, path))
                seen_paths.add(path_key)

        return products, sources

    @classmethod
    def _signature(
        cls, products: dict[int, dict[str, Any]], sources: list[tuple[int, Path]]
    ) -> tuple[tuple[int, str, int, int], ...]:
        signature = []
        for product_id, path in sources:
            try:
                stat = path.stat()
            except OSError:
                continue
            signature.append((product_id, str(path), stat.st_size, stat.st_mtime_ns))
        product_signature = tuple(
            (
                product_id,
                _normalize_text(_product_text(product)),
                0,
                0,
            )
            for product_id, product in sorted(products.items())
        )
        return tuple(signature) + product_signature

    @classmethod
    def _load_cache(cls) -> dict[str, Any]:
        try:
            payload = json.loads(cls.cache_path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Cannot read visual embedding cache: %s", type(exc).__name__)
            return {}
        if (
            payload.get("model") != settings.visual_search_model
            or payload.get("pretrained") != settings.visual_search_pretrained
        ):
            return {}
        return payload

    @classmethod
    def _save_cache(cls, payload: dict[str, Any]) -> None:
        path = cls.cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, separators=(",", ":"), allow_nan=False),
                encoding="utf-8",
            )
            temporary_path.replace(path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @classmethod
    def _set_indexes(
        cls,
        image_vectors: dict[str, np.ndarray],
        image_products: dict[str, set[int]],
        text_vectors: dict[int, np.ndarray],
    ) -> None:
        cls._image_hashes = sorted(image_vectors)
        cls._image_product_ids = [
            image_products.get(content_hash, set()) for content_hash in cls._image_hashes
        ]
        cls._image_index = None
        cls._text_product_ids = sorted(text_vectors)
        cls._text_index = None
        if image_vectors:
            matrix = np.stack([image_vectors[key] for key in cls._image_hashes]).astype(np.float32)
            faiss.normalize_L2(matrix)
            cls._image_index = faiss.IndexFlatIP(matrix.shape[1])
            cls._image_index.add(matrix)
        if text_vectors:
            matrix = np.stack([text_vectors[key] for key in cls._text_product_ids]).astype(np.float32)
            faiss.normalize_L2(matrix)
            cls._text_index = faiss.IndexFlatIP(matrix.shape[1])
            cls._text_index.add(matrix)

    @classmethod
    def build_from_db(cls, db: Session) -> dict[str, Any]:
        with cls._lock:
            products, sources = cls._fetch_catalog(db)
            signature = cls._signature(products, sources)
            old_cache = cls._load_cache()
            old_images = old_cache.get("image_vectors", {})
            old_text = old_cache.get("text_vectors", {})
            old_products = old_cache.get("products", {})
            if not isinstance(old_images, dict):
                old_images = {}
            if not isinstance(old_text, dict):
                old_text = {}
            if not isinstance(old_products, dict):
                old_products = {}
            previous_images = old_cache.get("images", [])
            previous_errors = old_cache.get("errors", [])
            if not isinstance(previous_images, list):
                previous_images = []
            if not isinstance(previous_errors, list):
                previous_errors = []
            old_image_records = {
                (int(item["MaSP"]), str(item["path"])): item
                for item in previous_images
                if isinstance(item, dict) and str(item.get("MaSP", "")).isdigit()
            }
            old_errors = {
                (int(item["MaSP"]), str(item["path"])): item
                for item in previous_errors
                if isinstance(item, dict) and str(item.get("MaSP", "")).isdigit()
            }
            image_vectors: dict[str, np.ndarray] = {}
            text_vectors: dict[int, np.ndarray] = {}
            image_products: dict[str, set[int]] = defaultdict(set)
            image_records: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            pending_images: dict[str, Image.Image] = {}
            pending_texts: dict[int, str] = {}

            for product_id, path in sources:
                try:
                    content = path.read_bytes()
                    content_hash = hashlib.sha256(content).hexdigest()
                    saved_vector = _validated_vector(old_images.get(content_hash))
                    if saved_vector is not None:
                        image_vectors[content_hash] = saved_vector
                    elif content_hash not in pending_images:
                        with Image.open(BytesIO(content)) as opened:
                            opened.load()
                            pending_images[content_hash] = ImageOps.exif_transpose(opened).convert("RGB")
                    image_products[content_hash].add(product_id)
                    display_path = path.relative_to(PRODUCT_IMAGE_ROOT).as_posix()
                    previous_record = old_image_records.get((product_id, display_path), {})
                    image_records.append({
                        "MaSP": product_id,
                        "path": display_path,
                        "sha256": content_hash,
                        "updated_at": (
                            previous_record.get("updated_at")
                            if previous_record.get("sha256") == content_hash
                            else _utc_now()
                        ),
                    })
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    display_path = (
                        path.relative_to(PRODUCT_IMAGE_ROOT).as_posix()
                        if path.is_relative_to(PRODUCT_IMAGE_ROOT)
                        else path.name
                    )
                    previous_error = old_errors.get((product_id, display_path), {})
                    errors.append({
                        "MaSP": product_id,
                        "path": display_path,
                        "error": type(exc).__name__,
                        "updated_at": _utc_now(),
                        "attempts": int(previous_error.get("attempts", 0)) + 1,
                    })
                    logger.warning(
                        "Visual index skipped MaSP=%d (%s)",
                        product_id,
                        type(exc).__name__,
                    )

            for product_id, product in products.items():
                product_text = _product_text(product)
                text_hash = hashlib.sha256(product_text.encode("utf-8")).hexdigest()
                old_record = old_text.get(str(product_id), {})
                saved_vector = (
                    _validated_vector(old_record.get("vector"))
                    if old_record.get("sha256") == text_hash
                    else None
                )
                if saved_vector is not None:
                    text_vectors[product_id] = saved_vector
                else:
                    pending_texts[product_id] = product_text

            pending_image_ids = list(pending_images)
            for start in range(0, len(pending_image_ids), settings.visual_search_batch_size):
                hashes = pending_image_ids[start : start + settings.visual_search_batch_size]
                images = [pending_images[key] for key in hashes]
                try:
                    vectors = encode_images(images)
                    if len(vectors) != len(hashes):
                        raise ValueError("OpenCLIP returned an incomplete image batch.")
                    for content_hash, vector in zip(hashes, vectors):
                        validated = _validated_vector(vector)
                        if validated is None:
                            raise ValueError("Invalid image embedding.")
                        image_vectors[content_hash] = validated
                except Exception as exc:
                    logger.warning("OpenCLIP image batch failed: %s", type(exc).__name__)
                    for content_hash, image in zip(hashes, images):
                        try:
                            vector = _validated_vector(encode_images([image])[0])
                            if vector is None:
                                raise ValueError("Invalid image embedding.")
                            image_vectors[content_hash] = vector
                        except Exception as image_exc:
                            for product_id in sorted(image_products[content_hash]):
                                record = next(
                                    (item for item in image_records
                                     if item["sha256"] == content_hash
                                     and item["MaSP"] == product_id),
                                    None,
                                )
                                record_path = record["path"] if record else ""
                                previous_error = old_errors.get(
                                    (product_id, record_path), {}
                                )
                                errors.append({
                                    "MaSP": product_id,
                                    "path": record_path,
                                    "error": type(image_exc).__name__,
                                    "updated_at": _utc_now(),
                                    "attempts": int(previous_error.get("attempts", 0)) + 1,
                                })

            pending_text_ids = list(pending_texts)
            for start in range(0, len(pending_text_ids), settings.visual_search_batch_size):
                product_ids = pending_text_ids[start : start + settings.visual_search_batch_size]
                texts = [pending_texts[product_id] for product_id in product_ids]
                vectors = encode_texts(texts)
                if len(vectors) != len(product_ids):
                    raise ValueError("OpenCLIP returned an incomplete text batch.")
                for product_id, vector in zip(product_ids, vectors):
                    validated = _validated_vector(vector)
                    if validated is None:
                        raise ValueError(f"Invalid text embedding for MaSP={product_id}.")
                    text_vectors[product_id] = validated

            valid_hashes = set(image_vectors)
            image_records = [record for record in image_records if record["sha256"] in valid_hashes]
            image_products = {
                key: value for key, value in image_products.items() if key in valid_hashes
            }
            text_hashes = {
                product_id: hashlib.sha256(
                    _product_text(product).encode("utf-8")
                ).hexdigest()
                for product_id, product in products.items()
            }
            product_cache = {}
            for product_id, product in products.items():
                previous = old_products.get(str(product_id), {})
                product_cache[str(product_id)] = {
                    "TenSP": str(product.get("TenSP") or ""),
                    "DanhMuc": str(product.get("DanhMuc") or ""),
                    "ThuongHieu": str(product.get("ThuongHieu") or ""),
                    "MoTa": str(product.get("MoTa") or ""),
                    "text_sha256": text_hashes[product_id],
                    "updated_at": (
                        previous.get("updated_at")
                        if previous.get("text_sha256") == text_hashes[product_id]
                        else _utc_now()
                    ),
                }
            cache = {
                "version": 1,
                "model": settings.visual_search_model,
                "pretrained": settings.visual_search_pretrained,
                "built_at": _utc_now(),
                "products": product_cache,
                "image_vectors": {
                    key: vector.tolist() for key, vector in image_vectors.items()
                },
                "text_vectors": {
                    str(key): {
                        "sha256": text_hashes[key],
                        "vector": text_vectors[key].tolist(),
                    }
                    for key in text_vectors
                },
                "images": image_records,
                "errors": errors,
            }
            cls._save_cache(cache)
            cls._set_indexes(image_vectors, image_products, text_vectors)
            cls._products_by_id = products
            cls._image_records = image_records
            cls._errors = errors
            cls._source_signature = signature
            cls._last_catalog_check = time.monotonic()
            cls._built_at = cache["built_at"]
            cls._loaded = True
            return cls.status()

    @classmethod
    def ensure_loaded(cls, db: Session) -> None:
        if cls._loaded and time.monotonic() - cls._last_catalog_check < MAX_INDEX_CHECK_INTERVAL_SECONDS:
            return
        with cls._lock:
            if cls._loaded and time.monotonic() - cls._last_catalog_check < MAX_INDEX_CHECK_INTERVAL_SECONDS:
                return
            products, sources = cls._fetch_catalog(db)
            signature = cls._signature(products, sources)
            if cls._loaded and signature == cls._source_signature:
                cls._products_by_id = products
                cls._last_catalog_check = time.monotonic()
                return
            cls.build_from_db(db)

    @classmethod
    def _search_index(
        cls,
        index: faiss.IndexFlatIP | None,
        query_vector: np.ndarray,
        index_kind: str,
    ) -> dict[int, float]:
        if index is None or index.ntotal == 0:
            return {}
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        scores, indexes = index.search(query, min(MAX_SEARCH_CANDIDATES, index.ntotal))
        results: dict[int, float] = {}
        for score, index_position in zip(scores[0], indexes[0]):
            if index_position < 0:
                continue
            if index_kind == "image":
                product_ids = cls._image_product_ids[index_position]
            else:
                product_ids = {cls._text_product_ids[index_position]}
            for product_id in product_ids:
                results[product_id] = max(results.get(product_id, -1.0), float(score))
        return results

    @classmethod
    def _crop_for_observation(
        cls, image: Image.Image, observation: VisualObservation
    ) -> Image.Image:
        if observation.bbox is None:
            return image
        width, height = image.size
        x1, y1, x2, y2 = observation.bbox
        crop = image.crop((
            max(0, int(width * x1 / 1000)),
            max(0, int(height * y1 / 1000)),
            min(width, int(width * x2 / 1000)),
            min(height, int(height * y2 / 1000)),
        ))
        return crop if crop.width >= 32 and crop.height >= 32 else image

    @classmethod
    def _fallback_crops(cls, image: Image.Image) -> list[Image.Image]:
        width, height = image.size
        crops = [image]
        if width > height * 1.12:
            columns, rows = 3, 2
        elif height > width * 1.12:
            columns, rows = 2, 3
        else:
            columns, rows = 2, 2
        for row in range(rows):
            for column in range(columns):
                left = int(width * column / columns)
                top = int(height * row / rows)
                right = int(width * (column + 1) / columns)
                bottom = int(height * (row + 1) / rows)
                if right - left >= 32 and bottom - top >= 32:
                    crops.append(image.crop((left, top, right, bottom)))
        center_width = max(32, int(width * 0.68))
        center_height = max(32, int(height * 0.68))
        left = (width - center_width) // 2
        top = (height - center_height) // 2
        crops.append(image.crop((left, top, left + center_width, top + center_height)))
        return crops

    @classmethod
    def _live_products(cls, db: Session, product_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not product_ids:
            return {}
        params = {f"id_{index}": value for index, value in enumerate(product_ids)}
        placeholders = ", ".join(f":id_{index}" for index in range(len(product_ids)))
        rows = db.execute(
            text(f"""
                SELECT sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc, sp.MoTa,
                       sp.ThuongHieu, sp.Anh, sp.DonViTinh, sp.GiaBan,
                       sp.SoLuongTon, sp.HanSuDung
                FROM dbo.SanPham sp
                INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
                WHERE sp.TrangThai = 1 AND sp.MaSP IN ({placeholders})
            """),
            params,
        ).mappings().all()
        return {int(row["MaSP"]): dict(row) for row in rows}

    @classmethod
    def _rank_observation(
        cls,
        observation: VisualObservation,
        image_vectors: list[np.ndarray],
        text_vectors: list[np.ndarray],
    ) -> dict[int, dict[str, float]]:
        scores: dict[int, dict[str, float]] = defaultdict(
            lambda: {"visual": -1.0, "semantic": -1.0}
        )
        for vector in image_vectors:
            for product_id, score in cls._search_index(cls._image_index, vector, "image").items():
                scores[product_id]["visual"] = max(scores[product_id]["visual"], score)
            for product_id, score in cls._search_index(cls._text_index, vector, "text").items():
                scores[product_id]["semantic"] = max(scores[product_id]["semantic"], score)
        for vector in text_vectors:
            for product_id, score in cls._search_index(cls._image_index, vector, "image").items():
                scores[product_id]["semantic"] = max(scores[product_id]["semantic"], score)
            for product_id, score in cls._search_index(cls._text_index, vector, "text").items():
                scores[product_id]["semantic"] = max(scores[product_id]["semantic"], score)
        query_text = observation.search_text
        for product_id, product in cls._products_by_id.items():
            metadata = _product_text(product)
            lexical = max(
                _token_overlap(query_text, str(product.get("TenSP") or "")),
                _token_overlap(query_text, metadata) * 0.8,
            ) if query_text else 0.0
            category_score = (
                _token_overlap(observation.category, str(product.get("DanhMuc") or ""))
                if observation.category else 0.0
            )
            brand_score = 1.0 if (
                observation.brand
                and _normalize_text(observation.brand)
                in _normalize_text(str(product.get("ThuongHieu") or ""))
            ) else 0.0
            existing = scores[product_id]
            existing["lexical"] = lexical
            existing["category"] = category_score
            existing["brand"] = brand_score
        return scores

    @classmethod
    def search(
        cls,
        db: Session,
        image: Image.Image,
        user_query: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        cls.ensure_loaded(db)
        if not cls._products_by_id:
            return {
                "products": [],
                "total_indexed": 0,
                "total_images_indexed": 0,
                "reason": "no_indexed_products",
            }

        normalized = ImageOps.exif_transpose(image).convert("RGB")
        observations, analysis_status = analyze_products_in_image(normalized, user_query)
        detected_observations = list(observations)
        legacy_result = FaissProductIndex.search(
            db,
            normalized,
            top_k=MAX_SEARCH_CANDIDATES,
            min_similarity=0.0,
        )
        resnet_scores = {
            int(item["product_id"]): float(item["similarity"])
            for item in legacy_result.get("matches", [])
        }
        if not observations:
            observations = [
                VisualObservation(
                    name=user_query[:180] if user_query else "",
                    category="",
                    brand="",
                    package_details="",
                    visible_text="",
                    bbox=None,
                )
            ]

        group_inputs: list[tuple[VisualObservation, list[Image.Image]]] = []
        for observation in observations[:6]:
            if observation.bbox is not None:
                group_inputs.append((observation, [cls._crop_for_observation(normalized, observation)]))
            elif analysis_status == "available" and len(observations) > 1:
                group_inputs.append((observation, [normalized]))
            elif len(observations) == 1:
                group_inputs.append((observation, cls._fallback_crops(normalized)))
            else:
                group_inputs.append((observation, [normalized]))

        ranked_by_id: dict[int, dict[str, Any]] = {}
        for observation, query_images in group_inputs:
            encoded_images = encode_images(query_images)
            query_texts = [observation.search_text] if observation.search_text else []
            encoded_texts = encode_texts(query_texts) if query_texts else np.empty((0, 0), dtype=np.float32)
            image_vectors = [vector for vector in encoded_images]
            text_vectors = [vector for vector in encoded_texts]
            with cls._lock:
                ranked = cls._rank_observation(
                    observation, image_vectors, text_vectors
                )
            for product_id, features in ranked.items():
                product = cls._products_by_id.get(product_id)
                if product is None:
                    continue
                visual = max(0.0, features.get("visual", -1.0))
                semantic = max(0.0, features.get("semantic", -1.0))
                lexical = features.get("lexical", 0.0)
                category = features.get("category", 0.0)
                brand = features.get("brand", 0.0)
                resnet = resnet_scores.get(product_id, 0.0)
                score = (
                    0.32 * visual
                    + 0.18 * resnet
                    + 0.22 * semantic
                    + 0.13 * lexical
                    + 0.10 * category
                    + 0.05 * brand
                )
                if score < MIN_RESULT_SCORE:
                    continue
                if visual >= 0.88 and (brand > 0 or lexical >= 0.5 or category > 0):
                    match_type = "closest"
                elif category > 0 and semantic < 0.22:
                    match_type = "substitute"
                else:
                    match_type = "similar"
                reasons = []
                if visual >= 0.5:
                    reasons.append("ảnh có đặc trưng trực quan gần")
                if resnet >= 0.8:
                    reasons.append("đặc trưng hình ảnh bổ sung khớp")
                if lexical >= 0.35:
                    reasons.append("tên hoặc mô tả khớp")
                if category > 0:
                    reasons.append("cùng danh mục")
                if brand > 0:
                    reasons.append("đúng thương hiệu")
                result = {
                    "MaSP": product_id,
                    "similarity": round(max(0.0, features.get("visual", 0.0)), 4),
                    "resnet_similarity": round(resnet, 4),
                    "semantic_similarity": round(semantic, 4),
                    "relevance_score": round(score, 4),
                    "match_type": match_type,
                    "matched_object": observation.name or observation.category or "Sản phẩm",
                    "match_reason": reasons or ["được xếp hạng từ ảnh và dữ liệu sản phẩm"],
                }
                previous = ranked_by_id.get(product_id)
                if previous is None or result["relevance_score"] > previous["relevance_score"]:
                    ranked_by_id[product_id] = result

        ranked_results = sorted(
            ranked_by_id.values(),
            key=lambda item: (-item["relevance_score"], item["MaSP"]),
        )
        search_id = str(uuid.uuid4())
        page_limit = min(max(int(limit), 1), 10)
        live_products = cls._live_products(db, [item["MaSP"] for item in ranked_results])
        enriched = []
        for item in ranked_results:
            product = live_products.get(item["MaSP"])
            if product is None:
                continue
            enriched.append({
                **product,
                **item,
                "Anh": f"/api/products/{item['MaSP']}/image",
                "image_url": f"/api/products/{item['MaSP']}/image",
            })
        SEARCH_RESULT_CACHE.put(search_id, enriched)
        return {
            "matches": [
                {
                    "product_id": item["MaSP"],
                    "similarity": item["similarity"],
                    "semantic_similarity": item["semantic_similarity"],
                    "match_type": item["match_type"],
                }
                for item in enriched[:page_limit]
            ],
            "products": enriched[:page_limit],
            "search_id": search_id,
            "total_results": len(enriched),
            "has_more": len(enriched) > page_limit,
            "total_indexed": len(cls._products_by_id),
            "total_images_indexed": len(cls._image_hashes),
            "analysis_status": analysis_status,
            "observations": [
                {
                    "name": item.name,
                    "category": item.category,
                    "brand": item.brand,
                    "visible_text": item.visible_text,
                }
                for item in detected_observations
            ],
            "reason": None if enriched else "no_confident_candidates",
        }

    @classmethod
    def status(cls) -> dict[str, Any]:
        if not cls._loaded:
            cache = cls._load_cache()
            cached_records = cache.get("images", [])
            cached_product_ids = {
                int(item["MaSP"])
                for item in cached_records
                if isinstance(item, dict) and str(item.get("MaSP", "")).isdigit()
            }
            return {
                "ready": False,
                "model": settings.visual_search_model,
                "pretrained": settings.visual_search_pretrained,
                "products_in_text_index": len(cache.get("text_vectors", {})),
                "products_with_indexed_images": len(cached_product_ids),
                "images_indexed": len(cache.get("image_vectors", {})),
                "failed_images": len(cache.get("errors", [])),
                "built_at": cache.get("built_at"),
                "errors": list(cache.get("errors", [])),
            }
        indexed_product_ids = {
            product_id for product_ids in cls._image_product_ids for product_id in product_ids
        }
        return {
            "ready": cls._loaded,
            "model": settings.visual_search_model,
            "pretrained": settings.visual_search_pretrained,
            "products_in_text_index": len(cls._text_product_ids),
            "products_with_indexed_images": len(indexed_product_ids),
            "images_indexed": len(cls._image_hashes),
            "failed_images": len(cls._errors),
            "built_at": cls._built_at,
            "errors": list(cls._errors),
        }

    @classmethod
    def invalidate(cls) -> None:
        with cls._lock:
            cls._loaded = False
            cls._last_catalog_check = 0.0
            cls._source_signature = ()
            cls._image_index = None
            cls._text_index = None
            cls._image_hashes = []
            cls._image_product_ids = []
            cls._text_product_ids = []
            cls._products_by_id = {}
            cls._image_records = []
            cls._errors = []
            cls._built_at = None


class SearchResultCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def put(self, search_id: str, products: list[dict[str, Any]]) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                key for key, (created, _) in self._entries.items()
                if now - created > SEARCH_CACHE_TTL_SECONDS
            ]
            for key in expired:
                self._entries.pop(key, None)
            while len(self._entries) >= MAX_SEARCH_CACHE_ENTRIES:
                self._entries.pop(next(iter(self._entries)))
            self._entries[search_id] = (now, products)

    def page(
        self, search_id: str, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int] | None:
        with self._lock:
            entry = self._entries.get(search_id)
            if entry is None or time.monotonic() - entry[0] > SEARCH_CACHE_TTL_SECONDS:
                self._entries.pop(search_id, None)
                return None
            return entry[1][offset : offset + limit], len(entry[1])

    def contains_product(self, search_id: str, product_id: int) -> bool:
        with self._lock:
            entry = self._entries.get(search_id)
            return bool(entry and any(item["MaSP"] == product_id for item in entry[1]))


SEARCH_RESULT_CACHE = SearchResultCache()


def get_search_result_page(
    db: Session, search_id: str, offset: int, limit: int
) -> dict[str, Any] | None:
    cached = SEARCH_RESULT_CACHE.page(search_id, offset, limit)
    if cached is None:
        return None
    cached_page, total = cached
    live = VisualSearchEngine._live_products(db, [item["MaSP"] for item in cached_page])
    products = []
    for item in cached_page:
        product = live.get(item["MaSP"])
        if product is not None:
            products.append({
                **product,
                **item,
                "Anh": f"/api/products/{item['MaSP']}/image",
                "image_url": f"/api/products/{item['MaSP']}/image",
            })
    return {
        "products": products,
        "total_results": total,
        "has_more": offset + len(cached_page) < total,
    }


def record_visual_search_event(
    search_id: str,
    duration_ms: float,
    result_count: int,
    analysis_status: str,
) -> None:
    path = settings.faiss_index_dir / "visual_search_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "search",
        "search_id": search_id,
        "timestamp": _utc_now(),
        "duration_ms": round(duration_ms, 2),
        "result_count": result_count,
        "matched": result_count > 0,
        "analysis_status": analysis_status,
    }
    try:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError as exc:
        logger.warning("Cannot record visual search metrics: %s", type(exc).__name__)


def record_visual_search_feedback(
    search_id: str,
    product_id: int | None,
    helpful: bool | None,
    action: str,
) -> bool:
    if not SEARCH_RESULT_CACHE.contains_product(search_id, product_id or -1):
        return False
    path = settings.faiss_index_dir / "visual_search_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "feedback",
        "search_id": search_id,
        "product_id": product_id,
        "helpful": helpful,
        "action": action,
        "timestamp": _utc_now(),
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")
    return True


def visual_search_metrics() -> dict[str, Any]:
    path = settings.faiss_index_dir / "visual_search_events.jsonl"
    searches: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []
    if path.is_file():
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "search":
                    searches.append(event)
                elif event.get("type") == "feedback":
                    feedback.append(event)
    durations = [float(item["duration_ms"]) for item in searches if "duration_ms" in item]
    return {
        "searches": len(searches),
        "matched_searches": sum(bool(item.get("matched")) for item in searches),
        "match_rate": (
            round(sum(bool(item.get("matched")) for item in searches) / len(searches), 4)
            if searches else None
        ),
        "average_search_ms": round(sum(durations) / len(durations), 2) if durations else None,
        "feedback_count": len(feedback),
        "helpful_feedback": sum(item.get("helpful") is True for item in feedback),
        "not_helpful_feedback": sum(item.get("helpful") is False for item in feedback),
        "selected_products": sum(item.get("action") == "selected" for item in feedback),
    }
