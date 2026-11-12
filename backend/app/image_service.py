"""Tìm sản phẩm bằng cosine similarity trên embedding của ảnh lưu theo đường dẫn."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .model import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME, extract_feature
from .product_images import (
    ALLOWED_IMAGE_TYPES,
    DEFAULT_PRODUCT_IMAGE,
    resolve_product_image_path,
)

logger = logging.getLogger(__name__)

FAISS_DIR = settings.faiss_index_dir
EMBEDDING_CACHE_PATH = FAISS_DIR / "product_image_path_embeddings.json"
MIN_IMAGE_COSINE = 0.88
MAX_RETURN_SCORE_GAP = 0.08
AMBIGUOUS_SCORE_MARGIN = 0.025

FALLBACK_SVG = DEFAULT_PRODUCT_IMAGE


def get_default_system_image(db: Session) -> tuple[bytes, str]:
    """Trả placeholder nội bộ; ảnh sản phẩm chỉ được đọc theo đường dẫn SQL."""
    return FALLBACK_SVG, "image/svg+xml"


def get_product_image(db: Session, product_id: int) -> tuple[bytes, str]:
    """Đọc ảnh từ đường dẫn Anh, không dùng cột VARBINARY legacy HinhAnh."""
    row = db.execute(
        text("""
            SELECT sp.Anh, sp.TenSP, dm.TenDM AS DanhMuc
            FROM dbo.SanPham sp
            INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
            WHERE sp.MaSP = :pid AND sp.TrangThai = 1
        """),
        {"pid": product_id},
    ).fetchone()
    if row:
        path = resolve_product_image_path(str(row[0])) if row[0] else None
        if path is not None:
            return path.read_bytes(), ALLOWED_IMAGE_TYPES[path.suffix.lower()]
    return get_default_system_image(db)


class FaissProductIndex:
    """FAISS index từ file ảnh của sản phẩm, cache embedding theo hash nội dung."""

    _index: faiss.IndexFlatIP | None = None
    _masp_list: list[int] = []
    _products_by_id: dict[int, dict[str, Any]] = {}
    _source_signature: tuple[tuple[int, str, int, int], ...] = ()
    _loaded = False
    _dim = EMBEDDING_DIMENSIONS

    @classmethod
    def _query_views(cls, query_image: Image.Image) -> list[Image.Image]:
        image = ImageOps.exif_transpose(query_image).convert("RGB")
        views = [
            image,
            image.rotate(-12, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white"),
            image.rotate(-8, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white"),
            image.rotate(8, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white"),
            image.rotate(12, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white"),
        ]
        width, height = image.size
        if width >= height * 1.25:
            for fraction in (0.68, 0.5):
                crop_width = max(32, int(width * fraction))
                for left in sorted({0, (width - crop_width) // 2, width - crop_width}):
                    views.append(image.crop((left, 0, left + crop_width, height)))
        elif height >= width * 1.25:
            for fraction in (0.68, 0.5):
                crop_height = max(32, int(height * fraction))
                for top in sorted({0, (height - crop_height) // 2, height - crop_height}):
                    views.append(image.crop((0, top, width, top + crop_height)))
        else:
            crop_width = max(32, int(width * 0.68))
            crop_height = max(32, int(height * 0.68))
            horizontal = sorted({0, (width - crop_width) // 2, width - crop_width})
            vertical = sorted({0, (height - crop_height) // 2, height - crop_height})
            for top in vertical:
                for left in horizontal:
                    views.append(
                        image.crop((left, top, left + crop_width, top + crop_height))
                    )
            center_width = max(32, width // 2)
            center_height = max(32, height // 2)
            left = (width - center_width) // 2
            top = (height - center_height) // 2
            views.append(
                image.crop((left, top, left + center_width, top + center_height))
            )
        return views

    @classmethod
    def _load_embedding_cache(cls) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(EMBEDDING_CACHE_PATH.read_text(encoding="utf-8"))
            if payload.get("model") != EMBEDDING_MODEL_NAME:
                return {}
            entries = payload.get("embeddings", {})
            return entries if isinstance(entries, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Không thể đọc cache embedding ảnh: %s", type(exc).__name__)
            return {}

    @classmethod
    def _save_embedding_cache(cls, entries: dict[str, dict[str, Any]]) -> None:
        try:
            FAISS_DIR.mkdir(parents=True, exist_ok=True)
            temporary_path = EMBEDDING_CACHE_PATH.with_suffix(".tmp")
            payload = {"model": EMBEDDING_MODEL_NAME, "embeddings": entries}
            temporary_path.write_text(
                json.dumps(payload, separators=(",", ":"), allow_nan=False),
                encoding="utf-8",
            )
            temporary_path.replace(EMBEDDING_CACHE_PATH)
        except OSError as exc:
            logger.warning("Không thể lưu cache embedding ảnh: %s", type(exc).__name__)

    @classmethod
    def _fetch_product_rows(cls, db: Session) -> list[dict[str, Any]]:
        rows = db.execute(
            text("""
                SELECT sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
                       sp.MoTa, sp.ThuongHieu, sp.Anh, sp.DonViTinh,
                       sp.GiaBan, sp.SoLuongTon, sp.HanSuDung
                FROM dbo.SanPham sp
                INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
                WHERE sp.TrangThai = 1 AND sp.Anh IS NOT NULL
                ORDER BY sp.MaSP
            """)
        ).mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    def _resolve_sources(
        cls, products: list[dict[str, Any]]
    ) -> tuple[list[tuple[dict[str, Any], Path]], tuple[tuple[int, str, int, int], ...]]:
        sources = []
        signature = []
        for product in products:
            path = resolve_product_image_path(product.get("Anh"))
            if path is None:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            product_id = int(product["MaSP"])
            sources.append((product, path))
            signature.append((product_id, str(path), stat.st_size, stat.st_mtime_ns))
        return sources, tuple(signature)

    @classmethod
    def build_from_db(cls, db: Session) -> int:
        """Tạo index từ đường dẫn Anh và chỉ suy luận lại ảnh đã đổi nội dung."""
        products = cls._fetch_product_rows(db)
        sources, signature = cls._resolve_sources(products)
        old_cache = cls._load_embedding_cache()
        cache: dict[str, dict[str, Any]] = {}
        vectors: list[np.ndarray] = []
        product_ids: list[int] = []
        products_by_id: dict[int, dict[str, Any]] = {}

        for product, path in sources:
            product_id = int(product["MaSP"])
            try:
                image_bytes = path.read_bytes()
                content_hash = hashlib.sha256(image_bytes).hexdigest()
                cache_key = str(product_id)
                saved = old_cache.get(cache_key, {})
                vector = None

                if (
                    saved.get("hash") == content_hash
                    and saved.get("model") == EMBEDDING_MODEL_NAME
                ):
                    candidate = np.asarray(saved.get("vector"), dtype=np.float32)
                    if candidate.ndim == 1 and candidate.size == cls._dim:
                        norm = np.linalg.norm(candidate)
                        if np.isfinite(candidate).all() and norm > 0:
                            vector = candidate / norm

                if vector is None:
                    with Image.open(io.BytesIO(image_bytes)) as image:
                        image.load()
                        vector = extract_feature(ImageOps.exif_transpose(image)).astype(np.float32)
                    norm = np.linalg.norm(vector)
                    if (
                        vector.ndim != 1
                        or vector.size != cls._dim
                        or not np.isfinite(vector).all()
                        or norm == 0
                    ):
                        logger.warning("Bỏ qua embedding không hợp lệ MaSP=%d", product_id)
                        continue
                    vector = vector / norm

                cache[cache_key] = {
                    "hash": content_hash,
                    "model": EMBEDDING_MODEL_NAME,
                    "vector": vector.tolist(),
                }
                vectors.append(vector)
                product_ids.append(product_id)
                products_by_id[product_id] = product
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Không thể tạo embedding cho MaSP=%d: %s",
                    product_id,
                    type(exc).__name__,
                )

        cls._index = None
        cls._masp_list = product_ids
        cls._products_by_id = products_by_id
        cls._source_signature = signature
        if vectors:
            matrix = np.stack(vectors).astype(np.float32)
            faiss.normalize_L2(matrix)
            cls._index = faiss.IndexFlatIP(matrix.shape[1])
            cls._index.add(matrix)
            cls._dim = matrix.shape[1]
        cls._loaded = True
        cls._save_embedding_cache(cache)

        logger.info(
            "Đã build image embedding index từ %d/%d đường dẫn ảnh",
            len(product_ids),
            len(products),
        )
        return len(product_ids)

    @classmethod
    def ensure_loaded(cls, db: Session) -> None:
        """Phát hiện thay đổi sản phẩm/ảnh mà không tính lại embedding còn nguyên."""
        products = cls._fetch_product_rows(db)
        sources, signature = cls._resolve_sources(products)
        if cls._loaded and signature == cls._source_signature:
            cls._products_by_id = {
                int(product["MaSP"]): product for product, _ in sources
            }
            return
        cls.build_from_db(db)

    @classmethod
    def search(
        cls,
        db: Session,
        query_image: Image.Image,
        top_k: int = 5,
        min_similarity: float = MIN_IMAGE_COSINE,
    ) -> dict[str, Any]:
        """Xếp hạng bằng cosine và loại kết quả yếu hoặc quá mơ hồ."""
        cls.ensure_loaded(db)
        if cls._index is None or cls._index.ntotal == 0:
            return {
                "matches": [],
                "products": [],
                "total_indexed": 0,
                "reason": "no_indexed_images",
            }

        query_vectors = []
        for view in cls._query_views(query_image):
            query_vector = extract_feature(view).astype(np.float32)
            norm = np.linalg.norm(query_vector)
            if (
                query_vector.ndim == 1
                and query_vector.size == cls._dim
                and np.isfinite(query_vector).all()
                and norm > 0
            ):
                query_vectors.append(query_vector / norm)
        if not query_vectors:
            return {
                "matches": [],
                "products": [],
                "total_indexed": cls._index.ntotal,
                "reason": "invalid_embedding",
            }
        query_matrix = np.stack(query_vectors).astype(np.float32)
        actual_k = min(max(int(top_k), 1), 10, cls._index.ntotal)
        scores, indices = cls._index.search(query_matrix, actual_k)
        best_score_by_index: dict[int, float] = {}
        for view_scores, view_indices in zip(scores, indices):
            for score, index in zip(view_scores, view_indices):
                if 0 <= index < len(cls._masp_list):
                    best_score_by_index[int(index)] = max(
                        best_score_by_index.get(int(index), -1.0),
                        float(score),
                    )
        ranked = [
            (score, index)
            for index, score in best_score_by_index.items()
        ]
        ranked.sort(reverse=True)

        if not ranked or ranked[0][0] < min_similarity:
            return {
                "matches": [],
                "products": [],
                "total_indexed": cls._index.ntotal,
                "best_similarity": round(ranked[0][0], 4) if ranked else None,
                "reason": "below_similarity_threshold",
            }
        if (
            len(ranked) > 1
            and ranked[0][0] < 0.96
            and ranked[0][0] - ranked[1][0] < AMBIGUOUS_SCORE_MARGIN
        ):
            return {
                "matches": [],
                "products": [],
                "total_indexed": cls._index.ntotal,
                "best_similarity": round(ranked[0][0], 4),
                "reason": "ambiguous_match",
            }

        matches = []
        sorted_products = []
        best_score = ranked[0][0]
        for similarity, index in ranked:
            if (
                similarity < min_similarity
                or best_score - similarity > MAX_RETURN_SCORE_GAP
            ):
                continue
            product_id = cls._masp_list[index]
            product = cls._products_by_id.get(product_id)
            if product is None:
                continue
            image_url = f"/api/products/{product_id}/image"
            product_result = dict(product)
            product_result["similarity"] = round(similarity, 4)
            product_result["Anh"] = image_url
            product_result["image_url"] = image_url
            sorted_products.append(product_result)
            matches.append({
                "product_id": product_id,
                "similarity": round(similarity, 4),
                "image_url": image_url,
            })

        return {
            "matches": matches,
            "products": sorted_products,
            "total_indexed": cls._index.ntotal,
            "reason": None,
            "embedding_model": EMBEDDING_MODEL_NAME,
        }

    @classmethod
    def invalidate(cls) -> None:
        """Buộc kiểm tra lại đường dẫn ảnh, giữ nguyên cache embedding trên đĩa."""
        cls._index = None
        cls._masp_list = []
        cls._products_by_id = {}
        cls._source_signature = ()
        cls._loaded = False
        logger.info("Đã vô hiệu hóa image index trong bộ nhớ.")

    @classmethod
    def add_or_update_product(cls, db: Session, masp: int) -> bool:
        """Làm mới cache sau khi đường dẫn ảnh của sản phẩm được cập nhật."""
        row = db.execute(
            text("SELECT Anh FROM dbo.SanPham WHERE MaSP = :pid AND TrangThai = 1"),
            {"pid": masp},
        ).fetchone()
        if not row or not resolve_product_image_path(row[0]):
            return False
        cls.invalidate()
        cls.ensure_loaded(db)
        return int(masp) in cls._products_by_id


def sync_product_image_embeddings(db: Session) -> int:
    """Đồng bộ embedding từ file Anh, không ghi vào bảng sản phẩm hay SQL cache cũ."""
    FaissProductIndex.invalidate()
    return FaissProductIndex.build_from_db(db)


class ProductImageSearchEngine:
    """API tương thích ngược cho các caller cũ."""

    _cache_embeddings = None
    _cache_masp: list[int] = []

    @classmethod
    def load_cache(cls, db: Session, force: bool = False) -> None:
        if force:
            FaissProductIndex.invalidate()
        FaissProductIndex.ensure_loaded(db)

    @classmethod
    def search(
        cls,
        db: Session,
        query_image: Image.Image,
        top_k: int = 5,
        min_similarity: float = MIN_IMAGE_COSINE,
    ) -> dict[str, Any]:
        return FaissProductIndex.search(
            db,
            query_image,
            top_k=top_k,
            min_similarity=min_similarity,
        )


class ImageIndex:
    """API tương thích ngược cho image search cũ."""

    def __init__(self, index_dir: Any = None):
        self.index_dir = index_dir

    def search(self, image: Image.Image, top_k: int = 5) -> list[dict[str, Any]]:
        from .database import SessionLocal

        if SessionLocal is None:
            raise RuntimeError("DATABASE_URL chưa được cấu hình.")
        with SessionLocal() as db:
            result = FaissProductIndex.search(db, image, top_k=top_k)
            return result["matches"]
