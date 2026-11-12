"""Tìm kiếm ảnh tương tự trực tiếp từ SQL Server.

Đã thay thế hoàn toàn cơ chế lấy ảnh từ dataset bên ngoài / GitHub.
Dữ liệu ảnh và vector embedding được lưu trữ và truy xuất từ SQL Server.
"""

from pathlib import Path
from typing import Any
from PIL import Image

from .image_service import ImageIndex, ProductImageSearchEngine

__all__ = ["ImageIndex", "ProductImageSearchEngine"]
