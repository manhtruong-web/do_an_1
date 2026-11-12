#!/usr/bin/env bash
set -euo pipefail

mkdir -p dataset
if [ -d dataset/GroceryStoreDataset/.git ]; then
  git -C dataset/GroceryStoreDataset pull --ff-only
else
  git clone https://github.com/marcusklasson/GroceryStoreDataset.git dataset/GroceryStoreDataset
fi

echo "Đã tải GroceryStoreDataset vào dataset/GroceryStoreDataset"
