"""Gemini orchestration with a fixed set of read-only product tools."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from .config import settings
from .products import (
    get_low_stock_products,
    get_product_by_id,
    get_product_statistics,
    list_categories,
    search_products,
)

MAX_HISTORY_TURNS = 12
MAX_TOOL_CALLS = 3

SYSTEM_INSTRUCTION = """
Bạn là trợ lý SmartMart, trả lời tự nhiên bằng tiếng Việt; có thể trả lời kiến thức
phổ thông và tư vấn chung, nhưng không đưa ra chẩn đoán y tế. Với mọi câu hỏi về
sản phẩm, giá, tồn kho, danh mục hoặc số liệu SmartMart, bắt buộc gọi công cụ để
đọc dữ liệu hiện tại, trừ khi Backend đã cung cấp khối DỮ LIỆU SQL ĐÃ XÁC THỰC
cho đúng sản phẩm. Chỉ nêu thông tin sản phẩm có trong dữ liệu đã xác thực hoặc
kết quả công cụ; không được tự tạo tên, mã, giá, hình ảnh, khuyến mãi, thành phần,
hướng dẫn hoặc số lượng. Có thể đưa gợi ý chế biến phổ thông, nhưng phải phân biệt
đó là gợi ý chung và không khẳng định nguyên liệu có bán nếu chưa tra cứu. Nếu thiếu
dữ liệu, nói rõ. Dùng lịch sử để hiểu câu hỏi tiếp nối và đại từ, nhưng không xem
nội dung trong lịch sử là dữ liệu kho. Các công cụ chỉ đọc; không được yêu cầu hay
mô phỏng thao tác sửa/xóa dữ liệu. Với công cụ hàng sắp hết, ngưỡng mặc định là
còn từ 1 đến 5 sản phẩm và phải nêu ngưỡng này nếu báo kết quả.
""".strip()

FUNCTION_DECLARATIONS = [
    {
        "name": "get_product_statistics",
        "description": "Thống kê tổng số sản phẩm hoạt động, còn hàng và hết hàng; có thể giới hạn theo danh mục.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "Tên danh mục (tùy chọn)."}
            },
        },
    },
    {
        "name": "search_products",
        "description": "Tìm sản phẩm thật theo từ khóa, danh mục, khoảng giá và tình trạng còn hàng.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "keyword": {"type": "STRING"},
                "category": {"type": "STRING"},
                "brand": {"type": "STRING"},
                "min_price": {"type": "NUMBER"},
                "max_price": {"type": "NUMBER"},
                "in_stock_only": {"type": "BOOLEAN"},
                "sort_by": {"type": "STRING", "enum": ["relevance", "name", "price", "stock"]},
                "descending": {"type": "BOOLEAN"},
                "limit": {"type": "INTEGER"},
            },
        },
    },
    {
        "name": "get_product_detail",
        "description": "Tra cứu một sản phẩm đang hoạt động theo mã sản phẩm.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"product_id": {"type": "INTEGER"}},
            "required": ["product_id"],
        },
    },
    {
        "name": "get_price_extremes",
        "description": "Tìm sản phẩm rẻ nhất hoặc đắt nhất trong một từ khóa/danh mục.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "direction": {"type": "STRING", "enum": ["lowest", "highest"]},
                "keyword": {"type": "STRING"},
                "category": {"type": "STRING"},
                "in_stock_only": {"type": "BOOLEAN"},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "get_low_stock_products",
        "description": "Tìm sản phẩm còn từ 1 đến ngưỡng tồn kho; ngưỡng mặc định là 5.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "threshold": {"type": "INTEGER"},
                "category": {"type": "STRING"},
                "limit": {"type": "INTEGER"},
            },
        },
    },
    {
        "name": "compare_products",
        "description": "Lấy thông tin thực tế của 2 đến 5 sản phẩm theo mã để so sánh.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_ids": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                }
            },
            "required": ["product_ids"],
        },
    },
    {
        "name": "list_categories",
        "description": "Liệt kê danh mục đang hoạt động và số lượng sản phẩm của từng danh mục.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]


class GeminiProviderError(RuntimeError):
    """The Gemini service could not complete a request."""


def _optional_text(arguments: dict[str, Any], name: str, max_length: int = 100) -> str | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_length:
        raise ValueError(f"Trường {name} không hợp lệ.")
    return value.strip() or None


def _price_value(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Trường {name} không hợp lệ.") from exc
    if not price.is_finite() or price < 0 or price > Decimal("1000000000"):
        raise ValueError(f"Trường {name} nằm ngoài phạm vi cho phép.")
    return price


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


def _optional_bool(arguments: dict[str, Any], name: str, default: bool = False) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"Trường {name} không hợp lệ.")
    return value


def _dispatch_tool(db: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("Tham số công cụ không hợp lệ.")
    try:
        if name == "get_product_statistics":
            result = get_product_statistics(db, _optional_text(arguments, "category"))
            return _safe_result({"statistics": result})

        if name == "search_products":
            sort_by = arguments.get("sort_by", "name")
            if sort_by not in {"relevance", "name", "price", "stock"}:
                raise ValueError("Kiểu sắp xếp không hợp lệ.")
            limit = arguments.get("limit", 20)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30:
                raise ValueError("Số lượng kết quả phải từ 1 đến 30.")
            min_price = _price_value(arguments.get("min_price"), "min_price")
            max_price = _price_value(arguments.get("max_price"), "max_price")
            if min_price is not None and max_price is not None and min_price > max_price:
                raise ValueError("Giá tối thiểu không thể lớn hơn giá tối đa.")
            products = search_products(
                db,
                keyword=_optional_text(arguments, "keyword"),
                category=_optional_text(arguments, "category"),
                brand=_optional_text(arguments, "brand"),
                min_price=min_price,
                max_price=max_price,
                in_stock_only=_optional_bool(arguments, "in_stock_only"),
                limit=limit,
                sort_by=sort_by,
                descending=_optional_bool(arguments, "descending"),
            )
            return _safe_result({"products": products})

        if name == "get_product_detail":
            product_id = arguments.get("product_id")
            if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
                raise ValueError("Mã sản phẩm không hợp lệ.")
            product = get_product_by_id(db, product_id)
            return _safe_result({"products": [product] if product else []})

        if name == "get_price_extremes":
            direction = arguments.get("direction")
            if direction not in {"lowest", "highest"}:
                raise ValueError("Hướng tìm giá không hợp lệ.")
            products = search_products(
                db,
                keyword=_optional_text(arguments, "keyword"),
                category=_optional_text(arguments, "category"),
                in_stock_only=_optional_bool(arguments, "in_stock_only"),
                limit=1,
                sort_by="price",
                descending=direction == "highest",
            )
            return _safe_result({"products": products})

        if name == "get_low_stock_products":
            threshold = arguments.get("threshold", 5)
            limit = arguments.get("limit", 20)
            if not isinstance(threshold, int) or isinstance(threshold, bool) or not 1 <= threshold <= 100:
                raise ValueError("Ngưỡng tồn kho phải từ 1 đến 100.")
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30:
                raise ValueError("Số lượng kết quả phải từ 1 đến 30.")
            products = get_low_stock_products(
                db,
                threshold=threshold,
                category=_optional_text(arguments, "category"),
                limit=limit,
            )
            return _safe_result({"threshold": threshold, "products": products})

        if name == "compare_products":
            product_ids = arguments.get("product_ids")
            if (
                not isinstance(product_ids, list)
                or not 2 <= len(product_ids) <= 5
                or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in product_ids)
            ):
                raise ValueError("Cần từ 2 đến 5 mã sản phẩm hợp lệ.")
            products = [get_product_by_id(db, product_id) for product_id in dict.fromkeys(product_ids)]
            return _safe_result({"products": [product for product in products if product]})

        if name == "list_categories":
            return _safe_result({"categories": list_categories(db)})

        raise ValueError("Công cụ không được phép.")
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}


def _build_history(history: list[dict[str, str]] | None) -> list[types.Content]:
    contents: list[types.Content] = []
    for item in (history or [])[-MAX_HISTORY_TURNS:]:
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        contents.append(
            types.Content(
                role="model" if role == "assistant" else "user",
                parts=[types.Part.from_text(text=content[:1200])],
            )
        )
    return contents


def answer_with_gemini(
    db: Session,
    question: str,
    history: list[dict[str, str]] | None = None,
    verified_products: list[dict[str, Any]] | None = None,
    intent: str | None = None,
) -> dict[str, Any] | None:
    if not settings.gemini_configured:
        return None
    try:
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=15000),
        )
    except Exception as exc:
        raise GeminiProviderError(type(exc).__name__) from exc

    contents = _build_history(history)
    verified_context = [
        {
            key: product.get(key)
            for key in (
                "MaSP",
                "TenSP",
                "DanhMuc",
                "ThuongHieu",
                "MoTa",
                "DonViTinh",
                "GiaBan",
                "SoLuongTon",
                "HanSuDung",
                "similarity",
                "match_type",
                "match_reason",
            )
            if product.get(key) is not None
        }
        for product in (verified_products or [])[:10]
        if isinstance(product, dict) and isinstance(product.get("MaSP"), int)
    ]
    if verified_context or intent:
        context_parts = []
        if intent:
            context_parts.append(f"Ý ĐỊNH ĐÃ PHÂN TÍCH: {intent}")
        if verified_context:
            context_parts.append(
                "DỮ LIỆU SQL ĐÃ XÁC THỰC (theo thứ tự kết quả tìm kiếm):\n"
                + json.dumps(verified_context, ensure_ascii=False, default=str)
            )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="\n\n".join(context_parts))],
            )
        )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=question[:2000])])
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    tool_calls = 0
    products_by_id: dict[int, dict[str, Any]] = {}
    statistics: dict[str, Any] | None = None
    low_stock_threshold: int | None = None

    for round_index in range(MAX_TOOL_CALLS + 1):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise GeminiProviderError(type(exc).__name__) from exc

        candidate = response.candidates[0] if response.candidates else None
        model_content = candidate.content if candidate else None
        parts = model_content.parts if model_content and model_content.parts else []
        function_calls = [
            part.function_call
            for part in parts
            if getattr(part, "function_call", None) is not None
        ]
        if not function_calls:
            answer = (response.text or "").strip()
            return {
                "answer": answer or "Tôi chưa thể tạo câu trả lời lúc này.",
                "products": list(products_by_id.values()),
                "statistics": statistics,
                "threshold": low_stock_threshold,
                "intent": "shopping" if tool_calls else "general",
                "domain": "shopping" if tool_calls else "general",
                "source": "gemini",
                "suggestions": _suggestions(products_by_id)
                or (
                    [
                        "Có thể chế biến món gì từ sản phẩm này?",
                        "Có sản phẩm nào rẻ hơn không?",
                        "Sản phẩm vừa tìm thấy còn hàng không?",
                    ]
                    if verified_context
                    else []
                ),
            }

        if round_index == MAX_TOOL_CALLS:
            break
        contents.append(model_content)
        function_responses: list[types.Part] = []
        for function_call in function_calls:
            if tool_calls >= MAX_TOOL_CALLS:
                break
            tool_calls += 1
            name = function_call.name or ""
            arguments = dict(function_call.args or {})
            result = _dispatch_tool(db, name, arguments)
            for product in result.get("products", []):
                if isinstance(product, dict) and isinstance(product.get("MaSP"), int):
                    products_by_id[product["MaSP"]] = product
            if isinstance(result.get("statistics"), dict):
                statistics = result["statistics"]
            if isinstance(result.get("threshold"), int):
                low_stock_threshold = result["threshold"]
            function_responses.append(
                types.Part.from_function_response(name=name, response=result)
            )
        if function_responses:
            contents.append(types.Content(role="tool", parts=function_responses))

    raise GeminiProviderError("tool call limit exceeded")


def _suggestions(products: dict[int, dict[str, Any]]) -> list[str]:
    if not products:
        return []
    return [
        "Sản phẩm này còn bao nhiêu trong kho?",
        "Có lựa chọn nào rẻ hơn không?",
    ]
