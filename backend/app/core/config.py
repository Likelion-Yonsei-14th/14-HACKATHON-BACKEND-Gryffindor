from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    recognition_provider: Literal["mock"] = "mock"
    mock_recognition_status: Literal["MATCHED", "AMBIGUOUS", "UNKNOWN"] = "MATCHED"
    mock_recognition_product_id: str | None = "mcm_001"
    recognition_max_image_bytes: int = Field(default=5 * 1024 * 1024, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
