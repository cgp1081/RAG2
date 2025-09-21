"""Application configuration powered by pydantic-settings.

The settings expose connectivity for the primary Postgres database used by the
SQLAlchemy session factory. Future components should rely on
``Settings.database_url`` rather than hard-coding URIs.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Generator

from dotenv import dotenv_values
from pydantic import AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    postgres_url: AnyHttpUrl | str = "postgresql+psycopg://postgres:postgres@postgres:5432/postgres"
    qdrant_url: AnyHttpUrl | str = "http://qdrant:6333"
    app_version: str = "0.1.0"
    database_url: PostgresDsn | str = "postgresql+psycopg://postgres:postgres@postgres:5432/postgres"
    db_pool_size: int = 10

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    @classmethod
    def load(cls) -> "Settings":
        """Create settings by merging `.env` values with the environment."""

        env_path = Path(".env")
        file_values = dotenv_values(str(env_path)) if env_path.exists() else {}
        merged = {**file_values, **os.environ}
        if "DATABASE_URL" not in merged and "POSTGRES_URL" in merged:
            merged["DATABASE_URL"] = merged["POSTGRES_URL"]
        if "DB_POOL_SIZE" not in merged and "DATABASE_POOL_SIZE" in merged:
            merged["DB_POOL_SIZE"] = merged["DATABASE_POOL_SIZE"]
        # BaseSettings will re-read the OS environment, so pass merged as data.
        return cls(**merged)


def _build_settings() -> Settings:
    return Settings.load()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return _build_settings()


def settings_dependency() -> Generator[Settings, None, None]:
    """FastAPI dependency that yields the cached settings."""

    yield get_settings()


__all__ = ["Settings", "get_settings", "settings_dependency"]
