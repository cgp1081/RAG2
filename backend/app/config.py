"""Application configuration powered by pydantic-settings."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Generator

from dotenv import dotenv_values
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    postgres_url: AnyHttpUrl | str = "postgresql://postgres:postgres@postgres:5432/postgres"
    qdrant_url: AnyHttpUrl | str = "http://qdrant:6333"
    app_version: str = "0.1.0"

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    @classmethod
    def load(cls) -> "Settings":
        """Create settings by merging `.env` values with the environment."""

        env_path = Path(".env")
        file_values = dotenv_values(str(env_path)) if env_path.exists() else {}
        merged = {**file_values, **os.environ}
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
