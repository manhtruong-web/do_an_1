"""
Script nạp hình ảnh sản phẩm trực tiếp vào SQL Server:
- Bảng dbo.SanPham.HinhAnh (VARBINARY(MAX))
- Bảng dbo.SystemDefaultImage
- Bảng dbo.AI_ProductImageEmbedding (Vector 512 chiều trích xuất từ ảnh trong SQL Server)
- Cập nhật trường dbo.SanPham.Anh = '/api/products/' + MaSP + '/image'
Hoàn toàn độc lập, không dùng GitHub hay Internet.
"""

from __future__ import annotations

import io
import json
import hashlib
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
import numpy as np
import torch
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings
from backend.app.model import extract_feature

DEFAULT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#e2e8f0"/>
    </linearGradient>
  </defs>
  <rect width="400" height="400" fill="url(#bg)" rx="16"/>
  <circle cx="200" cy="170" r="70" fill="#cbd5e1" opacity="0.6"/>
  <path d="M165 190 L185 160 L205 180 L220 165 L245 195 Z" fill="#64748b"/>
  <circle cx="180" cy="150" r="12" fill="#e2e8f0"/>
  <text x="200" y="270" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="22" font-weight="600" fill="#334155">SmartMart AI</text>
  <text x="200" y="300" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="14" fill="#64748b">Ảnh sản phẩm mặc định</text>
