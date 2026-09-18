"""Application configuration, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    github_raw_url: str = "https://raw.githubusercontent.com"
    http_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Analysis limits. These keep one request bounded in time, memory and API usage.
    max_tree_entries: int = Field(default=50_000, gt=0)
    max_files_to_fetch: int = Field(default=300, ge=0)
    max_file_bytes: int = Field(default=400_000, gt=0)
    max_total_fetch_bytes: int = Field(default=20_000_000, gt=0)
    fetch_concurrency: int = Field(default=8, ge=1, le=32)

    # Abuse protection. Limits are per client IP; 0 disables a limit.
    rate_limit_per_minute: int = Field(default=10, ge=0)  # analyses per client per minute
    ai_rate_limit_per_hour: int = Field(default=20, ge=0)  # AI summaries per client per hour
    trust_proxy_headers: bool = False  # honor X-Forwarded-For (only behind a trusted proxy)
    # Shared secret between the RepoLens frontend proxy and this API. When set, the client IP
    # the frontend reports in X-RepoLens-Client-IP is trusted only if the secret matches.
    proxy_shared_secret: SecretStr | None = None
    max_concurrent_analyses: int = Field(default=4, ge=1, le=64)
    analysis_timeout_seconds: float = Field(default=110, gt=0, le=600)
    max_request_bytes: int = Field(default=16_384, gt=0)
    enable_docs: bool = True  # serve /docs and /openapi.json

    # In-process caches (0 disables). Results are reused only for identical requests.
    cache_max_entries: int = Field(default=64, ge=0)
    cache_ttl_seconds: float = Field(default=600, ge=0)
    ai_cache_ttl_seconds: float = Field(default=3600, ge=0)

    ai_provider: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_timeout_seconds: float = Field(default=60.0, gt=0, le=300)

    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator(
        "github_token",
        "ai_api_key",
        "ai_provider",
        "ai_model",
        "ai_base_url",
        "proxy_shared_secret",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
