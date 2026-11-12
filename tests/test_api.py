from __future__ import annotations

import json
import unittest
from pathlib import Path
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.main import app


class ProductApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        gemini = patch("backend.app.main.answer_with_gemini", return_value=None)
        gemini.start()
        self.addCleanup(gemini.stop)

    def test_database_counts_and_categories(self) -> None:
        categories = self.client.get("/api/categories")
        self.assertEqual(categories.status_code, 200)
        self.assertEqual(len(categories.json()), 10)
        self.assertEqual(sum(item["SoLuongSanPham"] for item in categories.json()), 200)

    def test_filter_facets_return_live_database_counts_and_price_range(self) -> None:
        response = self.client.get("/api/filters")
        self.assertEqual(response.status_code, 200)
        filters = response.json()
        self.assertEqual(filters["total_products"], 200)
        self.assertLessEqual(filters["min_price"], filters["max_price"])
        self.assertEqual(sum(item["SoLuongSanPham"] for item in filters["categories"]), 200)
        self.assertTrue(filters["brands"])
        self.assertTrue(all(item["SoLuongSanPham"] > 0 for item in filters["brands"]))

    def test_detail_contains_vietnamese_description_and_image(self) -> None:
        response = self.client.get("/api/products/1")
        self.assertEqual(response.status_code, 200)
        product = response.json()
        self.assertIn("Sữa", product["TenSP"])
        self.assertTrue(product["MoTa"])
        self.assertTrue(product["Anh"])
        self.assertEqual(product["Anh"], "/api/products/1/image")
        self.assertIn("DanhMuc", product)

    def test_unresolved_product_image_uses_placeholder_not_dataset(self) -> None:
        with patch(
            "backend.app.main.get_product_by_id",
            return_value={"MaSP": 5, "Anh": "/api/products/5/image"},
        ):
            response = self.client.get("/api/products/5/image")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-image-source"], "placeholder")
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        self.assertEqual(response.headers["x-image-status"], "unavailable")

    def test_product_image_uses_exact_database_file(self) -> None:
        image_path = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
            / "sua-tuoi-vinamilk-co-duong.jpg"
        )
        self.assertTrue(image_path.is_file())
        response = self.client.get("/api/products/1/image")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-image-source"], "product")
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.content, image_path.read_bytes())
        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_sting_and_7up_use_their_own_project_images(self) -> None:
        image_root = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
        )
        for product_id, image_name in ((30, "sting.jpg"), (34, "7up.jpg")):
            with self.subTest(product_id=product_id):
                image_path = image_root / image_name
                self.assertTrue(image_path.is_file())
                response = self.client.get(f"/api/products/{product_id}/image")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["x-image-source"], "product")
                self.assertEqual(response.content, image_path.read_bytes())

    def test_newly_added_images_are_served_for_their_manifest_product_ids(self) -> None:
        image_root = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
        )
        for product_id, image_name in (
            (5, "sua-dac-ong-tho.jpg"),
            (89, "canh-ga.jpg"),
            (127, "duong-phen.jpg"),
        ):
            with self.subTest(product_id=product_id):
                image_path = image_root / image_name
                self.assertTrue(image_path.is_file())
                response = self.client.get(f"/api/products/{product_id}/image")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["x-image-source"], "product")
                self.assertEqual(response.content, image_path.read_bytes())

    def test_search_name_description_and_utf8(self) -> None:
        name_search = self.client.get("/api/products/search", params={"keyword": "sữa"})
        description_search = self.client.get(
            "/api/products/search",
            params={"keyword": "tiệt trùng"},
        )
        self.assertEqual(name_search.status_code, 200)
        self.assertGreater(len(name_search.json()), 0)
        self.assertRegex(name_search.json()[0]["Anh"], r"^/api/products/\d+/image$")
        self.assertEqual(description_search.status_code, 200)
        self.assertGreater(len(description_search.json()), 0)

    def test_search_ranks_brand_terms_and_common_typos(self) -> None:
        response = self.client.get(
            "/api/products/search",
            params={"keyword": "banh soltie"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["MaSP"], 106)

        branded = self.client.get(
            "/api/products/search",
            params={"keyword": "sua vinamilk", "brand": "Vinamilk"},
        )
        self.assertEqual(branded.status_code, 200)
        self.assertGreater(len(branded.json()), 0)
        self.assertTrue(all(item["ThuongHieu"] == "Vinamilk" for item in branded.json()))

    def test_search_filters_sorting_and_offset_are_applied(self) -> None:
        response = self.client.get(
            "/api/products/search",
            params={
                "keyword": "vinamilk",
                "brand": "Vinamilk",
                "sort_by": "price",
                "order": "asc",
                "limit": 20,
            },
        )
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(
            [item["GiaBan"] for item in items],
            sorted(item["GiaBan"] for item in items),
        )
        page = self.client.get(
            "/api/products/search",
            params={
                "keyword": "vinamilk",
                "brand": "Vinamilk",
                "sort_by": "price",
                "order": "asc",
                "limit": 1,
                "offset": 1,
            },
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["MaSP"], items[1]["MaSP"])

        invalid_range = self.client.get(
            "/api/products/search",
            params={"min_price": 50000, "max_price": 10000},
        )
        self.assertEqual(invalid_range.status_code, 422)

    def test_search_supports_multiple_brands_and_out_of_stock_filter(self) -> None:
        branded = self.client.get(
            "/api/products/search",
            params=[
                ("keyword", "sua"),
                ("brands", "Vinamilk"),
                ("brands", "TH true MILK"),
            ],
        )
        self.assertEqual(branded.status_code, 200)
        self.assertTrue(branded.json())
        self.assertTrue(
            all(item["ThuongHieu"] in {"Vinamilk", "TH true MILK"} for item in branded.json())
        )

        out_of_stock = self.client.get(
            "/api/products/search",
            params={"out_of_stock_only": "true"},
        )
        self.assertEqual(out_of_stock.status_code, 200)
        self.assertTrue(all(item["SoLuongTon"] == 0 for item in out_of_stock.json()))

        conflicting_stock_filters = self.client.get(
            "/api/products/search",
            params={"in_stock_only": "true", "out_of_stock_only": "true"},
        )
        self.assertEqual(conflicting_stock_filters.status_code, 422)

    def test_chat_recent_product_context_uses_actual_sql_inventory(self) -> None:
        with (
            patch("backend.app.assistant.answer_with_gemini", return_value=None),
        ):
            response = self.client.post(
                "/api/chat",
                json={"question": "Còn hàng không?", "recent_product_ids": [8]},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "sql")
        self.assertEqual(payload["products"][0]["MaSP"], 8)
        self.assertIn("còn", payload["answer"])

    def test_natural_chat_and_not_found(self) -> None:
        with (
            patch("backend.app.assistant.answer_with_gemini", return_value=None),
        ):
            chat = self.client.post("/api/chat", json={"question": "sữa", "history": []})
        missing = self.client.get(
            "/api/products/search",
            params={"keyword": "san pham khong ton tai"},
        )
        self.assertEqual(chat.status_code, 200)
        self.assertGreater(len(chat.json()["products"]), 0)
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(missing.json(), [])

    def test_chat_product_count_uses_sql_statistics_without_external_ai(self) -> None:
        with (
            patch("backend.app.assistant.answer_with_gemini", return_value=None),
        ):
            response = self.client.post(
                "/api/chat",
                json={"question": "SmartMart có bao nhiêu sản phẩm?", "history": []},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["statistics"]["total_products"], 200)

    def test_image_search_exact_database_file_ranks_matching_product_first(self) -> None:
        image_path = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
            / "sua-milo.jpg"
        )
        self.assertTrue(image_path.is_file())
        response = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("sua-milo.jpg", image_path.read_bytes(), "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "image_search")
        self.assertEqual(payload["source"], "image_embedding")
        self.assertEqual(payload["products"][0]["MaSP"], 8)
        self.assertEqual(payload["products"][0]["Anh"], "/api/products/8/image")
        self.assertGreater(payload["products"][0]["similarity"], 0.99)
        self.assertNotIn("similarity_pct", payload["products"][0])

    def test_image_search_consults_gemini_with_verified_products_and_prior_history(self) -> None:
        image_path = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
            / "sua-milo.jpg"
        )
        history = [
            {"role": "user", "content": "Tìm sữa Milo"},
            {"role": "assistant", "content": "Mình đã tìm thấy sữa Milo."},
            {"role": "user", "content": "Tìm bằng ảnh"},
        ]
        with patch(
            "backend.app.main.answer_with_gemini",
            return_value={
                "answer": "Mình tìm thấy sữa Milo và có thể gợi ý thêm.",
                "products": [],
                "suggestions": ["Có sản phẩm nào ít ngọt hơn?"],
            },
        ) as gemini:
            response = self.client.post(
                "/api/chat/search-by-image",
                files={"file": ("sua-milo.jpg", image_path.read_bytes(), "image/jpeg")},
                data={"message": "Tìm bằng ảnh", "history": json.dumps(history)},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["consultation_source"], "gemini")
        self.assertEqual(payload["answer"], "Mình tìm thấy sữa Milo và có thể gợi ý thêm.")
        self.assertEqual(payload["products"][0]["MaSP"], 8)
        self.assertEqual(gemini.call_args.args[2], history[:2])
        self.assertEqual(gemini.call_args.kwargs["verified_products"][0]["MaSP"], 8)
        self.assertEqual(gemini.call_args.kwargs["intent"], "image_product_consultation")

    def test_image_search_handles_tilted_and_multi_product_inputs(self) -> None:
        static_dir = Path(__file__).resolve().parents[1] / "backend" / "static"
        milo_path = static_dir / "Images" / "Products" / "sua-milo.jpg"
        dasani_path = static_dir / "Images" / "Products" / "dasani.jpg"

        with Image.open(milo_path) as source:
            tilted = source.convert("RGB").rotate(
                8,
                resample=Image.Resampling.BICUBIC,
                expand=True,
                fillcolor="white",
            )
        tilted_buffer = BytesIO()
        tilted.save(tilted_buffer, format="JPEG")
        tilted_response = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("tilted.jpg", tilted_buffer.getvalue(), "image/jpeg")},
        )
        self.assertEqual(tilted_response.status_code, 200)
        self.assertEqual(tilted_response.json()["products"][0]["MaSP"], 8)

        with Image.open(milo_path) as milo, Image.open(dasani_path) as dasani:
            first = milo.convert("RGB")
            second = dasani.convert("RGB")
            first.thumbnail((300, 300))
            second.thumbnail((300, 300))
            combined = Image.new("RGB", (first.width + second.width, 300), "white")
            combined.paste(first, (0, 0))
            combined.paste(second, (first.width, 0))
        combined_buffer = BytesIO()
        combined.save(combined_buffer, format="JPEG")
        combined_response = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("two-products.jpg", combined_buffer.getvalue(), "image/jpeg")},
        )
        self.assertEqual(combined_response.status_code, 200)
        product_ids = {product["MaSP"] for product in combined_response.json()["products"]}
        self.assertTrue({8, 23}.issubset(product_ids))

        busy_background = Image.new("RGB", (600, 600), "white")
        draw = ImageDraw.Draw(busy_background)
        colors = ("#d72b45", "#1976d2", "#ffc107", "#43a047")
        for y in range(0, 600, 40):
            for x in range(0, 600, 40):
                color = colors[((x // 40) + (y // 40)) % len(colors)]
                draw.rectangle((x, y, x + 39, y + 39), fill=color)
        with Image.open(milo_path) as source:
            centered_product = source.convert("RGB")
            centered_product.thumbnail((300, 300))
        busy_background.paste(
            centered_product,
            ((600 - centered_product.width) // 2, (600 - centered_product.height) // 2),
        )
        background_buffer = BytesIO()
        busy_background.save(background_buffer, format="JPEG")
        background_response = self.client.post(
            "/api/chat/search-by-image",
            files={
                "file": (
                    "complex-background.jpg",
                    background_buffer.getvalue(),
                    "image/jpeg",
                )
            },
        )
        self.assertEqual(background_response.status_code, 200)
        self.assertEqual(background_response.json()["products"][0]["MaSP"], 8)

    def test_image_search_rejects_invalid_and_oversized_images(self) -> None:
        invalid = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("invalid.jpg", b"not an image", "image/jpeg")},
        )
        oversized = self.client.post(
            "/api/chat/search-by-image",
            files={
                "file": (
                    "large.jpg",
                    b"x" * (settings.max_image_size_mb * 1024 * 1024 + 1),
                    "image/jpeg",
                )
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(oversized.status_code, 413)

    def test_image_search_accepts_supported_formats_and_resizes_large_inputs(self) -> None:
        for image_format, media_type, extension in (
            ("JPEG", "image/jpeg", "jpg"),
            ("PNG", "image/png", "png"),
            ("WEBP", "image/webp", "webp"),
        ):
            with self.subTest(image_format=image_format):
                image_buffer = BytesIO()
                source_image = Image.new("RGB", (1400, 900), color="white")
                draw = ImageDraw.Draw(source_image)
                draw.rectangle((260, 100, 1140, 800), fill=(26, 129, 95))
                draw.rectangle((420, 230, 980, 670), fill="white")
                source_image.save(
                    image_buffer,
                    format=image_format,
                )
                with patch(
                    "backend.app.main.VisualSearchEngine.search",
                    return_value={
                        "matches": [],
                        "products": [],
                        "total_indexed": 0,
                        "total_images_indexed": 0,
                        "reason": "no_confident_candidates",
                    },
                ) as search:
                    response = self.client.post(
                        "/api/chat/search-by-image",
                        files={
                            "file": (
                                f"product.{extension}",
                                image_buffer.getvalue(),
                                media_type,
                            )
                        },
                    )

                self.assertEqual(response.status_code, 200)
                normalized_image = search.call_args.args[1]
                self.assertLessEqual(max(normalized_image.size), 1024)
                self.assertEqual(response.json()["products"], [])

    def test_image_search_rejects_unrelated_visual_input(self) -> None:
        image_buffer = BytesIO()
        source_image = Image.new("RGB", (1400, 900), color="white")
        draw = ImageDraw.Draw(source_image)
        draw.rectangle((260, 100, 1140, 800), fill=(26, 129, 95))
        draw.rectangle((420, 230, 980, 670), fill="white")
        source_image.save(image_buffer, format="JPEG")

        response = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("abstract.jpg", image_buffer.getvalue(), "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"], [])
        self.assertEqual(response.json()["reason"], "no_confident_candidates")
        self.assertEqual(
            response.json()["answer"],
            "Hiện tại tôi chưa tìm thấy sản phẩm có hình ảnh đủ tương đồng trong siêu thị. "
            "Bạn có thể thử ảnh rõ hơn hoặc nhập tên sản phẩm để tôi tìm kiếm.",
        )

    def test_image_search_rejects_too_small_and_unsupported_formats(self) -> None:
        tiny_buffer = BytesIO()
        Image.new("RGB", (16, 16)).save(tiny_buffer, format="PNG")
        tiny = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("tiny.png", tiny_buffer.getvalue(), "image/png")},
        )
        gif_buffer = BytesIO()
        Image.new("RGB", (64, 64)).save(gif_buffer, format="GIF")
        unsupported = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("unsupported.gif", gif_buffer.getvalue(), "image/gif")},
        )

        self.assertEqual(tiny.status_code, 400)
        self.assertEqual(unsupported.status_code, 415)

    def test_image_search_rejects_severely_blurred_input(self) -> None:
        image_path = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "static"
            / "Images"
            / "Products"
            / "sua-milo.jpg"
        )
        with Image.open(image_path) as source:
            blurred = source.convert("RGB").filter(ImageFilter.GaussianBlur(5))
        image_buffer = BytesIO()
        blurred.save(image_buffer, format="JPEG")

        response = self.client.post(
            "/api/chat/search-by-image",
            files={"file": ("blurred.jpg", image_buffer.getvalue(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("mờ", response.json()["detail"])

    def test_missing_product_returns_404(self) -> None:
        response = self.client.get("/api/products/999999")
        self.assertEqual(response.status_code, 404)

    def test_default_product_image_is_available(self) -> None:
        response = self.client.get("/api/products/default-image")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        self.assertIn(b"SmartMart", response.content)
        self.assertEqual(response.headers["x-image-status"], "placeholder")

    def test_product_image_endpoint_serves_supported_file_types(self) -> None:
        expected_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        app.dependency_overrides[get_db] = lambda: None
        try:
            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                product_dir = root / "Images" / "Products"
                product_dir.mkdir(parents=True)
                with patch("backend.app.product_images.PRODUCT_IMAGE_ROOT", root):
                    for extension, media_type in expected_types.items():
                        with self.subTest(extension=extension):
                            image_buffer = BytesIO()
                            Image.new("RGB", (2, 2), color=(26, 129, 95)).save(
                                image_buffer,
                                format={
                                    ".jpg": "JPEG",
                                    ".jpeg": "JPEG",
                                    ".png": "PNG",
                                    ".webp": "WEBP",
                                }[extension],
                            )
                            image_bytes = image_buffer.getvalue()
                            (product_dir / f"photo{extension}").write_bytes(image_bytes)
                            with patch(
                                "backend.app.main.get_product_by_id",
                                return_value={
                                    "MaSP": 34,
                                    "Anh": f"Images/Products/photo{extension}",
                                },
                            ):
                                response = self.client.get("/api/products/34/image")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.headers["content-type"], media_type)
                            self.assertEqual(response.content, image_bytes)
                            self.assertEqual(response.headers["x-image-status"], "ok")
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_corrupt_image_file_uses_placeholder(self) -> None:
        app.dependency_overrides[get_db] = lambda: None
        try:
            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                product_dir = root / "Images" / "Products"
                product_dir.mkdir(parents=True)
                (product_dir / "broken.jpg").write_bytes(b"not an image")
                with (
                    patch("backend.app.product_images.PRODUCT_IMAGE_ROOT", root),
                    patch(
                        "backend.app.main.get_product_by_id",
                        return_value={"MaSP": 34, "Anh": "Images/Products/broken.jpg"},
                    ),
                ):
                    response = self.client.get("/api/products/34/image")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "image/svg+xml")
                self.assertEqual(response.headers["x-image-status"], "unavailable")
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_missing_or_unsafe_product_image_uses_placeholder(self) -> None:
        references = (None, "Images/Products/missing.webp", "../../outside.jpg")
        app.dependency_overrides[get_db] = lambda: None
        try:
            for reference in references:
                with self.subTest(reference=reference):
                    with patch(
                        "backend.app.main.get_product_by_id",
                        return_value={"MaSP": 34, "Anh": reference},
                    ):
                        response = self.client.get("/api/products/34/image")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["content-type"], "image/svg+xml")
                    self.assertEqual(response.headers["x-image-status"], "unavailable" if reference else "missing")

            with patch("backend.app.main.get_product_by_id", return_value=None):
                response = self.client.get("/api/products/999999/image")
            self.assertEqual(response.status_code, 404)
        finally:
            app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    unittest.main()