</svg>"""


def generate_product_card_image(product_name: str, category_name: str, brand: str) -> bytes:
    """Tạo ảnh minh họa sản phẩm chất lượng cao chuẩn siêu thị dưới dạng JPEG bytes."""
    width, height = 400, 400
    img = Image.new("RGB", (width, height), color="#f1f5f9")
    draw = ImageDraw.Draw(img)

    # Gradient/header bar
    colors = {
        "Sữa": ("#e0f2fe", "#0284c7"),
        "Đồ uống": ("#fef3c7", "#d97706"),
        "Rau củ": ("#dcfce7", "#16a34a"),
        "Trái cây": ("#ffedd5", "#ea580c"),
        "Thịt": ("#ffe4e6", "#e11d48"),
        "Bánh kẹo": ("#f3e8ff", "#9333ea"),
        "Gia vị": ("#fef9c3", "#ca8a04"),
        "Thực phẩm khô": ("#f5d0fe", "#c026d3"),
        "Hóa mỹ phẩm": ("#ccfbf1", "#0d9488"),
        "Đồ gia dụng": ("#e2e8f0", "#475569"),
    }
    bg_color, theme_color = colors.get(category_name.split()[0], ("#e2e8f0", "#2563eb"))

    draw.rectangle([0, 0, width, height], fill=bg_color)
    draw.rounded_rectangle([20, 20, width - 20, height - 20], radius=16, fill="white", outline=theme_color, width=3)
    draw.rounded_rectangle([30, 30, width - 30, 90], radius=8, fill=theme_color)

    # Thử load font hệ thống hoặc vẽ mặc định
    try:
        font_large = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_header = ImageFont.truetype("arialbd.ttf", 18)
    except Exception:
        font_large = font_small = font_header = ImageFont.load_default()

    draw.text((width / 2, 60), f"SmartMart AI · {category_name}", fill="white", anchor="mm", font=font_header)

    # Box icon / center
    draw.rounded_rectangle([70, 110, width - 70, 250], radius=12, fill="#f8fafc", outline="#cbd5e1", width=2)
    brand_display = brand if brand else "SmartMart"
    draw.text((width / 2, 160), brand_display.upper(), fill=theme_color, anchor="mm", font=font_header)
    draw.text((width / 2, 200), "CHÍNH HÃNG", fill="#64748b", anchor="mm", font=font_small)

    # Tên sản phẩm
    # Wrap text nếu quá dài
    words = product_name.split()
    line1 = " ".join(words[:4])
    line2 = " ".join(words[4:9]) if len(words) > 4 else ""

    draw.text((width / 2, 280), line1, fill="#0f172a", anchor="mm", font=font_large)
    if line2:
        draw.text((width / 2, 310), line2, fill="#0f172a", anchor="mm", font=font_large)

    draw.text((width / 2, 355), "SIÊU THỊ THÔNG MINH SMARTMART", fill="#94a3b8", anchor="mm", font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# Mapping các sản phẩm cụ thể sang ảnh iconic thật có sẵn trong dataset
DATASET_ICONIC_MAP = {
    "táo đỏ": "Fruit/Apple/Red-Delicious/Red-Delicious_Iconic.jpg",
    "táo xanh": "Fruit/Apple/Granny-Smith/Granny-Smith_Iconic.jpg",
    "táo vàng": "Fruit/Apple/Golden-Delicious/Golden-Delicious_Iconic.jpg",
    "golden delicious": "Fruit/Apple/Golden-Delicious/Golden-Delicious_Iconic.jpg",
    "chuối già": "Fruit/Banana/Banana_Iconic.jpg",
    "chuối": "Fruit/Banana/Banana_Iconic.jpg",
    "cam": "Fruit/Orange/Orange_Iconic.jpg",
    "kiwi": "Fruit/Kiwi/Kiwi_Iconic.jpg",
    "cà rốt": "Vegetables/Carrots/Carrots_Iconic.jpg",
    "khoai tây": "Vegetables/Potato/Floury-Potato/Floury-Potato_Iconic.jpg",
    "cà chua": "Vegetables/Tomato/Regular-Tomato/Regular-Tomato_Iconic.jpg",
    "dưa leo": "Vegetables/Cucumber/Cucumber_Iconic.jpg",
    "tỏi": "Vegetables/Garlic/Garlic_Iconic.jpg",
    "hành tây": "Vegetables/Onion/Yellow-Onion/Yellow-Onion_Iconic.jpg",
    "ớt đỏ": "Vegetables/Pepper/Red-Bell-Pepper/Red-Bell-Pepper_Iconic.jpg",
    "bắp cải": "Vegetables/Cabbage/Cabbage_Iconic.jpg",
    "nấm": "Vegetables/Mushroom/Brown-Cap-Mushroom/Brown-Cap-Mushroom_Iconic.jpg",
    "nước cam": "Packages/Juice/Bravo-Orange-Juice/Bravo-Orange-Juice_Iconic.jpg",
    "nước táo": "Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_Iconic.jpg",
    "sữa tươi vinamilk": "Packages/Milk/Arla-Standard-Milk/Arla-Standard-Milk_Iconic.jpg",
    "sữa tươi th": "Packages/Milk/Arla-Medium-Fat-Milk/Arla-Medium-Fat-Milk_Iconic.jpg",
    "sữa đậu nành": "Packages/Soy-Milk/Alpro-Fresh-Soy-Milk/Alpro-Fresh-Soy-Milk_Iconic.jpg",
    "sữa chua": "Packages/Yoghurt/Arla-Natural-Yoghurt/Arla-Natural-Yoghurt_Iconic.jpg",
    "bơ lạt": "Packages/Sour-Cream/Arla-Sour-Cream/Arla-Sour-Cream_Iconic.jpg",
}


def get_image_bytes_for_product(product_name: str, category_name: str, brand: str) -> bytes:
    """Lấy byte ảnh: Ưu tiên ảnh chụp iconic thực tế nếu khớp từ khóa, hoặc sinh ảnh sản phẩm chuyên nghiệp."""
    norm_name = product_name.lower()
    iconic_root = PROJECT_ROOT / "dataset/GroceryStoreDataset/dataset/iconic-images-and-descriptions"

    for kw, rel_path in DATASET_ICONIC_MAP.items():
        if kw in norm_name:
            full_path = iconic_root / rel_path
            if full_path.exists():
                return full_path.read_bytes()

    # Nếu không có ảnh iconic trực tiếp, sinh ảnh chuẩn đồ họa SmartMart
    return generate_product_card_image(product_name, category_name, brand)


def main():
    print("--- BẮT ĐẦU NẠP ẢNH SẢN PHẨM VÀO SQL SERVER ---")
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        # 1. Nạp ảnh mặc định hệ thống vào SystemDefaultImage
        svg_bytes = DEFAULT_SVG.encode("utf-8")
        conn.execute(
            text("""
                MERGE dbo.SystemDefaultImage AS target
                USING (SELECT :img_key AS ImageKey, :img_data AS ImageData, :mime AS MimeType, :descr AS Description) AS source
                ON (target.ImageKey = source.ImageKey)
                WHEN MATCHED THEN
                    UPDATE SET ImageData = source.ImageData, MimeType = source.MimeType, Description = source.Description, UpdatedAt = SYSDATETIME()
                WHEN NOT MATCHED THEN
                    INSERT (ImageKey, ImageData, MimeType, Description, UpdatedAt)
                    VALUES (source.ImageKey, source.ImageData, source.MimeType, source.Description, SYSDATETIME());
            """),
            {
                "img_key": "default_product",
                "img_data": svg_bytes,
                "mime": "image/svg+xml",
                "descr": "Ảnh mặc định hệ thống SmartMart AI",
            }
        )
        print("Đã lưu ảnh mặc định hệ thống vào dbo.SystemDefaultImage.")

        # 2. Đọc toàn bộ sản phẩm từ SQL Server
        products = conn.execute(
            text("""
                SELECT sp.MaSP, sp.TenSP, dm.TenDM, sp.ThuongHieu, sp.HinhAnh
                FROM dbo.SanPham sp
                INNER JOIN dbo.DanhMuc dm ON dm.MaDM = sp.MaDM
                WHERE sp.TrangThai = 1
                ORDER BY sp.MaSP
            """)
        ).fetchall()
        print(f"Tổng số sản phẩm cần kiểm tra/nạp ảnh: {len(products)}")

        loaded_count = 0
        embedding_count = 0

        for row in products:
            masp = row[0]
            tensp = row[1]
            tendm = row[2]
            thuonghieu = row[3] or ""
            existing_image = row[4]

            # Lấy hoặc tạo bytes ảnh
            if existing_image:
                img_bytes = bytes(existing_image)
            else:
                img_bytes = get_image_bytes_for_product(tensp, tendm, thuonghieu)
                # Lưu vào SanPham.HinhAnh và cập nhật Anh URL
                conn.execute(
                    text("""
                        UPDATE dbo.SanPham
                        SET HinhAnh = :img_bytes,
                            Anh = :img_url,
                            NgayCapNhat = SYSDATETIME()
                        WHERE MaSP = :masp
                    """),
                    {
                        "img_bytes": img_bytes,
                        "img_url": f"/api/products/{masp}/image",
                        "masp": masp,
                    }
                )
                loaded_count += 1

            # 3. Trích xuất vector đặc trưng ResNet18 từ byte ảnh trong SQL Server
            content_hash = hashlib.sha256(img_bytes).hexdigest()

            # Kiểm tra xem embedding đã tồn tại chưa
            chk = conn.execute(
                text("SELECT ContentHash FROM dbo.AI_ProductImageEmbedding WHERE MaSP = :masp"),
                {"masp": masp}
            ).fetchone()

            if not chk or chk[0] != content_hash:
                try:
                    pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    vector = extract_feature(pil_img)
                    vector_json = json.dumps(vector.tolist())

                    conn.execute(
                        text("""
                            MERGE dbo.AI_ProductImageEmbedding AS target
                            USING (SELECT :masp AS MaSP, :vec AS EmbeddingJson, 512 AS Dimensions, :hash AS ContentHash) AS source
                            ON (target.MaSP = source.MaSP)
                            WHEN MATCHED THEN
                                UPDATE SET EmbeddingJson = source.EmbeddingJson, ContentHash = source.ContentHash, UpdatedAt = SYSDATETIME()
                            WHEN NOT MATCHED THEN
                                INSERT (MaSP, EmbeddingJson, Dimensions, ContentHash, UpdatedAt)
                                VALUES (source.MaSP, source.EmbeddingJson, source.Dimensions, source.ContentHash, SYSDATETIME());
                        """),
                        {
                            "masp": masp,
                            "vec": vector_json,
                            "hash": content_hash,
                        }
                    )
                    embedding_count += 1
                except Exception as exc:
                    print(f"Lỗi tạo embedding cho MaSP={masp}: {exc}")

            if masp % 25 == 0:
                print(f"Tiến độ: đã xử lý {masp}/{len(products)} sản phẩm.")

    print(f"\n--- HOÀN THÀNH ---")
    print(f"- Số ảnh sản phẩm mới được nạp vào SQL Server: {loaded_count}")
    print(f"- Số vector đặc trưng (ResNet18) đã lưu vào SQL Server: {embedding_count}")


if __name__ == "__main__":
    main()
