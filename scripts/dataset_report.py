"""Generate a reproducible report for the checked-in GroceryStoreDataset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from dataset_reader import read_classes, read_split

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def inspect_split(dataset_dir: Path, split: str) -> dict[str, Any]:
    rows = read_split(dataset_dir, split)
    label_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    valid_images = 0
    invalid_images: list[str] = []

    for row in rows:
        label = str(row["label_id"])
        label_counts[label] += 1
        category_counts[str(row["coarse_label_id"])] += 1
        image_path = dataset_dir / row["path"]
        try:
            with Image.open(image_path) as image:
                image.verify()
                valid_images += 1
                format_counts[(image.format or "unknown").lower()] += 1
        except Exception as exc:
            invalid_images.append(f"{row['path']}: {type(exc).__name__}")

    return {
        "listed_images": len(rows),
        "valid_images": valid_images,
        "invalid_images": len(invalid_images),
        "invalid_image_paths": invalid_images,
        "labels": len(label_counts),
        "label_counts": dict(sorted(label_counts.items(), key=lambda item: int(item[0]))),
        "coarse_categories": len(category_counts),
        "coarse_category_counts": dict(sorted(category_counts.items(), key=lambda item: int(item[0]))),
        "formats": dict(sorted(format_counts.items())),
    }


def build_report(dataset_dir: Path) -> dict[str, Any]:
    classes = read_classes(dataset_dir)
    splits = {split: inspect_split(dataset_dir, split) for split in ("train", "val", "test")}
    image_files = [
        path.relative_to(dataset_dir).as_posix()
        for path in dataset_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return {
        "dataset": "GroceryStoreDataset",
        "dataset_dir": dataset_dir.as_posix(),
        "license_file_present": (dataset_dir.parent / "LICENSE").exists(),
        "classes": len(classes),
        "class_columns": list(classes[0].keys()) if classes else [],
        "splits": splits,
        "total_split_images": sum(item["listed_images"] for item in splits.values()),
        "total_valid_split_images": sum(item["valid_images"] for item in splits.values()),
        "total_invalid_split_images": sum(item["invalid_images"] for item in splits.values()),
        "recursive_image_files": len(image_files),
        "image_suffixes": sorted({Path(path).suffix.lower() for path in image_files}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("dataset/GroceryStoreDataset/dataset"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dataset_report.json"),
    )
    args = parser.parse_args()
    report = build_report(args.dataset_dir)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã ghi báo cáo dataset: {args.output}")
    print(json.dumps({key: report[key] for key in ("classes", "total_split_images", "total_valid_split_images", "total_invalid_split_images", "recursive_image_files")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
