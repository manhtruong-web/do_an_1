"""Tạo FAISS index từ tập train; val/test không dùng để xây index."""

import json
import sys
from pathlib import Path

import faiss
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_reader import read_split
from backend.app.model import extract_feature


def main() -> None:
    dataset_dir = PROJECT_ROOT / "dataset/GroceryStoreDataset/dataset"
    classes = {
        int(item["Class ID (int)"]): item["Class Name (str)"]
        for item in __import__("dataset_reader").read_classes(dataset_dir)
    }
    output_dir = PROJECT_ROOT / "faiss_index"
    output_dir.mkdir(exist_ok=True)
    rows = read_split(dataset_dir, "train")
    vectors, metadata = [], []
    for number, row in enumerate(rows, start=1):
        image_path = dataset_dir / row["path"]
        if not image_path.exists():
            print(f"Bỏ qua ảnh không tồn tại: {image_path}")
            continue
        try:
            with Image.open(image_path) as image:
                vectors.append(extract_feature(image))
            metadata.append({
                "path": row["path"],
                "label": classes.get(row["label_id"], ""),
                "label_id": row["label_id"],
                "split": "train",
            })
        except Exception as exc:
            print(f"Bỏ qua {image_path}: {exc}")
        if number % 100 == 0:
            print(f"Đã xử lý {number}/{len(rows)}")
    if not vectors:
        raise RuntimeError("Không trích xuất được vector nào.")
    matrix = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, str(output_dir / "products.index"))
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Đã tạo index với {len(metadata)} ảnh.")


if __name__ == "__main__":
    main()
