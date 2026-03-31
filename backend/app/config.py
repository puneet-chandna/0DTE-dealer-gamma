"""0DTE GEX Backend - Application Configuration."""

from functools import lru_cache

from pydantic import field_validator
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
    database_url: str = "postgresql+asyncpg://odte_user:odte_password@localhost:5432/odte_gex"

    # Data Providers
    data_provider: str = "yfinance"
    tradier_api_key: str | None = None
    tradier_base_url: str = "https://api.tradier.com/v1"

    # Background Tasks

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    debug: bool = True

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # API Rate Limiting
    api_rate_limit: int = 100  # requests per minute per IP

    # WebSocket Authentication (optional)
    ws_auth_enabled: bool = False
    ws_auth_secret: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Handle JSON-like string from env var
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fallback: comma-separated values
                return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> bool:
        """Accept common deployment strings in addition to strict booleans."""
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False

        return bool(value)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def is_staging(self) -> bool:
        """Check if running in staging mode."""
        return self.environment == "staging"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
