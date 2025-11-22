"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # OpenAI Configuration
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key")
    OPENAI_MODEL: str = Field(default="gpt-4o", description="OpenAI model to use")

    # Database Configuration
    DATABASE_URL: str = Field(
        ...,
        description="Database connection URL (mysql+aiomysql://user:pass@host:port/db)",
    )
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DATABASE_POOL_RECYCLE: int = Field(default=3600, ge=300)
    DATABASE_ECHO: bool = Field(default=False, description="Log SQL queries")

    # ChromaDB Configuration
    CHROMA_PERSIST_DIR: Path = Field(default=Path("./data/chroma"))
    CHROMA_COLLECTION_NAME: str = Field(default="freelancer_profiles")

    # Application Configuration
    APP_ENV: Literal["development", "production", "test"] = Field(default="development")
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000, ge=1024, le=65535)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")

    # CORS Configuration
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    # LangChain Configuration
    LANGCHAIN_TRACING_V2: bool = Field(default=False)
    LANGCHAIN_API_KEY: str = Field(default="")

    # Proposal Generation Settings
    MAX_RETRIEVAL_CHUNKS: int = Field(default=5, ge=1, le=20)
    SIMILARITY_THRESHOLD: float = Field(default=0.7, ge=0.0, le=1.0)
    LLM_TEMPERATURE: float = Field(default=0.7, ge=0.0, le=2.0)
    MAX_TOKENS: int = Field(default=2000, ge=100, le=4000)
    STREAMING_ENABLED: bool = Field(default=True)

    # Retry Configuration
    MAX_RETRY_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    RETRY_MIN_WAIT: int = Field(default=1, ge=1, description="Min wait seconds")
    RETRY_MAX_WAIT: int = Field(default=10, ge=1, description="Max wait seconds")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("CHROMA_PERSIST_DIR", mode="before")
    @classmethod
    def validate_chroma_dir(cls, v: str | Path) -> Path:
        """Ensure ChromaDB directory exists."""
        path = Path(v) if isinstance(v, str) else v
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
