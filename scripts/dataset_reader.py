"""Đọc GroceryStoreDataset mà không tự tạo nhãn."""

import csv
from pathlib import Path


def read_split(dataset_dir: Path, split: str) -> list[dict]:
    file_path = dataset_dir / f"{split}.txt"
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {file_path}")
    rows = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = next(csv.reader([line], skipinitialspace=True))
        image_path = parts[0].strip()
        fine_label = int(parts[1]) if len(parts) > 1 and parts[1].strip() else None
        coarse_label = int(parts[2]) if len(parts) > 2 and parts[2].strip() else None
        rows.append({
            "split": split,
            "path": image_path,
            "label_id": fine_label,
            "coarse_label_id": coarse_label,
        })
    return rows


def read_classes(dataset_dir: Path) -> list[dict]:
    classes_file = dataset_dir / "classes.csv"
    if not classes_file.exists():
        raise FileNotFoundError(f"Không tìm thấy {classes_file}")
    with classes_file.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file, skipinitialspace=True))


if __name__ == "__main__":
    root = Path("dataset/GroceryStoreDataset/dataset")
    for split in ("train", "val", "test"):
        rows = read_split(root, split)
        print(f"{split}: {len(rows)} ảnh")
    print(f"classes.csv: {len(read_classes(root))} lớp")
