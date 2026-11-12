from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from backend.app.image_service import FaissProductIndex


class PathBasedImageIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.image_dir = self.root / "Images" / "Products"
        self.image_dir.mkdir(parents=True)
        self.red_path = self.image_dir / "red.jpg"
        self.blue_path = self.image_dir / "blue.jpg"
        Image.new("RGB", (64, 64), color=(240, 20, 20)).save(self.red_path)
        Image.new("RGB", (64, 64), color=(20, 20, 240)).save(self.blue_path)

        self.products = [
            {
                "MaSP": 1,
                "TenSP": "Sản phẩm đỏ",
                "DanhMuc": "Đồ uống",
                "MoTa": "",
                "ThuongHieu": "Smart",
                "Anh": "Images/Products/red.jpg",
                "DonViTinh": "chai",
                "GiaBan": 1000,
                "SoLuongTon": 1,
                "HanSuDung": None,
            },
            {
                "MaSP": 2,
                "TenSP": "Sản phẩm xanh",
                "DanhMuc": "Đồ uống",
                "MoTa": "",
                "ThuongHieu": "Mart",
                "Anh": "Images/Products/blue.jpg",
                "DonViTinh": "chai",
                "GiaBan": 2000,
                "SoLuongTon": 1,
                "HanSuDung": None,
            },
        ]
        self.db = Mock()
        self.db.execute.return_value.mappings.return_value.all.return_value = self.products
        self.cache_path = self.root / "product_image_path_embeddings.json"

        self.patches = [
            patch("backend.app.product_images.PRODUCT_IMAGE_ROOT", self.root),
            patch("backend.app.image_service.FAISS_DIR", self.root),
            patch("backend.app.image_service.EMBEDDING_CACHE_PATH", self.cache_path),
            patch("backend.app.image_service.extract_feature", side_effect=self._feature),
        ]
        self.mocks = [item.start() for item in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)
        FaissProductIndex.invalidate()
        self.addCleanup(FaissProductIndex.invalidate)

    @staticmethod
    def _feature(image: Image.Image) -> np.ndarray:
        red, green, blue = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        vector = np.zeros(512, dtype=np.float32)
        vector[int(np.argmax((red, green, blue)))] = 1.0
        return vector

    def test_exact_path_image_is_ranked_by_cosine_and_uses_sql_metadata(self) -> None:
        with Image.open(self.red_path) as query:
            result = FaissProductIndex.search(self.db, query)

        self.assertEqual(result["products"][0]["MaSP"], 1)
        self.assertEqual(result["products"][0]["Anh"], "/api/products/1/image")
        self.assertEqual(result["products"][0]["similarity"], 1.0)
        self.assertNotIn("similarity_pct", result["products"][0])
        self.assertEqual(result["embedding_model"], "resnet18-imagenet-v1")
        sql = " ".join(str(call.args[0]) for call in self.db.execute.call_args_list)
        self.assertIn("sp.Anh", sql)
        self.assertNotIn("HinhAnh", sql)
        self.assertNotIn("AI_ProductImageEmbedding", sql)
        self.db.commit.assert_not_called()

    def test_unrelated_embedding_below_threshold_returns_no_products(self) -> None:
        FaissProductIndex.build_from_db(self.db)
        query = Image.new("RGB", (64, 64), color=(20, 220, 20))
        result = FaissProductIndex.search(self.db, query)
        self.assertEqual(result["products"], [])
        self.assertEqual(result["reason"], "below_similarity_threshold")

    def test_cached_path_embeddings_are_reused_on_rebuild(self) -> None:
        feature_extractor = self.mocks[-1]
        self.assertEqual(FaissProductIndex.build_from_db(self.db), 2)
        self.assertEqual(feature_extractor.call_count, 2)

        FaissProductIndex.invalidate()
        self.assertEqual(FaissProductIndex.build_from_db(self.db), 2)
        self.assertEqual(feature_extractor.call_count, 2)
        self.assertTrue(self.cache_path.is_file())


if __name__ == "__main__":
    unittest.main()
