from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from google.genai import types

from backend.app.assistant import _resolve_follow_up, answer_question, detect_intent
from backend.app.config import settings
from backend.app.gemini_service import GeminiProviderError, answer_with_gemini, _dispatch_tool
from backend.app.products import get_low_stock_products, get_product_statistics, search_products


class IntentTests(unittest.TestCase):
    def test_vietnamese_and_unaccented_queries(self) -> None:
        self.assertEqual(detect_intent("Xin chào").kind, "greeting")
        self.assertEqual(detect_intent("Toi muon mua sua").keyword, "sua")
        self.assertEqual(detect_intent("Co sua tuoi khong?").kind, "availability")
        self.assertTrue(detect_intent("Co sua tuoi khong?").in_stock_only)
        self.assertEqual(detect_intent("Gia sua bao nhieu?").kind, "price")
        self.assertEqual(detect_intent("Toi co 100 nghin nen mua gi?").max_price, Decimal("100000"))
        self.assertEqual(detect_intent("rau").category, "vegetable")
        self.assertEqual(detect_intent("trái cây").category, "fruit")

    def test_english_and_comparison_queries(self) -> None:
        self.assertEqual(detect_intent("Show me milk products").category, "milk")
        self.assertEqual(detect_intent("Find similar products").kind, "recommendation")
        self.assertEqual(detect_intent("Có thể chế biến món gì?").kind, "recommendation")
        self.assertEqual(detect_intent("Tìm khoai lang").kind, "search")
        self.assertEqual(detect_intent("So sanh sua va nuoc ep").kind, "comparison")

    def test_follow_up_questions_are_not_misclassified_as_product_keywords(self) -> None:
        cheaper = detect_intent("Có loại nào rẻ hơn không?")
        availability = detect_intent("Còn hàng không?")
        self.assertEqual(cheaper.kind, "price")
        self.assertIsNone(cheaper.keyword)
        self.assertEqual(availability.kind, "availability")
        self.assertIsNone(availability.keyword)

        resolved = _resolve_follow_up(
            "Có loại nào rẻ hơn không?",
            [{"role": "user", "content": "Tìm sữa Vinamilk"}],
            cheaper,
        )
        self.assertEqual(resolved.category, "milk")
        self.assertEqual(resolved.keyword, "sua vinamilk")


class ProductQueryTests(unittest.TestCase):
    def test_query_uses_parameters_and_safe_sort(self) -> None:
        db = Mock()
        db.execute.return_value.fetchall.return_value = []

        self.assertEqual(
            search_products(
                db,
                keyword="sua",
                category="milk",
                brand="Vinamilk",
                max_price=Decimal("100000"),
                in_stock_only=True,
                out_of_stock_only=False,
                sort_by="price",
                descending=True,
            ),
            [],
        )
        query, params = db.execute.call_args.args
        query_text = str(query)
        self.assertIn("ORDER BY sp.MaSP ASC", query_text)
        self.assertIn("Vietnamese_CI_AI", query_text)
        self.assertIn("sp.SoLuongTon > 0", query_text)
        self.assertIn("sp.GiaBan <= :max_price", query_text)
        self.assertEqual(params["max_price"], Decimal("100000"))
        self.assertNotIn("100000", query_text)

    def test_multiple_brand_and_out_of_stock_filters_use_bound_parameters(self) -> None:
        db = Mock()
        db.execute.return_value.fetchall.return_value = []

        search_products(
            db,
            brand=["Vinamilk", "TH true MILK"],
            out_of_stock_only=True,
        )

        query, params = db.execute.call_args.args
        query_text = str(query)
        self.assertIn("sp.SoLuongTon = 0", query_text)
        self.assertIn("sp.ThuongHieu COLLATE Vietnamese_CI_AI LIKE :brand_0", query_text)
        self.assertIn("sp.ThuongHieu COLLATE Vietnamese_CI_AI LIKE :brand_1", query_text)
        self.assertEqual(params["brand_0"], "%Vinamilk%")
        self.assertEqual(params["brand_1"], "%TH true MILK%")

    def test_statistics_and_low_stock_use_bound_parameters(self) -> None:
        db = Mock()
        db.execute.return_value.mappings.return_value.one.return_value = {
            "total_products": 8,
            "in_stock_products": 6,
            "out_of_stock_products": 2,
        }
        db.execute.return_value.fetchall.return_value = []

        stats = get_product_statistics(db, category="Sữa")
        query, params = db.execute.call_args.args
        self.assertEqual(stats["total_products"], 8)
        self.assertIn("dm.TenDM COLLATE Vietnamese_CI_AI LIKE :category", str(query))
        self.assertEqual(params, {"category": "%Sữa%"})

        self.assertEqual(get_low_stock_products(db, threshold=4), [])
        query, params = db.execute.call_args.args
        self.assertIn("sp.SoLuongTon BETWEEN 1 AND :threshold", str(query))
        self.assertEqual(params["threshold"], 4)

    def test_tool_dispatch_rejects_untrusted_sort_and_unknown_tool(self) -> None:
        db = Mock()
        self.assertIn("error", _dispatch_tool(db, "search_products", {"sort_by": "MaSP DESC"}))
        self.assertIn("error", _dispatch_tool(db, "run_sql", {"query": "DELETE"}))
        db.execute.assert_not_called()


