"""0DTE GEX Backend - Application Configuration."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://odte_user:password@localhost:5432/odte_gex"

    # Data Providers
    polygon_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    debug: bool = True

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
