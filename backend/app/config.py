"""Đọc cấu hình từ biến môi trường, không ghi khóa bí mật trong mã nguồn."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "SmartMart AI"
    debug: bool = False
    database_url: str = ""
    database_query_timeout_seconds: int = Field(default=15, ge=1, le=120)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    dataset_dir: Path = Path("../dataset/GroceryStoreDataset/dataset")
    faiss_index_dir: Path = Path("../faiss_index")
    image_search_top_k: int = Field(default=10, ge=1, le=10)
    visual_search_batch_size: int = Field(default=16, ge=1, le=128)
    visual_search_model: str = "ViT-B-32"
    visual_search_pretrained: str = "laion2b_s34b_b79k"
    visual_search_vision_enabled: bool = False
    admin_api_token: str = ""
    max_image_size_mb: int = 8
    allowed_image_types: str = "image/jpeg,image/png,image/webp"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    @field_validator("dataset_dir", "faiss_index_dir", mode="after")
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (BACKEND_DIR / value).resolve()

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_image_types.split(",")}

    @property
    def gemini_configured(self) -> bool:
        return self.gemini_api_key.strip() not in {"", "YOUR_GEMINI_API_KEY", "your_gemini_api_key"}


settings = Settings()
