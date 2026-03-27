from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    google_routes_api_key: str = Field(alias="GOOGLE_ROUTES_API_KEY")
    google_routes_monthly_quota_cap: int = Field(
        default=4500, alias="GOOGLE_ROUTES_MONTHLY_QUOTA_CAP", ge=1
    )

    redis_url: str = Field(alias="REDIS_URL")
    database_url: str = Field(alias="DATABASE_URL")
    cache_ttl_seconds: int = Field(default=300, alias="CACHE_TTL_SECONDS", ge=1)

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

