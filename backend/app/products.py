"""Các truy vấn sản phẩm dùng tham số hóa, tránh ghép chuỗi SQL."""

from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any
import math
import re
import unicodedata

from sqlalchemy import text
from sqlalchemy.orm import Session


SEARCH_ALIASES = {
    "sua": ("sua", "milk"),
    "milk": ("milk", "sua"),
    "tao": ("tao", "apple"),
    "apple": ("apple", "tao"),
    "chuoi": ("chuoi", "banana"),
    "banana": ("banana", "chuoi"),
    "cam": ("cam", "orange"),
    "orange": ("orange", "cam"),
    "dua": ("dua", "cucumber", "melon"),
    "cucumber": ("cucumber", "dua chuot"),
    "ca chua": ("ca chua", "tomato"),
    "tomato": ("tomato", "ca chua"),
    "khoai tay": ("khoai tay", "potato"),
    "potato": ("potato", "khoai tay"),
    "ca rot": ("ca rot", "carrot"),
    "carrot": ("carrot", "ca rot"),
    "bo": ("bo", "avocado"),
    "avocado": ("avocado", "bo"),
    "nam": ("nam", "mushroom"),
    "mushroom": ("mushroom", "nam"),
    "nuoc ep": ("nuoc ep", "juice"),
    "juice": ("juice", "nuoc ep"),
}

MAX_SEARCH_CANDIDATES = 5000

SEARCH_STOP_WORDS = {
    "cac", "cho", "co", "cua", "gi", "giup", "hay", "khong", "la", "loai", "nao",
    "nhe", "nhung", "san", "pham", "toi", "tim", "tu", "va", "voi", "muon",
    "mua", "nen", "hang", "gia", "hon", "re", "can", "xin", "vui", "long",
    "tai", "ton",
}

SEARCH_PHRASE_ALIASES = {
    "nuoc ngot": ("nuoc giai khat", "do uong"),
    "nuoc giai khat": ("nuoc ngot", "do uong"),
    "banh an sang": ("banh mi sandwich", "ngu coc", "yen mach"),
}

CATEGORY_ALIASES = {
    "fruit": ("fruit", "trai cay", "hoa qua"),
    "vegetable": ("vegetable", "rau cu", "rau", "vegetables"),
    "meat": ("meat", "thit"),
    "fish": ("fish", "ca", "hai san"),
    "juice": ("juice", "nuoc ep", "do uong", "nuoc uong"),
    "candy": ("candy", "banh keo", "banh", "keo"),
    "milk": ("milk", "sua", "dairy"),
}


def _normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    normalized = without_marks.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _search_tokens(value: str) -> list[str]:
    return [
        token
        for token in _normalize_search_text(value).split()
        if token not in SEARCH_STOP_WORDS
    ]


def _term_match_score(term: str, field_tokens: set[str]) -> float:
    if term in field_tokens:
        return 1.0
    if any(alias in field_tokens for alias in SEARCH_ALIASES.get(term, ())):
        return 0.9
    if len(term) < 3:
        return 0.0

    best = 0.0
    for candidate in field_tokens:
        if len(candidate) >= 3 and (
            candidate.startswith(term) or term.startswith(candidate)
        ):
            best = max(best, 0.82)
            continue
        if len(term) >= 4 and len(candidate) >= 4 and abs(len(term) - len(candidate)) <= 2:
            similarity = SequenceMatcher(None, term, candidate, autojunk=False).ratio()
            threshold = 0.75 if min(len(term), len(candidate)) <= 5 else 0.8
            if similarity >= threshold:
                best = max(best, similarity)
    return best


def _product_relevance(product: dict[str, Any], keyword: str) -> tuple[float, int, int]:
    normalized_query = _normalize_search_text(keyword)
    terms = _search_tokens(keyword)
    if not terms:
        return 0.0, 0, 0

    fields = (
        (12.0, _normalize_search_text(str(product.get("TenSP") or ""))),
        (10.0, _normalize_search_text(str(product.get("ThuongHieu") or ""))),
        (6.0, _normalize_search_text(str(product.get("DanhMuc") or ""))),
        (3.0, _normalize_search_text(str(product.get("MoTa") or ""))),
    )
    product_id = str(product.get("MaSP") or "")
    if product_id in terms:
        return 1000.0, 1, 1

    aliases = SEARCH_PHRASE_ALIASES.get(" ".join(terms), ())
    if aliases:
        alias_score = max(
            (weight * 4.0 for weight, value in fields for alias in aliases if alias in value),
            default=0.0,
        )
        if alias_score:
            return alias_score, len(terms), len(terms)

    field_tokens = [(weight, set(value.split())) for weight, value in fields]
    score = 0.0
    matched_terms = 0
    for term in terms:
        best_match = max(
            (
                weight * _term_match_score(term, tokens)
                for weight, tokens in field_tokens
            ),
            default=0.0,
        )
        if best_match:
            matched_terms += 1
            score += best_match

    required_matches = max(1, math.ceil(len(terms) * 0.6))
    if matched_terms < required_matches:
        return 0.0, matched_terms, len(terms)

    for weight, value in fields:
        if normalized_query in value:
            score += weight * 2.0
            break
    return score, matched_terms, len(terms)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def get_product_by_id(db: Session, product_id: int) -> dict[str, Any] | None:
    query = text("""
        SELECT sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
               sp.MoTa, sp.ThuongHieu, sp.Anh, sp.DonViTinh,
               sp.GiaBan, sp.SoLuongTon, sp.HanSuDung
        FROM dbo.SanPham sp
        INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
        WHERE sp.MaSP = :product_id AND sp.TrangThai = 1
    """)
    row = db.execute(query, {"product_id": product_id}).mappings().first()
    return dict(row) if row else None


