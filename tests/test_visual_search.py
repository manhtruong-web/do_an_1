from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import settings
from backend.app.main import app
from backend.app.visual_search import VisualSearchEngine
from backend.app.image_service import FaissProductIndex
from backend.app import vision_analysis
from backend.app.vision_analysis import _parse_bbox


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def fetchall(self):
        return self.rows


class _Session:
    def __init__(self, products):
        self.products = products

    def execute(self, query, params=None):
        statement = str(query)
        if "dbo.SanPhamAnh" in statement:
            return _Result([])
        if "sp.MaSP IN (" in statement:
            ids = set((params or {}).values())
            return _Result([row for row in self.products if row["MaSP"] in ids])
        return _Result(self.products)


class VisualSearchIndexTests(unittest.TestCase):
    def setUp(self):
        VisualSearchEngine.invalidate()

    def tearDown(self):
        VisualSearchEngine.invalidate()

    def test_hash_deduplication_reuses_image_and_text_embeddings(self):
        products = [
            {
                "MaSP": 1,
                "TenSP": "Sữa Milo",
                "DanhMuc": "Sữa",
                "MoTa": "Thức uống cacao",
                "ThuongHieu": "Milo",
                "Anh": "shared.jpg",
                "DonViTinh": "Hộp",
                "GiaBan": 10000,
                "SoLuongTon": 4,
                "HanSuDung": None,
            },
            {
                "MaSP": 2,
                "TenSP": "Milo cacao",
                "DanhMuc": "Đồ uống",
                "MoTa": "Thức uống",
                "ThuongHieu": "Milo",
                "Anh": "shared.jpg",
                "DonViTinh": "Hộp",
                "GiaBan": 12000,
                "SoLuongTon": 3,
                "HanSuDung": None,
            },
        ]
        session = _Session(products)
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "product.jpg"
            Image.new("RGB", (80, 80), "white").save(image_path, format="JPEG")
            with (
                patch.object(settings, "faiss_index_dir", Path(directory)),
                patch("backend.app.visual_search.resolve_product_image_path", return_value=image_path),
                patch(
                    "backend.app.visual_search.encode_images",
                    side_effect=lambda images: np.tile(
                        np.array([[1.0, 0.0]], dtype=np.float32), (len(images), 1)
                    ),
                ) as image_encoder,
                patch(
                    "backend.app.visual_search.encode_texts",
                    side_effect=lambda texts: np.tile(
                        np.array([[1.0, 0.0]], dtype=np.float32), (len(texts), 1)
                    ),
                ) as text_encoder,
            ):
                first = VisualSearchEngine.build_from_db(session)
                self.assertEqual(first["images_indexed"], 1)
                self.assertEqual(first["products_in_text_index"], 2)
                VisualSearchEngine.build_from_db(session)
                self.assertEqual(image_encoder.call_count, 1)
                self.assertEqual(text_encoder.call_count, 1)
                cached = json.loads(
                    (Path(directory) / "visual_product_embeddings.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(len(cached["image_vectors"]), 1)
                self.assertEqual(len(cached["text_vectors"]), 2)

    def test_visual_search_returns_only_catalog_products_with_live_stock(self):
        product = {
            "MaSP": 8,
            "TenSP": "Sữa Milo",
            "DanhMuc": "Sữa và chế phẩm từ sữa",
            "MoTa": "Thức uống cacao",
            "ThuongHieu": "Milo",
            "Anh": "milo.jpg",
            "DonViTinh": "Hộp",
            "GiaBan": 12000,
            "SoLuongTon": 7,
            "HanSuDung": None,
        }
        session = _Session([product])
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "milo.jpg"
            Image.new("RGB", (80, 80), "#1367a2").save(image_path, format="JPEG")
            with (
                patch.object(settings, "faiss_index_dir", Path(directory)),
                patch.object(settings, "visual_search_vision_enabled", False),
                patch("backend.app.visual_search.resolve_product_image_path", return_value=image_path),
                patch(
                    "backend.app.visual_search.encode_images",
                    side_effect=lambda images: np.tile(
                        np.array([[1.0, 0.0]], dtype=np.float32), (len(images), 1)
                    ),
                ),
                patch(
                    "backend.app.visual_search.encode_texts",
                    side_effect=lambda texts: np.tile(
                        np.array([[1.0, 0.0]], dtype=np.float32), (len(texts), 1)
                    ),
                ),
            ):
                result = VisualSearchEngine.search(
                    session,
                    Image.new("RGB", (80, 80), "#1367a2"),
                    user_query="Milo",
                )
        self.assertEqual(result["products"][0]["MaSP"], 8)
        self.assertEqual(result["products"][0]["SoLuongTon"], 7)
        self.assertEqual(result["products"][0]["match_type"], "closest")
        self.assertEqual(result["analysis_status"], "disabled")

    def test_bounding_boxes_are_clamped_by_validation(self):
        self.assertEqual(_parse_bbox([10, 20, 900, 950]), (10, 20, 900, 950))
        self.assertIsNone(_parse_bbox([-1, 0, 1000, 1000]))
        self.assertIsNone(_parse_bbox([20, 20, 20, 40]))
        self.assertIsNone(_parse_bbox(["bad", 0, 1, 1]))

    def test_gemini_vision_uses_structured_product_observations_when_enabled(self):
        class FakeModels:
            def generate_content(self, **kwargs):
                return type(
                    "Response",
                    (),
                    {"text": json.dumps({
                        "objects": [{
                            "product_name": "Sữa Milo",
                            "category": "Sữa",
                            "brand": "Milo",
                            "package_details": "hộp màu nâu",
                            "visible_text": "MILO",
                            "bbox": [100, 120, 800, 900],
                        }]
                    })},
                )()

        fake_client = type("Client", (), {"models": FakeModels()})()
        with (
            patch.object(settings, "visual_search_vision_enabled", True),
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(
                vision_analysis.genai,
                "Client",
                side_effect=lambda **kwargs: fake_client,
            ),
        ):
            observations, status = vision_analysis.analyze_products_in_image(
                Image.new("RGB", (80, 80), "white")
            )
        self.assertEqual(status, "available")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].brand, "Milo")
        self.assertEqual(observations[0].bbox, (100, 120, 800, 900))


class VisualSearchAdminAuthTests(unittest.TestCase):
    def test_admin_api_requires_configured_token(self):
        client = TestClient(app)
        with patch.object(settings, "admin_api_token", "test-token"):
            unauthorized = client.get("/api/admin/visual-search/errors")
            authorized = client.get(
                "/api/admin/visual-search/errors",
                headers={"X-Admin-Token": "test-token"},
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_admin_api_fails_closed_when_token_is_missing(self):
        client = TestClient(app)
        with patch.object(settings, "admin_api_token", ""):
            response = client.get("/api/admin/visual-search/errors")
        self.assertEqual(response.status_code, 503)


class ProductImageIndexSourceTests(unittest.TestCase):
    def test_dataset_image_is_not_used_when_catalog_image_is_missing(self):
        with patch(
            "backend.app.image_service.resolve_product_image_path",
            return_value=None,
        ):
            sources, signature = FaissProductIndex._resolve_sources(
                [{"MaSP": 8, "TenSP": "Sữa Milo", "DanhMuc": "Sữa", "Anh": "missing.jpg"}]
            )

        self.assertEqual(sources, [])
        self.assertEqual(signature, ())
