"""Settings from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IBMI_DOCS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    version: str = "7.5.0"
    cache_path: Path = Field(
        default_factory=lambda: Path("~/.cache/ibmi-docs-mcp/docs_cache.db").expanduser()
    )
    ttl_days: int = 30
    max_chars: int = 12000
    http_timeout: float = 20.0
    max_retries: int = 3
    max_concurrency: int = 2
    user_agent: str = "ibmi-docs-mcp/0.1 (+local-agent)"
    base_url: str = "https://www.ibm.com"
    log_level: str = "INFO"

    @field_validator("cache_path", mode="before")
    @classmethod
    def expand_cache_path(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value.expanduser()
        return Path(str(value)).expanduser()

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return str(value).upper()


def load_settings() -> Settings:
    return Settings()