def get_product_statistics(
    db: Session,
    category: str | None = None,
) -> dict[str, int | str | None]:
    category_filter = ""
    params: dict[str, Any] = {}
    if category:
        category_filter = "AND dm.TenDM COLLATE Vietnamese_CI_AI LIKE :category"
        params["category"] = f"%{category.strip()}%"
    row = db.execute(
        text(f"""
            SELECT COUNT(*) AS total_products,
                   SUM(CASE WHEN sp.SoLuongTon > 0 THEN 1 ELSE 0 END) AS in_stock_products,
                   SUM(CASE WHEN sp.SoLuongTon = 0 THEN 1 ELSE 0 END) AS out_of_stock_products
            FROM dbo.SanPham sp
            INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
            WHERE sp.TrangThai = 1 {category_filter}
        """),
        params,
    ).mappings().one()
    return {
        "category": category,
        "total_products": int(row["total_products"] or 0),
        "in_stock_products": int(row["in_stock_products"] or 0),
        "out_of_stock_products": int(row["out_of_stock_products"] or 0),
    }


def get_low_stock_products(
    db: Session,
    threshold: int = 5,
    category: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    safe_threshold = min(max(threshold, 1), 100)
    safe_limit = min(max(limit, 1), 100)
    category_filter = ""
    params: dict[str, Any] = {"threshold": safe_threshold}
    if category:
        category_filter = "AND dm.TenDM COLLATE Vietnamese_CI_AI LIKE :category"
        params["category"] = f"%{category.strip()}%"
    query = text(f"""
        SELECT TOP {safe_limit} sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
               sp.MoTa, sp.ThuongHieu, sp.Anh, sp.DonViTinh,
               sp.GiaBan, sp.SoLuongTon, sp.HanSuDung
        FROM dbo.SanPham sp
        INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
        WHERE sp.TrangThai = 1 AND sp.SoLuongTon BETWEEN 1 AND :threshold
              {category_filter}
        ORDER BY sp.SoLuongTon ASC, sp.TenSP ASC
    """)
    return [_row_to_dict(row) for row in db.execute(query, params).fetchall()]


def list_categories(db: Session) -> list[dict[str, Any]]:
    query = text("""
        SELECT dm.MaDM, dm.TenDM, dm.MoTa,
               COUNT(CASE WHEN sp.TrangThai = 1 THEN sp.MaSP END) AS SoLuongSanPham
        FROM dbo.DanhMuc dm
        LEFT JOIN dbo.SanPham sp ON sp.MaDM = dm.MaDM
        WHERE dm.TrangThai = 1
        GROUP BY dm.MaDM, dm.TenDM, dm.MoTa
        ORDER BY dm.TenDM
    """)
    return [dict(row) for row in db.execute(query).mappings().all()]


def list_brands(db: Session) -> list[dict[str, Any]]:
    query = text("""
        SELECT LTRIM(RTRIM(sp.ThuongHieu)) AS ThuongHieu,
               COUNT(*) AS SoLuongSanPham
        FROM dbo.SanPham sp
        WHERE sp.TrangThai = 1
          AND NULLIF(LTRIM(RTRIM(sp.ThuongHieu)), '') IS NOT NULL
        GROUP BY LTRIM(RTRIM(sp.ThuongHieu))
        ORDER BY LTRIM(RTRIM(sp.ThuongHieu))
    """)
    return [dict(row) for row in db.execute(query).mappings().all()]


def get_product_filter_options(db: Session) -> dict[str, Any]:
    totals = db.execute(
        text("""
            SELECT COUNT(*) AS total_products,
                   MIN(sp.GiaBan) AS min_price,
                   MAX(sp.GiaBan) AS max_price
            FROM dbo.SanPham sp
            WHERE sp.TrangThai = 1
        """)
    ).mappings().one()
    return {
        "total_products": int(totals["total_products"] or 0),
        "min_price": int(totals["min_price"] or 0),
        "max_price": int(totals["max_price"] or 0),
        "categories": list_categories(db),
        "brands": list_brands(db),
    }


def search_products(
    db: Session,
    keyword: str | None = None,
    category: str | None = None,
    brand: str | list[str] | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    in_stock_only: bool = False,
    out_of_stock_only: bool = False,
    limit: int = 50,
    sort_by: str = "name",
    descending: bool = False,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions = ["sp.TrangThai = 1"]
    params: dict[str, Any] = {}
    safe_limit = min(max(limit, 1), 100)
    safe_offset = min(max(offset, 0), 1_000_000)
    if category:
        category_conditions = []
        normalized_category = _normalize_search_text(category)
        for index, alias in enumerate(CATEGORY_ALIASES.get(normalized_category, (category,))):
            param_name = f"category_{index}"
            category_conditions.append(f"dm.TenDM COLLATE Vietnamese_CI_AI LIKE :{param_name}")
            params[param_name] = f"%{alias}%"
        conditions.append("(" + " OR ".join(category_conditions) + ")")
    brands = [brand] if isinstance(brand, str) else (brand or [])
    brands = [item.strip() for item in brands if item and item.strip()]
    if brands:
        brand_conditions = []
        for index, value in enumerate(brands):
            param_name = f"brand_{index}"
            brand_conditions.append(
                f"sp.ThuongHieu COLLATE Vietnamese_CI_AI LIKE :{param_name}"
            )
            params[param_name] = f"%{value}%"
        conditions.append("(" + " OR ".join(brand_conditions) + ")")
    if min_price is not None:
        conditions.append("sp.GiaBan >= :min_price")
        params["min_price"] = min_price
    if max_price is not None:
        conditions.append("sp.GiaBan <= :max_price")
        params["max_price"] = max_price
    if in_stock_only and not out_of_stock_only:
        conditions.append("sp.SoLuongTon > 0")
    elif out_of_stock_only and not in_stock_only:
        conditions.append("sp.SoLuongTon = 0")

    query = text(f"""
        SELECT TOP {MAX_SEARCH_CANDIDATES} sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
               sp.MoTa, sp.ThuongHieu, sp.Anh, sp.DonViTinh,
               sp.GiaBan, sp.SoLuongTon, sp.HanSuDung
        FROM dbo.SanPham sp
        INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
        WHERE {' AND '.join(conditions)}
        ORDER BY sp.MaSP ASC
    """)
    products = [_row_to_dict(row) for row in db.execute(query, params).fetchall()]
    scored_products = []
    for product in products:
        score = _product_relevance(product, keyword)[0] if keyword else 0.0
        if keyword and score <= 0:
            continue
        scored_products.append((score, product))

    if sort_by == "relevance" and keyword:
        scored_products.sort(
            key=lambda item: (-item[0], _normalize_search_text(str(item[1].get("TenSP") or "")), int(item[1]["MaSP"]))
        )
    elif sort_by == "price":
        scored_products.sort(
            key=lambda item: (
                -Decimal(str(item[1].get("GiaBan") or 0)) if descending else Decimal(str(item[1].get("GiaBan") or 0)),
                _normalize_search_text(str(item[1].get("TenSP") or "")),
            )
        )
    elif sort_by == "stock":
        scored_products.sort(
            key=lambda item: (
                -int(item[1].get("SoLuongTon") or 0) if descending else int(item[1].get("SoLuongTon") or 0),
                _normalize_search_text(str(item[1].get("TenSP") or "")),
            )
        )
    else:
        scored_products.sort(
            key=lambda item: (
                _normalize_search_text(str(item[1].get("TenSP") or "")),
                int(item[1].get("MaSP") or 0),
            ),
            reverse=descending,
        )
    return [product for _, product in scored_products[safe_offset:safe_offset + safe_limit]]


def find_products_by_dataset_labels(db: Session, labels: list[str]) -> list[dict[str, Any]]:
    """Chỉ trả về sản phẩm có ánh xạ thật trong SQL Server."""
    if not labels:
        return []
    placeholders = ", ".join(f":label_{i}" for i in range(len(labels)))
    params = {f"label_{i}": label for i, label in enumerate(labels)}
    query = text(f"""
        SELECT DISTINCT TOP 50 sp.MaSP, sp.TenSP, dm.TenDM AS DanhMuc,
               sp.MoTa, sp.ThuongHieu, sp.Anh, sp.DonViTinh,
               sp.GiaBan, sp.SoLuongTon, sp.HanSuDung
        FROM dbo.SanPham sp
        INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
        INNER JOIN dbo.SanPhamAnh spa ON spa.MaSP = sp.MaSP
        WHERE sp.TrangThai = 1 AND spa.NhanDataset IN ({placeholders})
        ORDER BY sp.TenSP
    """)
    return [_row_to_dict(row) for row in db.execute(query, params).fetchall()]


def format_product_context(products: list[dict[str, Any]]) -> str:
    """Tạo dữ liệu có nguồn cho prompt; không tạo sản phẩm ngoài DB."""
    if not products:
        return "Không tìm thấy sản phẩm phù hợp trong cơ sở dữ liệu siêu thị."
    lines = []
    for product in products:
        stock = "còn hàng" if product["SoLuongTon"] > 0 else "hết hàng"
        lines.append(
            f"- {product['TenSP']} | danh mục: {product['DanhMuc']} | "
            f"thương hiệu: {product['ThuongHieu'] or 'chưa cập nhật'} | "
            f"giá: {product['GiaBan']} | {stock} | tồn: {product['SoLuongTon']}"
        )
    return "\n".join(lines)
