from __future__ import annotations

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import types
from pydantic import ValidationError

from backend.app.recipe_service import (
    ClassificationItem,
    GeminiRecipeGenerator,
    RecipeGenerationResponse,
    RecipeIngredientDraft,
    RecipeProviderError,
    _gemini_response_schema,
    _force_safe_classification,
    extract_recipe_product_query,
    is_recipe_question,
    recipe_product_candidates,
)


class RecipeIntentTests(unittest.TestCase):
    def test_extracts_product_name_from_recipe_question(self) -> None:
        question = "Nước rửa chén này nấu được món gì?"
        self.assertTrue(is_recipe_question(question))
        self.assertEqual(extract_recipe_product_query(question), "nuoc rua chen")
        self.assertEqual(extract_recipe_product_query("Có thể chế biến món gì?"), "")

    def test_recipe_candidates_require_product_name_token_match(self) -> None:
        candidates = [
            {"MaSP": 165, "TenSP": "Nước rửa chén Sunlight"},
            {"MaSP": 189, "TenSP": "Miếng rửa chén"},
            {"MaSP": 178, "TenSP": "Nước rửa tay Lifebuoy"},
        ]
        with patch(
            "backend.app.recipe_service.search_products",
            return_value=candidates,
        ):
            matches = recipe_product_candidates(
                Mock(),
                "Nước rửa chén này nấu được món gì?",
            )
        self.assertEqual([item["MaSP"] for item in matches], [165])


class RecipeModelTests(unittest.TestCase):
    def test_household_products_are_forced_to_non_food(self) -> None:
        product = {
            "MaSP": 161,
            "TenSP": "Nước giặt OMO",
            "DanhMuc": "Hóa mỹ phẩm",
            "MoTa": "Nước giặt dùng cho máy giặt.",
        }
        unsafe_classification = ClassificationItem(
            product_id=161,
            classification="COOKING_INGREDIENT",
            is_cookable=True,
            recipe_generation_allowed=True,
            classification_reason="Dữ liệu bị mô hình phân loại nhầm.",
            confidence=0.99,
        )

        classification = _force_safe_classification(product, unsafe_classification)

        self.assertEqual(classification.classification, "NON_FOOD")
        self.assertFalse(classification.is_cookable)
        self.assertFalse(classification.recipe_generation_allowed)

    def test_classification_batch_uses_structured_gemini_output(self) -> None:
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(
                {
                    "items": [
                        {
                            "product_id": 81,
                            "classification": "COOKING_INGREDIENT",
                            "is_cookable": True,
                            "recipe_generation_allowed": True,
                            "classification_reason": "Thịt tươi phù hợp để chế biến.",
                            "confidence": 0.96,
                        }
                    ]
                }
            )
        )
        generator = GeminiRecipeGenerator(client)

        result = generator.classify_batch(
            [
                {
                    "MaSP": 81,
                    "TenSP": "Thịt heo ba chỉ",
                    "DanhMuc": "Thịt và thủy sản",
                    "MoTa": "Thịt ba chỉ heo tươi.",
                    "ThuongHieu": "Vissan",
                    "DonViTinh": "kg",
                }
            ]
        )

        self.assertEqual(result[0].classification, "COOKING_INGREDIENT")
        self.assertTrue(result[0].is_cookable)
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_schema.type, types.Type.OBJECT)

    def test_response_schemas_are_compatible_with_gemini_sdk(self) -> None:
        for schema_model in (ClassificationItem, RecipeGenerationResponse):
            with self.subTest(schema=schema_model.__name__):
                schema = _gemini_response_schema(schema_model)
                self.assertEqual(schema.type, types.Type.OBJECT)

    def test_recipe_ingredient_quantity_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            RecipeIngredientDraft(
                ingredient_name="Thịt heo",
                quantity=Decimal("0"),
                unit="g",
            )

    def test_recipe_generation_requires_primary_product_match(self) -> None:
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(
                {
                    "recipes": [
                        {
                            "category_name": "Món xào",
                            "recipe_name": "Thịt heo xào rau",
                            "description": "Món xào dùng thịt heo làm nguyên liệu chính.",
                            "ingredients": [
                                {
                                    "ingredient_name": "Thịt bò",
                                    "quantity": "300",
                                    "unit": "g",
                                    "is_primary": True,
                                },
                                {
                                    "ingredient_name": "Rau cải",
                                    "quantity": "150",
                                    "unit": "g",
                                    "is_primary": False,
                                },
                            ],
                            "servings": 2,
                            "preparation_time_minutes": 10,
                            "cooking_time_minutes": 15,
                            "difficulty": "easy",
                            "steps": [
                                {
                                    "step_number": 1,
                                    "instruction": "Sơ chế thịt và rau riêng biệt.",
                                },
                                {
                                    "step_number": 2,
                                    "instruction": "Xào chín hoàn toàn rồi dùng ngay.",
                                    "temperature_c": 180,
                                    "duration_minutes": 10,
                                },
                            ],
                            "tips": "Không để thịt sống tiếp xúc với rau đã sơ chế.",
                            "safety_notes": "Rửa tay và dụng cụ sau khi sơ chế thịt sống.",
                        }
                    ],
                    "not_suitable_reason": None,
                }
            )
        )
        generator = GeminiRecipeGenerator(client)
        classification = ClassificationItem(
            product_id=81,
            classification="COOKING_INGREDIENT",
            is_cookable=True,
            recipe_generation_allowed=True,
            classification_reason="Thịt tươi dùng để nấu ăn.",
            confidence=0.96,
        )

        classification = classification.model_copy(
            update={
                "classification": "BEVERAGE",
                "is_cookable": False,
            }
        )
        with self.assertRaisesRegex(
            RecipeProviderError,
            "không gắn đúng nguyên liệu chính",
        ):
            generator.generate_recipes(
                {
                    "MaSP": 81,
                    "TenSP": "Nước cam đóng chai",
                    "DanhMuc": "Đồ uống",
                    "MoTa": "Nước cam đóng chai.",
                },
                classification,
            )

    def test_non_food_never_calls_recipe_generation(self) -> None:
        client = Mock()
        generator = GeminiRecipeGenerator(client)
        classification = ClassificationItem(
            product_id=161,
            classification="NON_FOOD",
            is_cookable=False,
            recipe_generation_allowed=False,
            classification_reason="Sản phẩm giặt tẩy.",
            confidence=1,
        )

        response = generator.generate_recipes(
            {"MaSP": 161, "TenSP": "Nước giặt OMO"},
            classification,
        )

        self.assertEqual(response.recipes, [])
        client.models.generate_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
