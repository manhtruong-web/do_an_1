"""Import GroceryStoreDataset labels into SanPhamAnh without inventing business data.

The mapping CSV must contain: NhanDataset,MaSP.
This tool never creates products, prices, stock, categories, or images.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from backend.app.config import settings
from scripts.dataset_reader import read_classes, read_split


INSERT_MAPPING = text("""
    INSERT INTO dbo.SanPhamAnh
        (MaSP, DuongDanAnhDataset, NhanDataset, LaAnhDaiDien, TapDuLieu)
    SELECT :product_id, :dataset_path, :dataset_label, 0, :split
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.SanPhamAnh
        WHERE MaSP = :product_id
          AND DuongDanAnhDataset = :dataset_path
          AND NhanDataset = :dataset_label
          AND TapDuLieu = :split
    )
""")


def read_mapping(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {"NhanDataset", "MaSP"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Mapping CSV phải có cột NhanDataset,MaSP.")
    mapping: dict[str, int] = {}
    for row in rows:
        label = row["NhanDataset"].strip()
        if not label:
            raise ValueError("NhanDataset không được rỗng.")
        product_id = int(row["MaSP"])
        if label in mapping and mapping[label] != product_id:
            raise ValueError(f"Nhãn {label!r} được ánh xạ tới nhiều MaSP.")
        mapping[label] = product_id
    return mapping


def collect_rows(dataset_dir: Path, mapping: dict[str, int], split: str) -> list[dict[str, object]]:
    classes = {
        int(row["Class ID (int)"]): row["Class Name (str)"]
        for row in read_classes(dataset_dir)
    }
    rows: list[dict[str, object]] = []
    for item in read_split(dataset_dir, split):
        label = classes.get(item["label_id"])
        if label in mapping:
            rows.append({
                "product_id": mapping[label],
                "dataset_path": item["path"],
                "dataset_label": label,
                "split": split,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "val", "test", "all"), default="all")
    parser.add_argument("--apply", action="store_true", help="Ghi mapping vào SQL Server; mặc định chỉ dry-run.")
    args = parser.parse_args()

    mapping = read_mapping(args.mapping)
    dataset_dir = settings.dataset_dir
    splits = ("train", "val", "test") if args.split == "all" else (args.split,)
    rows = [row for split in splits for row in collect_rows(dataset_dir, mapping, split)]
    engine = create_engine(settings.database_url, connect_args={"timeout": 5})

    with engine.begin() as connection:
        valid_products = set(connection.execute(text("SELECT MaSP FROM dbo.SanPham WHERE TrangThai = 1")).scalars())
        invalid_products = sorted({row["product_id"] for row in rows} - valid_products)
        if invalid_products:
            raise ValueError(f"MaSP không tồn tại hoặc không active: {invalid_products}")
        before = connection.execute(text("SELECT COUNT(*) FROM dbo.SanPhamAnh")).scalar_one()
        inserted = 0
        if args.apply:
            for row in rows:
                result = connection.execute(INSERT_MAPPING, row)
                inserted += result.rowcount
        after = before + inserted if args.apply else before

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: labels={len(mapping)} candidate_rows={len(rows)}")
    print(f"{mode}: SanPhamAnh_before={before} expected_after={after}")
    if not args.apply:
        print("Chưa ghi dữ liệu. Thêm --apply sau khi kiểm tra mapping.")


if __name__ == "__main__":
    main()