class GeminiToolCallingTests(unittest.TestCase):
    def test_chat_uses_sql_fallback_when_gemini_is_unavailable(self) -> None:
        product = {
            "MaSP": 8,
            "TenSP": "Sữa cacao Milo 180ml",
            "DanhMuc": "Sữa và chế phẩm",
            "GiaBan": Decimal("10000"),
            "SoLuongTon": 7,
            "DonViTinh": "Hộp",
        }
        with (
            patch(
                "backend.app.assistant.answer_with_gemini",
                side_effect=GeminiProviderError("temporary failure"),
            ),
            patch("backend.app.assistant.search_products", return_value=[product]),
        ):
            result = answer_question(Mock(), "Tìm sữa Milo")

        self.assertEqual(result["source"], "sql")
        self.assertEqual(result["products"], [product])
        self.assertIn("Gemini hiện không khả dụng", result["answer"])

    def test_gemini_receives_only_verified_product_fields_and_intent(self) -> None:
        db = Mock()
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(
            candidates=[],
            text="Sữa Milo đang có hàng.",
        )
        product = {
            "MaSP": 8,
            "TenSP": "Sữa cacao Milo 180ml",
            "DanhMuc": "Sữa và chế phẩm",
            "GiaBan": Decimal("10000"),
            "SoLuongTon": 7,
            "GiaNhap": Decimal("8000"),
            "HinhAnh": b"private-image-data",
        }

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "gemini-test"),
            patch("backend.app.gemini_service.genai.Client", return_value=client),
        ):
            result = answer_with_gemini(
                db,
                "Có thể chế biến món gì?",
                verified_products=[product],
                intent="recommendation",
            )

        self.assertEqual(result["source"], "gemini")
        context = client.models.generate_content.call_args.kwargs["contents"][0]
        context_text = context.parts[0].text
        self.assertIn("Ý ĐỊNH ĐÃ PHÂN TÍCH: recommendation", context_text)
        self.assertIn("Sữa cacao Milo 180ml", context_text)
        self.assertIn("10000", context_text)
        self.assertNotIn("GiaNhap", context_text)
        self.assertNotIn("private-image-data", context_text)

    def test_gemini_function_call_returns_database_statistics(self) -> None:
        db = Mock()
        db.execute.return_value.mappings.return_value.one.return_value = {
            "total_products": 8,
            "in_stock_products": 6,
            "out_of_stock_products": 2,
        }
        model_content = types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="get_product_statistics",
                        args={},
                    )
                )
            ],
        )
        final_content = types.Content(
            role="model",
            parts=[types.Part.from_text(text="SmartMart có 8 sản phẩm đang hoạt động.")],
        )
        client = Mock()
        client.models.generate_content.side_effect = [
            SimpleNamespace(candidates=[SimpleNamespace(content=model_content)], text=None),
            SimpleNamespace(
                candidates=[SimpleNamespace(content=final_content)],
                text="SmartMart có 8 sản phẩm đang hoạt động.",
            ),
        ]

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "gemini-test"),
            patch("backend.app.gemini_service.genai.Client", return_value=client),
        ):
            result = answer_with_gemini(db, "SmartMart có bao nhiêu sản phẩm?")

        self.assertEqual(result["statistics"]["total_products"], 8)
        self.assertEqual(result["source"], "gemini")
        self.assertEqual(client.models.generate_content.call_count, 2)
        tool_content = client.models.generate_content.call_args.kwargs["contents"][-1]
        self.assertEqual(tool_content.role, "tool")

    def test_short_follow_up_reuses_previous_category(self) -> None:
        intent = _resolve_follow_up(
            "Loại nào rẻ nhất?",
            [{"role": "user", "content": "Có những loại sữa nào?"}],
            detect_intent("Loại nào rẻ nhất?"),
        )
        self.assertEqual(intent.kind, "price")
        self.assertEqual(intent.category, "milk")

    def test_stock_follow_up_uses_current_sql_product_values(self) -> None:
        product = {
            "MaSP": 8,
            "TenSP": "Sữa cacao Milo 180ml",
            "DanhMuc": "Sữa và chế phẩm",
            "MoTa": "Sữa cacao.",
            "ThuongHieu": "Milo",
            "Anh": "Images/Products/sua-milo.jpg",
            "DonViTinh": "Hộp",
            "GiaBan": Decimal("10000"),
            "SoLuongTon": 7,
            "HanSuDung": None,
        }
        with (
            patch("backend.app.assistant.get_product_by_id", return_value=product),
            patch("backend.app.assistant.answer_with_gemini", side_effect=AssertionError("must use SQL context")),
        ):
            result = answer_question(
                Mock(),
                "Còn hàng không?",
                recent_product_ids=[8],
            )
        self.assertEqual(result["source"], "sql")
        self.assertEqual(result["products"], [product])
        self.assertIn("còn 7 Hộp", result["answer"])

    def test_recipe_follow_up_uses_live_recent_product(self) -> None:
        product = {
            "MaSP": 8,
            "TenSP": "Sữa cacao Milo 180ml",
            "DanhMuc": "Sữa và chế phẩm",
            "GiaBan": Decimal("10000"),
            "SoLuongTon": 7,
            "DonViTinh": "Hộp",
        }
        with (
            patch("backend.app.assistant.get_product_by_id", return_value=product),
            patch(
                "backend.app.assistant.build_recipe_consultation",
                return_value={
                    "answer": "Có thể dùng sữa trong món ăn.",
                    "products": [product],
                    "recipes": [],
                },
            ) as recipe_lookup,
        ):
            result = answer_question(
                Mock(),
                "Có thể chế biến món gì?",
                history=[{"role": "user", "content": "Tìm sữa Milo"}],
                recent_product_ids=[8],
            )

        self.assertEqual(result["products"], [product])
        self.assertEqual(
            recipe_lookup.call_args.args[2],
            [product],
        )

    def test_cheaper_follow_up_filters_below_recent_sql_products(self) -> None:
        recent_products = [
            {
                "MaSP": 106,
                "TenSP": "Bánh bông lan Solite",
                "DanhMuc": "Bánh kẹo",
                "GiaBan": Decimal("20000"),
                "SoLuongTon": 5,
                "DonViTinh": "Gói",
            }
        ]
        alternatives = [{"MaSP": 101, "TenSP": "Bánh quy Danisa", "GiaBan": Decimal("15000")}]
        with (
            patch("backend.app.assistant.get_product_by_id", return_value=recent_products[0]),
            patch("backend.app.assistant.search_products", return_value=alternatives) as search,
            patch("backend.app.assistant.answer_with_gemini", side_effect=AssertionError("must use SQL context")),
        ):
            result = answer_question(Mock(), "Có loại nào rẻ hơn không?", recent_product_ids=[106])
        self.assertEqual(result["products"], alternatives)
        self.assertEqual(search.call_args.kwargs["category"], "Bánh kẹo")
        self.assertEqual(search.call_args.kwargs["max_price"], Decimal("19999.99"))


if __name__ == "__main__":
    unittest.main()
