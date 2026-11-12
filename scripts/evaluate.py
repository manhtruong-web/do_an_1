"""Đánh giá top-1 trên tập test đã có sẵn; không huấn luyện bằng test."""

import json
import sys
from pathlib import Path

import faiss
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_reader import read_split
from backend.app.model import extract_feature


def main() -> None:
    dataset_dir = PROJECT_ROOT / "dataset/GroceryStoreDataset/dataset"
    index = faiss.read_index(str(PROJECT_ROOT / "faiss_index/products.index"))
    metadata = json.loads((PROJECT_ROOT / "faiss_index/metadata.json").read_text(encoding="utf-8"))
    test_rows = read_split(dataset_dir, "test")
    correct = 0
    evaluated = 0
    for row in test_rows:
        image_path = dataset_dir / row["path"]
        if not image_path.exists():
            continue
        with Image.open(image_path) as image:
            distances, positions = index.search(extract_feature(image)[None, :], 1)
        if positions[0][0] >= 0:
            evaluated += 1
            predicted = metadata[int(positions[0][0])]["label_id"]
            correct += predicted == row["label_id"]
    accuracy = correct / evaluated if evaluated else 0
    print(f"Test images evaluated: {evaluated}")
    print(f"Top-1 accuracy: {accuracy:.4f}")
    print("Lưu ý: đây là đánh giá truy hồi bằng nhãn fine-grained; cần bổ sung")
    print("precision/recall/F1 theo bài toán nghiệp vụ khi có bộ ánh xạ SQL Server.")


if __name__ == "__main__":
    main()
