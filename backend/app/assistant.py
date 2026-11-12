"""Chatbot siêu thị có phân tích ý định và trả lời dựa trên SQL Server."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy.orm import Session

from .gemini_service import GeminiProviderError, answer_with_gemini
from .products import (
    get_low_stock_products,
    get_product_by_id,
    get_product_statistics,
    search_products,
)
from .recipe_service import build_recipe_consultation, is_recipe_question

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "cho", "toi", "tôi", "hoi", "hỏi", "biet", "biết", "xin", "vui", "long",
    "lòng", "co", "có", "khong", "không", "san", "sản", "pham", "phẩm",
    "nao", "nào", "giup", "giúp", "tu", "tư", "van", "vấn", "gia", "giá",
    "bao", "bao", "nhieu", "nhiêu", "mot", "một", "loai", "loại", "con",
    "còn", "hang", "hàng", "voi", "với", "ngan", "ngân", "sach", "sách",
    "muon", "muốn", "mua", "show", "me", "the", "san", "pham", "product",
    "products", "what", "is", "do", "you", "have", "find", "please", "can",
    "gi", "gì", "loai", "loại", "nhe", "nhé", "nao", "nào",
    "nen", "nên", "sanh", "và", "va", "similar", "similarity", "nghin",
    "ngan", "dong", "trieu", "k", "d",
    "nhung", "những", "re", "rẻ", "nhat", "nhất", "dat", "đắt",
    "cao", "thap", "thấp", "kia", "nay", "no", "nó", "do", "đó",
    "kho", "kho?", "trong", "cua", "của", "hon", "dang", "thap", "tim", "tai",
    "dat", "nhat", "con", "ton", "hang", "gia", "them", "nua",
}


@dataclass(frozen=True)
class ChatIntent:
    kind: str
    keyword: str | None = None
    max_price: Decimal | None = None
    min_price: Decimal | None = None
    in_stock_only: bool = False
    category: str | None = None
    sort_by: str = "name"
    descending: bool = False


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()


def _extract_budget(question: str) -> Decimal | None:
    normalized = _normalized(question).replace(".", "").replace(",", "")
    match = re.search(r"(\d+(?:\s*\d{3})?)\s*(trieu|tr|k|nghin|ngan|dong|d)?", normalized)
    if not match:
        return None
    amount = Decimal(match.group(1).replace(" ", ""))
    unit = match.group(2) or ""
    if unit in {"trieu", "tr"}:
        amount *= 1_000_000
    elif unit in {"k", "nghin", "ngan"}:
        amount *= 1_000
    return amount


def _extract_keyword(question: str) -> str | None:
    words = re.findall(r"[a-zA-ZÀ-ỹ0-9-]+", question)
    useful = [
        _normalized(word)
        for word in words
        if _normalized(word) not in {_normalized(item) for item in STOP_WORDS}
        and not _normalized(word).isdigit()
        and len(word) > 2
    ]
    return " ".join(useful[:4]) or None


def detect_intent(question: str) -> ChatIntent:
    normalized = _normalized(question)
    budget = _extract_budget(question)
    keyword = _extract_keyword(question)
    category = next(
        (
            value
            for aliases, value in (
                (("trai cay", "fruit", "hoa qua"), "fruit"),
                (("rau", "rau cu", "vegetable", "vegetables"), "vegetable"),
                (("thit", "meat"), "meat"),
                (("ca", "fish", "hai san"), "fish"),
                (("banh keo", "banh", "keo", "candy"), "candy"),
                (("do uong", "nuoc uong", "juice"), "juice"),
                (("nuoc ngot", "nuoc giai khat"), "juice"),
                (("sua", "milk", "dairy"), "milk"),
            )
            if any(alias in normalized for alias in aliases)
        ),
        None,
    )
    if any(word in normalized for word in ("xin chao", "hello", "chao ban", "cam on")):
        return ChatIntent("greeting")
    if "so sanh" in normalized or "khac nhau" in normalized:
        return ChatIntent("comparison", keyword=keyword, category=category, sort_by="price")
    if any(phrase in normalized for phrase in ("re hon", "gia re hon", "re nhat", "thap nhat", "gia thap hon")):
        return ChatIntent("price", keyword=keyword, category=category, sort_by="price")
    if any(phrase in normalized for phrase in ("dat hon", "dat nhat", "cao nhat", "gia cao hon")):
        return ChatIntent("price", keyword=keyword, category=category, sort_by="price", descending=True)
    if (
        "con hang" in normalized
        or "ton kho" in normalized
        or "trong kho" in normalized
        or "co ban khong" in normalized
        or "co hang khong" in normalized
        or "con san pham" in normalized
        or (
            "co " in normalized
            and " khong" in normalized
            and not any(phrase in normalized for phrase in ("re hon", "gia re hon"))
        )
    ):
        return ChatIntent("availability", keyword=keyword, category=category, in_stock_only=True)
    if "gia" in normalized or "bao nhieu" in normalized:
        return ChatIntent("price", keyword=keyword, category=category, sort_by="price")
    if budget is not None and any(
        word in normalized
        for word in ("ngan sach", "duoi", "trong tam", "phu hop", "nen mua", "mua gi")
    ):
        return ChatIntent("budget", keyword=keyword, category=category, max_price=budget, in_stock_only=True, sort_by="price")
    if any(word in normalized for word in ("goi y", "tu van", "phu hop", "thay the", "tuong tu", "similar")):
        return ChatIntent("recommendation", keyword=keyword, category=category, in_stock_only=True)
    if (
        any(
            phrase in normalized
            for phrase in (
                "che bien",
                "mon an",
                "su dung",
                "bao quan",
                "cong thuc",
            )
        )
        or re.search(r"\b(?:nau|nuong|chien|xao|kho|rim|luoc|ham|recipe|cook)\b", normalized)
    ):
        return ChatIntent("recommendation", category=category, in_stock_only=True)
    return ChatIntent("search", keyword=keyword, category=category)


def _resolve_follow_up(
    question: str,
    history: list[dict[str, str]] | None,
    intent: ChatIntent,
) -> ChatIntent:
    normalized = _normalized(question)
    is_follow_up = any(
        phrase in normalized
        for phrase in (
            "re hon", "re nhat", "dat hon", "dat nhat", "cao nhat",
            "thap nhat", "ton kho", "trong kho", "con hang", "con san pham",
            "co hang khong", "loai nao", "them lua chon", "con lua chon",
            "bao nhieu",
        )
    )
    if not is_follow_up:
        return intent
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        previous = detect_intent(item.get("content", ""))
        if previous.kind != "greeting" and (previous.category or previous.keyword):
            return replace(
                intent,
                category=intent.category or previous.category,
                keyword=intent.keyword or previous.keyword,
            )
    return intent


def _statistics_answer(question: str, statistics: dict[str, Any]) -> str:
    normalized = _normalized(question)
    if "het hang" in normalized:
        return f"Hiện có {statistics['out_of_stock_products']} sản phẩm hết hàng."
    if "con hang" in normalized or "ton kho" in normalized:
        return f"Hiện có {statistics['in_stock_products']} sản phẩm còn hàng."
    return f"SmartMart hiện có {statistics['total_products']} sản phẩm đang hoạt động."


def _format_money(value: Any) -> str:
    return f"{Decimal(str(value)):,.0f}".replace(",", ".") + " đồng"


def _deterministic_answer(intent: ChatIntent, products: list[dict[str, Any]]) -> str:
    if intent.kind == "greeting":
        return "Xin chào! Tôi có thể tra giá, tồn kho, tìm sản phẩm theo ngân sách và tư vấn sản phẩm đang có bán."
    if not products:
        if intent.kind == "budget" and intent.max_price is not None:
            return f"Hiện chưa tìm thấy sản phẩm đang còn hàng trong ngân sách {_format_money(intent.max_price)}."
        return "Tôi chưa tìm thấy sản phẩm phù hợp trong dữ liệu siêu thị. Bạn có thể thử tên hoặc danh mục cụ thể hơn."
    if intent.kind == "price":
        return "\n".join(
            f"- {item['TenSP']}: {_format_money(item['GiaBan'])}; "
            f"{'còn hàng' if item['SoLuongTon'] > 0 else 'hết hàng'}."
            for item in products[:10]
        )
    if intent.kind == "availability":
        return "\n".join(
            f"- {item['TenSP']}: {'còn ' + str(item['SoLuongTon']) + ' sản phẩm' if item['SoLuongTon'] > 0 else 'hết hàng'}."
            for item in products[:10]
        )
    if intent.kind == "budget":
        return "Các sản phẩm đang còn hàng phù hợp ngân sách:\n" + "\n".join(
            f"- {item['TenSP']}: {_format_money(item['GiaBan'])}."
            for item in products[:10]
        )
    if intent.kind == "comparison":
        return "Các sản phẩm để bạn so sánh theo giá:\n" + "\n".join(
            f"- {item['TenSP']}: {_format_money(item['GiaBan'])}; "
            f"{'còn hàng' if item['SoLuongTon'] > 0 else 'hết hàng'}."
            for item in products[:10]
        )
    return "Tôi tìm thấy các sản phẩm phù hợp:\n" + "\n".join(
        f"- {item['TenSP']} ({item['DanhMuc']}): {_format_money(item['GiaBan'])}; "
        f"{'còn hàng' if item['SoLuongTon'] > 0 else 'hết hàng'}."
        for item in products[:10]
    )


def answer_question(
    db: Session,
    question: str,
    history: list[dict[str, str]] | None = None,
    recent_product_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Trả về câu trả lời và nguồn sản phẩm để frontend hiển thị minh bạch."""
    intent = _resolve_follow_up(question, history, detect_intent(question))
    normalized = _normalized(question)
    recent_products = []
    if recent_product_ids:
        for product_id in dict.fromkeys(recent_product_ids[:30]):
            if isinstance(product_id, int) and not isinstance(product_id, bool) and product_id > 0:
                product = get_product_by_id(db, product_id)
                if product:
                    recent_products.append(product)
    if is_recipe_question(question):
        return build_recipe_consultation(db, question, recent_products)
    if recent_products and intent.kind == "availability":
        if any(phrase in normalized for phrase in ("dau tien", "thu nhat", "san pham nay")):
            recent_products = recent_products[:1]
        elif any(phrase in normalized for phrase in ("thu hai", "san pham thu hai")):
            recent_products = recent_products[1:2]
        if recent_products:
            return {
                "answer": "Tồn kho hiện tại của các sản phẩm vừa gợi ý:\n" + "\n".join(
                    f"- {item['TenSP']}: "
                    f"{'còn ' + str(item['SoLuongTon']) + ' ' + str(item['DonViTinh'] or 'sản phẩm') if item['SoLuongTon'] > 0 else 'đã hết hàng'}."
                    for item in recent_products
                ),
                "products": recent_products,
                "intent": "availability",
                "source": "sql",
            }
    if recent_products and any(
        phrase in normalized for phrase in ("re hon", "gia re hon", "re nhat", "thap nhat")
    ):
        cheapest_price = min(Decimal(str(item["GiaBan"])) for item in recent_products)
        categories = {item.get("DanhMuc") for item in recent_products}
        category_filter = next(iter(categories)) if len(categories) == 1 else intent.category
        cheaper_products = search_products(
            db,
            category=category_filter,
            max_price=cheapest_price - Decimal("0.01"),
            in_stock_only=True,
            limit=10,
            sort_by="price",
        )
        return {
            "answer": (
                "Các lựa chọn còn hàng có giá thấp hơn sản phẩm vừa xem:\n"
                + "\n".join(
                    f"- {item['TenSP']}: {_format_money(item['GiaBan'])}."
                    for item in cheaper_products
                )
                if cheaper_products
                else "Tôi chưa tìm thấy lựa chọn cùng danh mục có giá thấp hơn trong kho hiện tại."
            ),
            "products": cheaper_products,
            "intent": "recommendation",
            "source": "sql",
        }

    gemini_unavailable = False
    try:
        gemini_response = answer_with_gemini(
            db,
            question,
            history,
            verified_products=recent_products or None,
            intent=intent.kind,
        )
        if gemini_response is not None:
            if not gemini_response.get("products") and recent_products:
                gemini_response["products"] = recent_products[:10]
            return gemini_response
    except GeminiProviderError as exc:
        logger.warning("Gemini request failed: %s", str(exc))
        gemini_unavailable = True

    if intent.kind == "greeting":
        return {"answer": _deterministic_answer(intent, []), "products": [], "intent": intent.kind}

    is_count_question = (
        "bao nhieu" in normalized
        and any(term in normalized for term in ("san pham", "hang", "ton kho"))
    )
    if is_count_question and not any(
        term in normalized for term in ("loai nao", "san pham nao", "nhung san pham")
    ):
        statistics = get_product_statistics(db, intent.category)
        return {
            "answer": _statistics_answer(question, statistics),
            "products": [],
            "intent": "statistics",
            "statistics": statistics,
            "source": "sql",
        }

    if "sap het" in normalized or "sắp hết" in question:
        products = get_low_stock_products(db, category=intent.category)
        fallback = (
            "Sản phẩm sắp hết hàng (tồn kho từ 1 đến 5):\n"
            + "\n".join(
                f"- {item['TenSP']}: còn {item['SoLuongTon']}."
                for item in products
            )
            if products
            else "Không có sản phẩm nào đang ở ngưỡng tồn kho từ 1 đến 5."
        )
        return {
            "answer": fallback,
            "products": products,
            "intent": "low_stock",
            "source": "sql",
            "threshold": 5,
        }

    products = search_products(
        db,
        keyword=intent.keyword,
        category=intent.category,
        max_price=intent.max_price,
        min_price=intent.min_price,
        in_stock_only=intent.in_stock_only,
        limit=30,
        sort_by=intent.sort_by,
        descending=intent.descending,
    )
    fallback = _deterministic_answer(intent, products)
    if gemini_unavailable:
        fallback += "\n\n(Lưu ý: Gemini hiện không khả dụng; câu trả lời dựa trên truy vấn SQL.)"
    return {"answer": fallback, "products": products, "intent": intent.kind, "source": "sql"}
