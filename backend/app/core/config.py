from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gryffindor Backend"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:55433/gryffindor"
    )
    recognition_provider: Literal["mock", "openai", "openclip"] = "openclip"
    mock_recognition_status: Literal["MATCHED", "AMBIGUOUS", "UNKNOWN"] = "MATCHED"
    mock_recognition_product_id: str | None = "test_outer_001"
    recognition_max_image_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    recognition_max_candidates: int = Field(default=20, gt=0)
    recognition_debug_save_images: bool = False
    recognition_debug_image_dir: Path = Path("artifacts/recognition_crops")
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    openai_vision_model: str = Field(default="gpt-5.6-luna", min_length=1)
    openai_document_model: str = Field(default="gpt-5.6-luna", min_length=1)
    openai_recommendation_model: str = Field(default="gpt-5.6-luna", min_length=1)
    openai_timeout_seconds: float = Field(default=20.0, gt=0)
    recommendation_max_candidates: int = Field(default=50, gt=0)
    openclip_model: str = Field(default="ViT-B-32", min_length=1)
    openclip_pretrained: str = Field(default="laion2b_s34b_b79k", min_length=1)
    openclip_device: str = Field(default="auto", min_length=1)
    openclip_embedding_dimension: int = Field(default=512, gt=0)
    # Calibrated on the Gen2 demo crops; remeasure when the catalog or encoder changes.
    openclip_match_threshold: float = Field(default=0.62, ge=-1, le=1)
    openclip_margin_threshold: float = Field(default=0.06, ge=0, le=2)
    frankfurter_base_url: str = Field(
        default="https://api.frankfurter.dev/v2",
        min_length=1,
    )
    frankfurter_timeout_seconds: float = Field(default=10.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
